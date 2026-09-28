import logging
from datetime import timedelta
from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from .models import Campaign, CampaignRecipient, Contact, EmailEvent
from .services import EmailService, DeliveryError, blocked, build_payload, refresh_counts, publish_campaign
from .utils import VARIABLES

logger = logging.getLogger('mailing')

def deliver_recipient(campaign_id, recipient_id):
    # Commit the exact request before the external side effect. All workers lock
    # campaign then recipient, so duplicate tasks cannot send a recipient concurrently.
    with transaction.atomic():
        campaign = Campaign.objects.select_for_update().get(pk=campaign_id)
        if campaign.status not in ('queued', 'sending'):
            return None
        recipient = CampaignRecipient.objects.select_for_update().get(pk=recipient_id)
        if recipient.status not in ('pending', 'queued'):
            return None
        if recipient.next_attempt_at and recipient.next_attempt_at > timezone.now():
            return max(1, int((recipient.next_attempt_at - timezone.now()).total_seconds()))
        if not recipient.delivery_payload:
            url = f'{settings.BACKEND_URL}/api/email/unsubscribe/{recipient.unsubscribe_token}/'
            recipient.delivery_payload = build_payload(campaign, recipient.email, {key: getattr(recipient, key) for key in VARIABLES}, url)
            recipient.first_attempt_at = timezone.now()
            recipient.save(update_fields=['delivery_payload', 'first_attempt_at', 'updated_at'])

    delay = None
    with transaction.atomic():
        campaign = Campaign.objects.select_for_update().get(pk=campaign_id)
        if campaign.status not in ('queued', 'sending'):
            return None
        recipient = CampaignRecipient.objects.select_for_update().get(pk=recipient_id)
        if recipient.status not in ('pending', 'queued'):
            return None
        if recipient.next_attempt_at and recipient.next_attempt_at > timezone.now():
            return max(1, int((recipient.next_attempt_at - timezone.now()).total_seconds()))
        contact = Contact.objects.select_for_update().get(pk=recipient.contact_id)
        if blocked(recipient.email, contact):
            recipient.status = 'suppressed'
            recipient.error_message = 'Recipient no longer eligible.'
        elif recipient.first_attempt_at < timezone.now() - timedelta(hours=23):
            # Never automatically replay an ambiguous send outside provider retention.
            recipient.status = 'failed'
            recipient.failed_at = timezone.now()
            recipient.error_message = 'Idempotency window expired; reconcile with provider before any manual resend.'
        else:
            try:
                result = EmailService().send_email(recipient.delivery_payload, f'campaign-{campaign_id}-recipient-{recipient_id}')
                if not isinstance(result, dict) or not result.get('id'):
                    raise DeliveryError('Provider returned an incomplete response.', temporary=True)
            except DeliveryError as exc:
                recipient.error_message = str(exc)
                if exc.temporary and recipient.retry_count < settings.EMAIL_RETRY_LIMIT:
                    recipient.retry_count += 1
                    delay = 30 * (2 ** (recipient.retry_count - 1))
                    recipient.next_attempt_at = timezone.now() + timedelta(seconds=delay)
                    recipient.status = 'queued'
                else:
                    recipient.status = 'failed'
                    recipient.failed_at = timezone.now()
                logger.warning('email send failure recipient=%s temporary=%s', recipient_id, exc.temporary)
            else:
                recipient.provider_message_id = result['id']
                recipient.status = 'sent'
                recipient.sent_at = timezone.now()
                recipient.error_message = ''
                contact.last_email_sent_at = recipient.sent_at
                contact.save(update_fields=['last_email_sent_at', 'updated_at'])
        recipient.save()
        refresh_counts(campaign_id)
    # Reconcile webhooks that arrived before the provider response was committed.
    if recipient.provider_message_id:
        from .webhooks import process_event
        for event_id in EmailEvent.objects.filter(provider_message_id=recipient.provider_message_id, processed_at__isnull=True).values_list('id', flat=True):
            process_event(event_id)
    return delay

@shared_task(bind=True, max_retries=None)
def send_campaign(self, campaign_id):
    with transaction.atomic():
        campaign = Campaign.objects.select_for_update().get(pk=campaign_id)
        if campaign.status not in ('queued', 'sending'):
            return
        campaign.status = 'sending'
        campaign.started_at = campaign.started_at or timezone.now()
        campaign.save(update_fields=['status', 'started_at', 'updated_at'])
    logger.info('campaign started id=%s', campaign_id)
    delays = []
    # Bounded database chunks; individual sends keep per-recipient idempotency and
    # suppression/cancellation checks immediately adjacent to every provider call.
    cursor = 0
    while True:
        ids = list(CampaignRecipient.objects.filter(campaign_id=campaign_id, pk__gt=cursor,
            status__in=['pending', 'queued']).order_by('pk').values_list('pk', flat=True)[:settings.EMAIL_BATCH_SIZE])
        if not ids:
            break
        for recipient_id in ids:
            delay = deliver_recipient(campaign_id, recipient_id)
            if delay:
                delays.append(delay)
        cursor = ids[-1]
        if Campaign.objects.get(pk=campaign_id).status == 'cancelled':
            return
    with transaction.atomic():
        campaign = Campaign.objects.select_for_update().get(pk=campaign_id)
        refresh_counts(campaign_id)
        if campaign.status != 'cancelled' and not campaign.recipients.filter(status__in=['pending', 'queued']).exists():
            campaign.status = 'failed' if campaign.recipients.exists() and not campaign.recipients.filter(sent_at__isnull=False).exists() and campaign.recipients.filter(status='failed').exists() else 'completed'
            campaign.completed_at = timezone.now()
            campaign.save(update_fields=['status', 'completed_at', 'updated_at'])
            logger.info('campaign %s id=%s', campaign.status, campaign_id)
    if delays:
        raise self.retry(countdown=min(delays))

@shared_task
def dispatch_due_campaigns():
    now = timezone.now()
    candidates = Campaign.objects.filter(Q(status='scheduled', scheduled_at__lte=now) |
        Q(status__in=['queued', 'sending'], updated_at__lt=now - timedelta(minutes=5)))
    dispatched = 0
    for campaign_id in list(candidates.values_list('id', flat=True)):
        with transaction.atomic():
            campaign = Campaign.objects.select_for_update().get(pk=campaign_id)
            due = campaign.status == 'scheduled' and campaign.scheduled_at <= now
            stale = campaign.status in ('queued', 'sending') and campaign.updated_at < now - timedelta(minutes=5)
            if not (due or stale):
                continue
            campaign.status = 'queued'
            campaign.save(update_fields=['status', 'updated_at'])
            transaction.on_commit(lambda pk=campaign_id: publish_campaign(pk))
            dispatched += 1
    return dispatched

import logging
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from svix.webhooks import Webhook, WebhookVerificationError
from .models import Campaign, CampaignRecipient, Contact, EmailEvent, Suppression
from .services import refresh_counts

logger = logging.getLogger('mailing')

@transaction.atomic
def process_event(event_id):
    event = EmailEvent.objects.get(pk=event_id)
    recipient = CampaignRecipient.objects.filter(provider_message_id=event.provider_message_id).first() if event.provider_message_id else None
    if not recipient:
        return
    Campaign.objects.select_for_update().get(pk=recipient.campaign_id)
    event = EmailEvent.objects.select_for_update().get(pk=event_id)
    if event.processed_at:
        return
    recipient = CampaignRecipient.objects.select_for_update().get(pk=recipient.pk)
    contact = Contact.objects.select_for_update().get(pk=recipient.contact_id)
    kind, when = event.event_type, event.occurred_at
    fields = {'email.sent': 'sent_at', 'email.delivered': 'delivered_at', 'email.opened': 'opened_at',
              'email.clicked': 'clicked_at', 'email.bounced': 'bounced_at', 'email.failed': 'failed_at'}
    field = fields.get(kind)
    if field and getattr(recipient, field) is None:
        setattr(recipient, field, when)
    if kind == 'email.bounced':
        contact.status = 'bounced'
        contact.bounced_at = contact.bounced_at or when
        Suppression.objects.get_or_create(email=recipient.email, defaults={'contact': contact, 'reason': 'hard_bounce'})
    if kind in ('email.complained', 'email.suppressed'):
        contact.status = 'suppressed'
        Suppression.objects.get_or_create(email=recipient.email, defaults={'contact': contact,
            'reason': 'complaint' if kind == 'email.complained' else 'manual'})
    if kind == 'email.opened' and (not contact.last_email_opened_at or contact.last_email_opened_at < when):
        contact.last_email_opened_at = when
    # Terminal evidence wins regardless of webhook arrival order.
    if recipient.bounced_at:
        recipient.status = 'bounced'
    elif recipient.failed_at:
        recipient.status = 'failed'
    elif kind == 'email.suppressed' or recipient.status == 'suppressed':
        recipient.status = 'suppressed'
    elif recipient.delivered_at:
        recipient.status = 'delivered'
    elif recipient.sent_at:
        recipient.status = 'sent'
    contact.save()
    recipient.save()
    event.campaign_recipient = recipient
    event.processed_at = timezone.now()
    event.save(update_fields=['campaign_recipient', 'processed_at'])
    refresh_counts(recipient.campaign_id)

@api_view(['POST'])
@authentication_classes([])
@permission_classes([AllowAny])
def resend_webhook(request):
    if not settings.RESEND_WEBHOOK_SECRET:
        return Response({'detail': 'Webhook is not configured.'}, status=503)
    try:
        payload = Webhook(settings.RESEND_WEBHOOK_SECRET).verify(request.body, dict(request.headers))
    except (WebhookVerificationError, ValueError, TypeError):
        logger.warning('webhook rejected')
        return Response({'detail': 'Invalid webhook signature.'}, status=400)
    try:
        event_type = payload['type']
        data = payload['data']
        occurred = parse_datetime(payload['created_at'])
        event_id = request.headers['svix-id']
        message_id = data.get('email_id', '')
        if not occurred or timezone.is_naive(occurred) or not isinstance(event_type, str) or not isinstance(message_id, str) or len(event_type) > 100 or len(message_id) > 255 or len(event_id) > 255:
            raise ValueError
    except (KeyError, TypeError, ValueError, AttributeError):
        return Response({'detail': 'Invalid event payload.'}, status=400)
    event, created = EmailEvent.objects.get_or_create(provider='resend', provider_event_id=event_id,
        defaults={'provider_message_id': message_id, 'event_type': event_type, 'payload': payload, 'occurred_at': occurred})
    process_event(event.pk)
    logger.info('webhook received event=%s duplicate=%s', event.pk, not created)
    return Response({'received': True, 'duplicate': not created})

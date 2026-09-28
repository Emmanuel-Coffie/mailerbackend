import csv
import io
import logging
import uuid
from email.utils import formataddr
from html import escape, unescape
import resend
import requests
from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.html import strip_tags
from rest_framework.exceptions import ValidationError
from .models import Campaign, CampaignRecipient, Contact, ContactList, Suppression, Unsubscribe
from .utils import VARIABLES, render_content

logger = logging.getLogger('mailing')

def blocked(email, contact=None):
    try:
        validate_email(email)
    except DjangoValidationError:
        return True
    if contact and contact.status != 'active':
        return True
    query = Q(email=email)
    if contact:
        query |= Q(contact=contact)
    return Suppression.objects.filter(query).exists() or Contact.objects.filter(email=email).exclude(status='active').exists()

def refresh_counts(campaign_id):
    # Call under the campaign row lock when mutating delivery history.
    recipients = CampaignRecipient.objects.filter(campaign_id=campaign_id)
    counts = {'total_recipients': recipients.count()}
    for name in ('sent', 'delivered', 'bounced', 'failed', 'opened', 'clicked'):
        counts[name + '_count'] = recipients.filter(**{name + '_at__isnull': False}).count()
    counts['unsubscribed_count'] = Unsubscribe.objects.filter(campaign_id=campaign_id).count()
    Campaign.objects.filter(pk=campaign_id).update(**counts)
    return counts

def require_draft(campaign):
    if campaign.status != 'draft':
        raise ValidationError('Only draft campaigns may be edited or prepared.')

def freeze_content(campaign):
    if campaign.template:
        for field in ('subject', 'html_content', 'text_content'):
            if not getattr(campaign, field):
                setattr(campaign, field, getattr(campaign.template, field))
    campaign.from_email = campaign.from_email or settings.RESEND_FROM_EMAIL
    campaign.from_name = campaign.from_name or settings.RESEND_FROM_NAME
    campaign.reply_to = campaign.reply_to or settings.RESEND_REPLY_TO
    if not campaign.subject or not (campaign.html_content or campaign.text_content):
        raise ValidationError('A subject and HTML or text content are required.')
    try:
        validate_email(campaign.from_email)
        if campaign.reply_to:
            validate_email(campaign.reply_to)
    except DjangoValidationError:
        raise ValidationError('Configure a valid sender and reply-to address.')
    campaign.save()

@transaction.atomic
def prepare_campaign(campaign_id):
    campaign = Campaign.objects.select_for_update().get(pk=campaign_id)
    require_draft(campaign)
    selected = Contact.objects.filter(contact_lists__in=campaign.contact_lists.all())
    contacts = list(selected.distinct())
    report = {'selected': selected.count(), 'duplicates_removed': selected.count() - len(contacts),
              'unsubscribed_excluded': 0, 'bounced_excluded': 0, 'suppressed_excluded': 0,
              'invalid_excluded': 0, 'eligible': 0}
    eligible_ids = []
    for contact in contacts:
        if contact.status != 'active':
            report[contact.status + '_excluded'] += 1
            continue
        try:
            validate_email(contact.email)
        except DjangoValidationError:
            report['invalid_excluded'] += 1
            continue
        if blocked(contact.email, contact):
            report['suppressed_excluded'] += 1
            continue
        eligible_ids.append(contact.pk)
        CampaignRecipient.objects.get_or_create(campaign=campaign, contact=contact, defaults={
            field: getattr(contact, field) for field in ('email', *VARIABLES)})
    # Draft audience changes must not leave removed recipients queued for delivery.
    campaign.recipients.exclude(contact_id__in=eligible_ids).delete()
    report['eligible'] = len(eligible_ids)
    campaign.total_recipients = len(eligible_ids)
    campaign.save(update_fields=['total_recipients', 'updated_at'])
    return report

def publish_campaign(campaign_id):
    from .tasks import send_campaign
    try:
        send_campaign.delay(campaign_id)
        logger.info('campaign queued id=%s', campaign_id)
    except Exception:
        # Durable queued state is retried by Beat, including a broker outage.
        logger.error('campaign dispatch deferred id=%s', campaign_id)

@transaction.atomic
def queue_campaign(campaign_id):
    campaign = Campaign.objects.select_for_update().get(pk=campaign_id)
    require_draft(campaign)
    freeze_content(campaign)
    prepare_campaign(campaign_id)
    campaign.refresh_from_db()
    if not campaign.total_recipients:
        raise ValidationError('No eligible recipients.')
    campaign.status = 'queued'
    campaign.save(update_fields=['status', 'updated_at'])
    transaction.on_commit(lambda: publish_campaign(campaign_id))
    return campaign

@transaction.atomic
def schedule_campaign(campaign_id, when):
    campaign = Campaign.objects.select_for_update().get(pk=campaign_id)
    require_draft(campaign)
    if when <= timezone.now():
        raise ValidationError('scheduled_at must be in the future.')
    freeze_content(campaign)
    prepare_campaign(campaign_id)
    campaign.status = 'scheduled'
    campaign.scheduled_at = when
    campaign.save(update_fields=['status', 'scheduled_at', 'updated_at'])
    return campaign

@transaction.atomic
def cancel_campaign(campaign_id):
    campaign = Campaign.objects.select_for_update().get(pk=campaign_id)
    if campaign.status in ('completed', 'failed'):
        raise ValidationError('A finished campaign cannot be cancelled.')
    campaign.status = 'cancelled'
    campaign.save(update_fields=['status', 'updated_at'])
    return campaign

def import_contacts(upload, contact_list_id=None):
    if not upload.name.lower().endswith('.csv') or upload.size > settings.CSV_MAX_BYTES:
        raise ValidationError('Upload a CSV within CSV_MAX_BYTES.')
    target = None
    if contact_list_id:
        try:
            target = ContactList.objects.get(pk=int(contact_list_id))
        except (ValueError, TypeError, ContactList.DoesNotExist):
            raise ValidationError('Invalid contact_list_id.')
    try:
        reader = csv.DictReader(io.StringIO(upload.read().decode('utf-8-sig')), strict=True)
        if not reader.fieldnames or 'email' not in reader.fieldnames:
            raise ValidationError('CSV must have an email header.')
        rows = list(reader)
    except (UnicodeDecodeError, csv.Error):
        raise ValidationError('CSV must be valid UTF-8 with valid quoting.')
    counts = dict.fromkeys(('total', 'valid', 'invalid', 'duplicates', 'existing', 'imported'), 0)
    seen = set()
    for row in rows:
        counts['total'] += 1
        values = {field: (row.get(field) or '').strip() for field in ('email', 'first_name', 'last_name', 'company', 'phone', 'position')}
        values['email'] = values['email'].lower()
        candidate = Contact(**values, source='csv')
        try:
            candidate.full_clean(validate_unique=False)
        except DjangoValidationError:
            counts['invalid'] += 1
            continue
        if values['email'] in seen:
            counts['duplicates'] += 1
            continue
        seen.add(values['email'])
        counts['valid'] += 1
        with transaction.atomic():
            contact, created = Contact.objects.get_or_create(email=values.pop('email'), defaults={**values, 'source': 'csv'})
            counts['imported' if created else 'existing'] += 1
            if target:
                target.contacts.add(contact)
    logger.info('CSV import counts=%s', counts)
    return counts

class DeliveryError(Exception):
    def __init__(self, message, temporary=False):
        super().__init__(message)
        self.temporary = temporary

class EmailService:
    """Only provider boundary. One address per message; never expose other recipients."""
    def _guard(self, params):
        if not settings.RESEND_API_KEY:
            raise DeliveryError('Email provider is not configured.')
        for address in params['to']:
            if blocked(address):
                raise DeliveryError('Recipient is not eligible for delivery.')
            if settings.DEBUG and settings.EMAIL_ALLOWED_TEST_RECIPIENTS and address.lower() not in settings.EMAIL_ALLOWED_TEST_RECIPIENTS:
                raise DeliveryError('Recipient is outside the development allowlist.')

    def _call(self, method, params, key):
        resend.api_key = settings.RESEND_API_KEY
        try:
            return method(params, {'idempotency_key': key})
        except requests.RequestException:
            logger.warning('Resend network failure')
            raise DeliveryError('Temporary provider connection failure.', temporary=True) from None
        except resend.exceptions.ResendError as exc:
            code = getattr(exc, 'code', None)
            status = getattr(exc, 'status_code', None)
            temporary = str(status or code) in ('429', '500', '502', '503', '504')
            logger.warning('Resend API failure temporary=%s', temporary)
            raise DeliveryError('Provider temporarily unavailable.' if temporary else 'Provider rejected the email.', temporary) from None

    def send_email(self, params, key):
        self._guard(params)
        return self._call(resend.Emails.send, params, key)

    def send_batch(self, messages, key):
        if not 1 <= len(messages) <= 100:
            raise DeliveryError('Resend batches require 1 to 100 messages.')
        for params in messages:
            self._guard(params)
        return self._call(resend.Batch.send, messages, key)

    def send_test_email(self, campaign, address, key):
        data = {'first_name': 'Test', 'last_name': 'Recipient', 'company': 'Example Company', 'position': 'Administrator'}
        return self.send_email(build_payload(campaign, address, data), key)

def build_payload(campaign, email, data, unsubscribe_url=None):
    content = render_content(campaign.subject, campaign.html_content, campaign.text_content, data)
    if unsubscribe_url:
        if not content['html']:
            content['html'] = '<div style="white-space: pre-wrap">' + escape(content['text']) + '</div>'
        if not content['text']:
            content['text'] = unescape(strip_tags(content['html']))
        content['html'] += '<p>Don\'t want to receive these emails? <a href="' + escape(unsubscribe_url, quote=True) + '">Unsubscribe</a></p>'
        content['text'] += '\n\nUnsubscribe: ' + unsubscribe_url
    payload = {'from': formataddr((campaign.from_name, campaign.from_email)), 'to': [email], **content}
    if campaign.reply_to:
        payload['reply_to'] = campaign.reply_to
    if unsubscribe_url:
        payload['headers'] = {'List-Unsubscribe': '<' + unsubscribe_url + '>', 'List-Unsubscribe-Post': 'List-Unsubscribe=One-Click'}
    return payload

def test_campaign(campaign, address):
    """Resolve defaults in memory only: test delivery never changes campaign history."""
    if campaign.template:
        for field in ('subject', 'html_content', 'text_content'):
            setattr(campaign, field, getattr(campaign, field) or getattr(campaign.template, field))
    campaign.from_email = campaign.from_email or settings.RESEND_FROM_EMAIL
    campaign.from_name = campaign.from_name or settings.RESEND_FROM_NAME
    campaign.reply_to = campaign.reply_to or settings.RESEND_REPLY_TO
    if not campaign.subject or not (campaign.html_content or campaign.text_content) or not campaign.from_email:
        raise ValidationError('Configure campaign content and sender first.')
    return EmailService().send_test_email(campaign, address.lower(), 'test-' + uuid.uuid4().hex)

@transaction.atomic
def unsubscribe_recipient(token):
    recipient = CampaignRecipient.objects.get(unsubscribe_token=token)
    Campaign.objects.select_for_update().get(pk=recipient.campaign_id)
    contact = Contact.objects.select_for_update().get(pk=recipient.contact_id)
    contact.status = 'unsubscribed'
    contact.unsubscribed_at = contact.unsubscribed_at or timezone.now()
    contact.save(update_fields=['status', 'unsubscribed_at', 'updated_at'])
    Suppression.objects.get_or_create(email=recipient.email, defaults={'contact': contact, 'reason': 'unsubscribe'})
    Unsubscribe.objects.get_or_create(campaign_recipient=recipient, defaults={
        'contact': contact, 'campaign_id': recipient.campaign_id, 'token': token})
    refresh_counts(recipient.campaign_id)
    logger.info('unsubscribe recipient=%s', recipient.pk)

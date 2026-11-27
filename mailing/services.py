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

@transaction.atomic
def import_contacts(upload, contact_list_id=None, group_by='auto', preview=False):
    from .imports import read_contacts
    import re
    if group_by not in ('auto', 'group', 'company', 'position', 'sheet', 'none'):
        raise ValidationError('Choose a supported grouping option.')
    target = None
    if contact_list_id:
        try:
            target = ContactList.objects.get(pk=int(contact_list_id))
        except (ValueError, TypeError, ContactList.DoesNotExist):
            raise ValidationError('Invalid contact_list_id.')
    rows, detected = read_contacts(upload)
    counts = dict.fromkeys(('total', 'valid', 'invalid', 'duplicates', 'existing', 'imported'), 0)
    seen, groups, errors = set(), {}, []
    prepared = []
    for index, row in enumerate(rows, 2):
        counts['total'] += 1
        values = {field: row.get(field, '') for field in ('email', 'first_name', 'last_name', 'company', 'phone', 'position')}
        values['email'] = values['email'].lower()
        try:
            Contact(**values, source='spreadsheet').full_clean(validate_unique=False)
        except DjangoValidationError:
            counts['invalid'] += 1
            if len(errors) < 20:
                errors.append({'row': index, 'sheet': row.get('_sheet') or 'CSV', 'message': 'Invalid email or contact field exceeds its length limit.'})
            continue
        duplicate = values['email'] in seen
        if duplicate:
            counts['duplicates'] += 1
        else:
            seen.add(values['email'])
            counts['valid'] += 1
        selected = group_by
        if selected == 'auto':
            selected = 'group' if row.get('group') else 'company' if row.get('company') else 'sheet'
        raw = row.get('_sheet' if selected == 'sheet' else selected, '') if selected != 'none' else ''
        names = [name.strip() for name in re.split(r'[;,|]', raw) if name.strip()] if selected == 'group' else ([raw] if raw else [])
        if any(len(name) > 255 for name in names):
            raise ValidationError('Group names must be 255 characters or fewer.')
        for name in names:
            groups.setdefault(name, set()).add(values['email'])
        if len(groups) > 200:
            raise ValidationError('This import would create more than 200 groups. Choose another grouping option.')
        prepared.append((values, names, duplicate))
    existing = set(Contact.objects.filter(email__in=seen).values_list('email', flat=True))
    counts['existing'] = len(existing)
    counts['imported'] = len(seen - existing)
    if not preview:
        group_objects = {}
        for name in groups:
            group_objects[name] = ContactList.objects.filter(name__iexact=name).order_by('id').first() or ContactList.objects.create(name=name, description='Created from a contact import')
        for values, names, duplicate in prepared:
            contact, _ = Contact.objects.get_or_create(email=values['email'], defaults={**{k: v for k, v in values.items() if k != 'email'}, 'source': 'spreadsheet'})
            if target:
                target.contacts.add(contact)
            for name in names:
                group_objects[name].contacts.add(contact)
    return {**counts, 'preview': preview, 'detected_columns': detected,
            'groups': [{'name': name, 'contacts': len(emails)} for name, emails in groups.items()], 'errors': errors}

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
    import re
    html = campaign.html_content or ''
    text = campaign.text_content or ''
    marker = r'{{\s*unsubscribe_url\s*}}'
    has_html_link = bool(re.search(marker, html))
    has_text_link = bool(re.search(marker, text))
    destination = unsubscribe_url or settings.FRONTEND_URL + '/unsubscribe/preview'
    html = re.sub(marker, lambda _: escape(destination, quote=True), html)
    text = re.sub(marker, lambda _: destination, text)
    content = render_content(campaign.subject, html, text, data)
    if unsubscribe_url:
        if not content['html']:
            content['html'] = '<div style="white-space: pre-wrap">' + escape(content['text']) + '</div>'
        if not content['text']:
            content['text'] = unescape(strip_tags(content['html']))
        if not has_html_link:
            footer = '<p style="text-align:center;font:13px Arial;color:#627175;padding:24px">Don\'t want to receive these emails? <a href="' + escape(unsubscribe_url, quote=True) + '">Unsubscribe</a></p>'
            content['html'] = content['html'].replace('</body>', footer + '</body>') if '</body>' in content['html'] else content['html'] + footer
        if not has_text_link:
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

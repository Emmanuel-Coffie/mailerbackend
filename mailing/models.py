import secrets
from django.db import models, transaction
from django.core.validators import validate_email

def token():
    return secrets.token_urlsafe(32)

class Timestamped(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        abstract = True
        ordering = ['-id']

class Contact(Timestamped):
    STATUS = [(s, s) for s in ('active', 'unsubscribed', 'bounced', 'suppressed')]
    first_name = models.CharField(max_length=150, blank=True)
    last_name = models.CharField(max_length=150, blank=True)
    email = models.EmailField(unique=True)
    company = models.CharField(max_length=255, blank=True, db_index=True)
    phone = models.CharField(max_length=50, blank=True)
    position = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=20, choices=STATUS, default='active', db_index=True)
    source = models.CharField(max_length=255, blank=True)
    notes = models.TextField(blank=True)
    last_email_sent_at = models.DateTimeField(null=True, blank=True)
    last_email_opened_at = models.DateTimeField(null=True, blank=True)
    unsubscribed_at = models.DateTimeField(null=True, blank=True)
    bounced_at = models.DateTimeField(null=True, blank=True)

    def clean(self):
        self.email = self.email.strip().lower()
        validate_email(self.email)

    def save(self, *args, **kwargs):
        self.clean()
        with transaction.atomic():
            super().save(*args, **kwargs)
            # Preserve opt-outs even if the contact is later deleted/reimported
            # or an administrator changes its display status back to active.
            reasons = {'unsubscribed': 'unsubscribe', 'bounced': 'hard_bounce', 'suppressed': 'manual'}
            if self.status in reasons:
                Suppression.objects.get_or_create(email=self.email, defaults={'contact': self, 'reason': reasons[self.status]})

    def __str__(self):
        return self.email

class ContactList(Timestamped):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    contacts = models.ManyToManyField(Contact, related_name='contact_lists', blank=True)
    def __str__(self):
        return self.name

class Suppression(models.Model):
    contact = models.ForeignKey(Contact, null=True, blank=True, on_delete=models.SET_NULL)
    email = models.EmailField(unique=True)
    reason = models.CharField(max_length=20, choices=[(s, s) for s in ('unsubscribe', 'hard_bounce', 'complaint', 'manual', 'invalid')])
    created_at = models.DateTimeField(auto_now_add=True)
    def save(self, *args, **kwargs):
        self.email = self.email.strip().lower()
        validate_email(self.email)
        super().save(*args, **kwargs)

class EmailTemplate(Timestamped):
    name = models.CharField(max_length=255)
    subject = models.CharField(max_length=998)
    html_content = models.TextField(blank=True)
    text_content = models.TextField(blank=True)
    def __str__(self):
        return self.name

class Campaign(Timestamped):
    STATUS = [(s, s) for s in ('draft', 'scheduled', 'queued', 'sending', 'completed', 'cancelled', 'failed')]
    name = models.CharField(max_length=255)
    subject = models.CharField(max_length=998, blank=True)
    html_content = models.TextField(blank=True)
    text_content = models.TextField(blank=True)
    template = models.ForeignKey(EmailTemplate, null=True, blank=True, on_delete=models.SET_NULL)
    contact_lists = models.ManyToManyField(ContactList, blank=True)
    from_name = models.CharField(max_length=255, blank=True)
    from_email = models.EmailField(blank=True)
    reply_to = models.EmailField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS, default='draft', db_index=True)
    scheduled_at = models.DateTimeField(null=True, blank=True, db_index=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    total_recipients = models.PositiveIntegerField(default=0)
    sent_count = models.PositiveIntegerField(default=0)
    delivered_count = models.PositiveIntegerField(default=0)
    bounced_count = models.PositiveIntegerField(default=0)
    failed_count = models.PositiveIntegerField(default=0)
    opened_count = models.PositiveIntegerField(default=0)
    clicked_count = models.PositiveIntegerField(default=0)
    unsubscribed_count = models.PositiveIntegerField(default=0)
    def __str__(self):
        return self.name

class CampaignAttachment(Timestamped):
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name='attachments')
    filename = models.CharField(max_length=255)
    content = models.BinaryField()
    size = models.PositiveIntegerField()

class CampaignRecipient(Timestamped):
    campaign = models.ForeignKey(Campaign, on_delete=models.PROTECT, related_name='recipients')
    contact = models.ForeignKey(Contact, on_delete=models.PROTECT)
    email = models.EmailField()
    first_name = models.CharField(max_length=150, blank=True)
    last_name = models.CharField(max_length=150, blank=True)
    company = models.CharField(max_length=255, blank=True)
    position = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=20, default='pending', db_index=True,
        choices=[(s, s) for s in ('pending', 'queued', 'sent', 'delivered', 'bounced', 'failed', 'suppressed')])
    provider_message_id = models.CharField(max_length=255, null=True, blank=True, unique=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    opened_at = models.DateTimeField(null=True, blank=True)
    clicked_at = models.DateTimeField(null=True, blank=True)
    bounced_at = models.DateTimeField(null=True, blank=True)
    failed_at = models.DateTimeField(null=True, blank=True)
    retry_count = models.PositiveIntegerField(default=0)
    error_message = models.TextField(blank=True)
    # Freeze exact provider request across retries, including after process crashes.
    delivery_payload = models.JSONField(default=dict, blank=True)
    first_attempt_at = models.DateTimeField(null=True, blank=True)
    next_attempt_at = models.DateTimeField(null=True, blank=True)
    unsubscribe_token = models.CharField(max_length=64, unique=True, default=token, editable=False)
    class Meta:
        ordering = ['id']
        constraints = [models.UniqueConstraint(fields=['campaign', 'contact'], name='unique_campaign_contact')]
        indexes = [models.Index(fields=['campaign', 'status'])]

class EmailEvent(models.Model):
    campaign_recipient = models.ForeignKey(CampaignRecipient, null=True, blank=True, on_delete=models.PROTECT)
    provider = models.CharField(max_length=30, default='resend')
    provider_event_id = models.CharField(max_length=255)
    provider_message_id = models.CharField(max_length=255, blank=True, db_index=True)
    event_type = models.CharField(max_length=100)
    payload = models.JSONField()
    occurred_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['provider', 'provider_event_id'], name='unique_provider_event')]

class Unsubscribe(models.Model):
    contact = models.ForeignKey(Contact, on_delete=models.PROTECT)
    campaign = models.ForeignKey(Campaign, on_delete=models.PROTECT)
    campaign_recipient = models.OneToOneField(CampaignRecipient, on_delete=models.PROTECT)
    token = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

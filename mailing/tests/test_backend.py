import base64
import json
from datetime import timedelta
from unittest.mock import patch
import requests
from celery.exceptions import Retry
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient
from resend.exceptions import ResendError
from svix.webhooks import Webhook
from mailing.models import Contact, ContactList, Campaign, CampaignRecipient, Suppression, EmailTemplate, EmailEvent, Unsubscribe
from mailing.services import prepare_campaign, queue_campaign, EmailService, DeliveryError, schedule_campaign
from mailing.tasks import send_campaign, dispatch_due_campaigns
from mailing.utils import render_content

class BackendFixture:
    def setUp(self):
        self.client = APIClient()
        self.staff = User.objects.create_user('admin', password='test-pass', is_staff=True, is_superuser=True)
        self.client.force_authenticate(self.staff)
        self.contact = Contact.objects.create(email='one@example.com', first_name='Ada', company='Original')
        self.list = ContactList.objects.create(name='Customers')
        self.list.contacts.add(self.contact)
        self.campaign = Campaign.objects.create(name='Introduction', subject='Hello {{first_name}}', text_content='Welcome {{company}}')
        self.campaign.contact_lists.add(self.list)

    def endpoint(self, action):
        return f'/api/email/campaigns/{self.campaign.pk}/{action}/'

    def queued(self):
        with self.captureOnCommitCallbacks(execute=True), patch('mailing.tasks.send_campaign.delay'):
            queue_campaign(self.campaign.pk)
        return self.campaign.recipients.get()

class BackendTests(BackendFixture, TestCase):
    def test_unauthenticated_and_nonstaff(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get('/api/email/contacts/').status_code, 401)
        normal = User.objects.create_user('normal', password='pass')
        self.client.force_authenticate(normal)
        self.assertEqual(self.client.post(self.endpoint('send')).status_code, 403)
        self.assertEqual(self.client.get('/api/email/settings/status/').status_code, 403)

    def test_jwt_login_refresh_and_management(self):
        self.client.force_authenticate(None)
        response = self.client.post('/api/auth/token/', {'username': 'admin', 'password': 'test-pass'})
        self.assertEqual(response.status_code, 200)
        self.client.credentials(HTTP_AUTHORIZATION='Bearer ' + response.data['access'])
        self.assertEqual(self.client.get('/api/email/contacts/').status_code, 200)
        self.assertEqual(self.client.post('/api/auth/token/refresh/', {'refresh': response.data['refresh']}).status_code, 200)

    def test_contact_normalization_duplicates_validation(self):
        response = self.client.post('/api/email/contacts/', {'email': '  TWO@EXAMPLE.COM  '})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['email'], 'two@example.com')
        self.assertEqual(self.client.post('/api/email/contacts/', {'email': 'Two@Example.com'}).status_code, 400)
        self.assertEqual(self.client.post('/api/email/contacts/', {'email': 'broken'}).status_code, 400)
        url = f"/api/email/contacts/{response.data['id']}/"
        self.assertEqual(self.client.patch(url, {'company': 'Updated'}).status_code, 200)
        self.assertEqual(self.client.delete(url).status_code, 204)

    def test_search_filters_pagination(self):
        result = self.client.get('/api/email/contacts/', {'search': 'Ada', 'contact_lists': self.list.pk, 'ordering': 'email'})
        self.assertEqual(result.data['count'], 1)
        self.assertEqual(self.client.get('/api/email/contacts/', {'status': 'bounced'}).data['count'], 0)

    def test_list_crud_membership(self):
        response = self.client.post('/api/email/lists/', {'name': 'New'})
        self.assertEqual(response.status_code, 201)
        url = f"/api/email/lists/{response.data['id']}/"
        body = {'contact_ids': [self.contact.pk]}
        self.assertEqual(self.client.post(url + 'add-contacts/', body, format='json').status_code, 200)
        self.assertEqual(ContactList.objects.get(pk=response.data['id']).contacts.count(), 1)
        self.assertEqual(self.client.post(url + 'remove-contacts/', body, format='json').status_code, 200)
        self.assertEqual(ContactList.objects.get(pk=response.data['id']).contacts.count(), 0)
        self.assertEqual(self.client.post(url + 'add-contacts/', {'contact_ids': [999]}, format='json').status_code, 400)
        self.assertEqual(self.client.delete(url).status_code, 204)

    def test_csv_counts_and_membership(self):
        upload = SimpleUploadedFile('contacts.csv', b'email,first_name\none@example.com,Existing\nNEW@example.com,New\nnew@example.com,Duplicate\nbad,Bad\n')
        result = self.client.post('/api/email/contacts/import/', {'file': upload, 'contact_list_id': self.list.pk})
        self.assertEqual(result.status_code, 200)
        self.assertEqual({key: result.data[key] for key in ('total', 'valid', 'invalid', 'duplicates', 'existing', 'imported')}, {'total': 4, 'valid': 2, 'invalid': 1, 'duplicates': 1, 'existing': 1, 'imported': 1})
        self.assertEqual(self.list.contacts.count(), 2)

    @override_settings(CSV_MAX_BYTES=10)
    def test_csv_limits(self):
        for name, body in [('x.txt', b'email\n'), ('x.csv', b'email\na@b.com\n')]:
            self.assertEqual(self.client.post('/api/email/contacts/import/', {'file': SimpleUploadedFile(name, body)}).status_code, 400)

    def test_csv_bad_encoding_and_header(self):
        for body in [b'email\n\xff', b'company\nName', b'email\n"unclosed']:
            self.assertEqual(self.client.post('/api/email/contacts/import/', {'file': SimpleUploadedFile('x.csv', body)}).status_code, 400)

    def test_template_rendering_and_preview(self):
        result = render_content('Hi {{first_name}}', '{{company}} {{missing}} {{position}}', '{{last_name}}', {'first_name': 'Ada', 'company': '<script>'})
        self.assertEqual(result, {'subject': 'Hi Ada', 'html': '&lt;script&gt;  ', 'text': ''})
        response = self.client.post('/api/email/templates/', {'name': 'Welcome', 'subject': 'Hi {{first_name}}', 'text_content': '{{company}}'})
        self.assertEqual(response.status_code, 201)
        url = f"/api/email/templates/{response.data['id']}/"
        self.assertEqual(self.client.post(url + 'preview/', {'first_name': 'Ada'}, format='json').data['subject'], 'Hi Ada')
        self.assertEqual(self.client.delete(url).status_code, 204)

    def test_campaign_create_prepare_dedup_and_exclusions(self):
        self.assertEqual(self.client.post('/api/email/campaigns/', {'name': 'New'}).status_code, 201)
        other = ContactList.objects.create(name='Other')
        other.contacts.add(self.contact)
        self.campaign.contact_lists.add(other)
        for status in ('unsubscribed', 'bounced', 'suppressed'):
            self.list.contacts.add(Contact.objects.create(email=f'{status}@example.com', status=status))
        suppressed = Contact.objects.create(email='blocked@example.com')
        self.list.contacts.add(suppressed)
        Suppression.objects.create(email=suppressed.email, reason='manual')
        invalid = Contact.objects.create(email='valid@example.com')
        Contact.objects.filter(pk=invalid.pk).update(email='broken')
        self.list.contacts.add(invalid)
        result = self.client.post(self.endpoint('prepare'))
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.data, {'selected': 7, 'duplicates_removed': 1, 'unsubscribed_excluded': 1,
            'bounced_excluded': 1, 'suppressed_excluded': 2, 'invalid_excluded': 1, 'eligible': 1})
        self.client.post(self.endpoint('prepare'))
        self.assertEqual(self.campaign.recipients.count(), 1)

    def test_snapshots_and_removed_audience(self):
        prepare_campaign(self.campaign.pk)
        self.contact.company = 'Changed'
        self.contact.save()
        prepare_campaign(self.campaign.pk)
        self.assertEqual(self.campaign.recipients.get().company, 'Original')
        self.list.contacts.clear()
        prepare_campaign(self.campaign.pk)
        self.assertEqual(self.campaign.recipients.count(), 0)

    def test_send_queues_once_and_locks_edits(self):
        with patch('mailing.tasks.send_campaign.delay') as task, self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(self.endpoint('send'))
        self.assertEqual(response.status_code, 202)
        task.assert_called_once_with(self.campaign.pk)
        self.assertEqual(self.client.post(self.endpoint('send')).status_code, 400)
        self.assertEqual(self.client.patch(f'/api/email/campaigns/{self.campaign.pk}/', {'subject': 'changed'}).status_code, 400)

    @override_settings(RESEND_API_KEY='fake-for-tests')
    @patch('resend.Emails.send', return_value={'id': 'message-1'})
    def test_successful_send_and_duplicate_task(self, send):
        recipient = self.queued()
        send_campaign.run(self.campaign.pk)
        send_campaign.run(self.campaign.pk)
        send.assert_called_once()
        payload, options = send.call_args.args
        self.assertEqual(options['idempotency_key'], f'campaign-{self.campaign.pk}-recipient-{recipient.pk}')
        self.assertIn(recipient.unsubscribe_token, payload['html'])
        self.assertIn('Welcome Original', payload['html'])
        self.assertEqual(payload['subject'], 'Hello Ada')
        self.campaign.refresh_from_db()
        self.assertEqual((self.campaign.status, self.campaign.sent_count), ('completed', 1))
        self.assertEqual(self.client.get(self.endpoint('recipients'), {'status': 'sent'}).data['count'], 1)

    @override_settings(RESEND_API_KEY='fake-for-tests')
    @patch('resend.Emails.send')
    def test_temporary_failure_retry_payload_and_success(self, send):
        recipient = self.queued()
        send.side_effect = requests.ConnectionError('secret must not be logged')
        with self.assertRaises(Retry):
            send_campaign.run(self.campaign.pk)
        recipient.refresh_from_db()
        self.assertEqual((recipient.status, recipient.retry_count), ('queued', 1))
        self.assertNotIn('secret', recipient.error_message)
        initial = recipient.delivery_payload
        CampaignRecipient.objects.filter(pk=recipient.pk).update(next_attempt_at=timezone.now() - timedelta(seconds=1))
        send.side_effect = None
        send.return_value = {'id': 'retry-success'}
        send_campaign.run(self.campaign.pk)
        self.assertEqual(send.call_args.args[0], initial)
        recipient.refresh_from_db()
        self.assertEqual(recipient.status, 'sent')

    @override_settings(RESEND_API_KEY='fake-for-tests', EMAIL_RETRY_LIMIT=1)
    @patch('resend.Emails.send', side_effect=ResendError(429, 'rate_limit_exceeded', 'private', ''))
    def test_rate_limit_and_retry_exhaustion(self, send):
        recipient = self.queued()
        with self.assertRaises(Retry):
            send_campaign.run(self.campaign.pk)
        CampaignRecipient.objects.filter(pk=recipient.pk).update(next_attempt_at=timezone.now() - timedelta(seconds=1))
        send_campaign.run(self.campaign.pk)
        recipient.refresh_from_db()
        self.assertEqual(recipient.status, 'failed')
        self.assertEqual(send.call_count, 2)

    @override_settings(RESEND_API_KEY='fake-for-tests')
    @patch('resend.Emails.send', side_effect=ResendError(422, 'validation_error', 'private', ''))
    def test_permanent_failure(self, send):
        recipient = self.queued()
        send_campaign.run(self.campaign.pk)
        recipient.refresh_from_db()
        self.assertEqual((recipient.status, recipient.retry_count), ('failed', 0))
        self.campaign.refresh_from_db()
        self.assertEqual(self.campaign.status, 'failed')

    @patch('resend.Emails.send')
    def test_expired_idempotency_window(self, send):
        recipient = self.queued()
        CampaignRecipient.objects.filter(pk=recipient.pk).update(delivery_payload={'to': [recipient.email]}, first_attempt_at=timezone.now() - timedelta(days=2))
        send_campaign.run(self.campaign.pk)
        send.assert_not_called()
        recipient.refresh_from_db()
        self.assertEqual(recipient.status, 'failed')

    @patch('resend.Emails.send')
    def test_unsubscribe_after_prepare_repeat_and_future_exclusion(self, send):
        recipient = self.queued()
        url = f'/api/email/unsubscribe/{recipient.unsubscribe_token}/'
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertEqual(self.client.post(url).status_code, 200)
        self.assertEqual(Unsubscribe.objects.count(), 1)
        self.assertEqual(Suppression.objects.count(), 1)
        self.campaign.refresh_from_db()
        self.assertEqual(self.campaign.unsubscribed_count, 1)
        send_campaign.run(self.campaign.pk)
        send.assert_not_called()
        future = Campaign.objects.create(name='Future')
        future.contact_lists.add(self.list)
        self.assertEqual(prepare_campaign(future.pk)['eligible'], 0)
        self.assertEqual(self.client.get('/api/email/unsubscribe/invalid/').status_code, 404)

    @patch('resend.Emails.send')
    def test_cancellation(self, send):
        self.queued()
        self.assertEqual(self.client.post(self.endpoint('cancel')).status_code, 200)
        send_campaign.run(self.campaign.pk)
        send.assert_not_called()

    def test_schedule_due_once_and_future(self):
        future = timezone.now() + timedelta(hours=1)
        response = self.client.post(self.endpoint('schedule'), {'scheduled_at': future.isoformat()})
        self.assertEqual(response.status_code, 200)
        with patch('mailing.tasks.send_campaign.delay') as task, self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(dispatch_due_campaigns.run(), 0)
            Campaign.objects.filter(pk=self.campaign.pk).update(scheduled_at=timezone.now() - timedelta(seconds=1))
            self.assertEqual(dispatch_due_campaigns.run(), 1)
            self.assertEqual(dispatch_due_campaigns.run(), 0)
        task.assert_called_once()

    def test_schedule_past_rejected(self):
        self.assertEqual(self.client.post(self.endpoint('schedule'), {'scheduled_at': (timezone.now() - timedelta(hours=1)).isoformat()}).status_code, 400)

    @override_settings(RESEND_API_KEY='fake-for-tests')
    @patch('resend.Emails.send', return_value={'id': 'test-only'})
    def test_test_email_does_not_change_history(self, send):
        result = self.client.post(self.endpoint('test'), {'email': 'test@example.com'})
        self.assertEqual(result.data, {'id': 'test-only'})
        self.assertEqual(CampaignRecipient.objects.count(), 0)
        self.campaign.refresh_from_db()
        self.assertEqual(self.campaign.sent_count, 0)
        self.assertEqual(send.call_args.args[0]['subject'], 'Hello Test')

    @override_settings(DEBUG=True, RESEND_API_KEY='fake-for-tests', EMAIL_ALLOWED_TEST_RECIPIENTS={'allowed@example.com'})
    @patch('resend.Emails.send')
    def test_development_allowlist(self, send):
        self.assertEqual(self.client.post(self.endpoint('test'), {'email': 'other@example.com'}).status_code, 400)
        send.assert_not_called()

    @override_settings(RESEND_API_KEY='fake-for-tests')
    @patch('resend.Batch.send', return_value={'data': [{'id': 'batch-one'}]})
    def test_batch_service(self, send):
        payload = {'to': ['one@example.com'], 'subject': 'Hi', 'text': 'Hi', 'from': 'sender@example.com'}
        self.assertEqual(EmailService().send_batch([payload], 'batch-key')['data'][0]['id'], 'batch-one')
        send.assert_called_once_with([payload], {'idempotency_key': 'batch-key'})
        with self.assertRaises(DeliveryError):
            EmailService().send_batch([payload] * 101, 'large')

    def test_dashboard_analytics_settings_and_admin(self):
        self.assertEqual(self.client.get('/api/email/dashboard/').data['total_contacts'], 1)
        self.assertIsNone(self.client.get(self.endpoint('analytics')).data['open_rate'])
        self.assertNotIn('RESEND_API_KEY', self.client.get('/api/email/settings/status/').data)
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get('/admin/').status_code, 200)
        for model in ['contact', 'contactlist', 'suppression', 'emailtemplate', 'campaign', 'campaignrecipient', 'emailevent', 'unsubscribe']:
            self.assertEqual(self.client.get('/admin/mailing/' + model + '/').status_code, 200)

    def test_task_discovery(self):
        from bulkmailer.celery import app
        app.autodiscover_tasks(force=True)
        self.assertIn('mailing.tasks.send_campaign', app.tasks)
        self.assertIn('mailing.tasks.dispatch_due_campaigns', app.tasks)

    def test_broker_failure_recovers_from_durable_queue(self):
        with patch('mailing.tasks.send_campaign.delay', side_effect=RuntimeError('broker unavailable')), self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(self.endpoint('send'))
        self.assertEqual(response.status_code, 202)
        self.campaign.refresh_from_db()
        self.assertEqual(self.campaign.status, 'queued')
        Campaign.objects.filter(pk=self.campaign.pk).update(updated_at=timezone.now() - timedelta(minutes=6))
        with patch('mailing.tasks.send_campaign.delay') as task, self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(dispatch_due_campaigns.run(), 1)
            self.assertEqual(dispatch_due_campaigns.run(), 0)
        task.assert_called_once()

    @override_settings(RESEND_API_KEY='fake-for-tests')
    @patch('resend.Emails.send')
    def test_suppression_added_between_prepare_and_send(self, send):
        recipient = self.queued()
        Suppression.objects.create(email=self.contact.email, reason='manual')
        send_campaign.run(self.campaign.pk)
        recipient.refresh_from_db()
        self.assertEqual(recipient.status, 'suppressed')
        send.assert_not_called()

    def test_inactive_contact_delete_reimport_stays_suppressed(self):
        self.contact.status = 'unsubscribed'
        self.contact.save()
        email = self.contact.email
        self.contact.delete()
        recreated = Contact.objects.create(email=email)
        self.list.contacts.add(recreated)
        self.assertEqual(prepare_campaign(self.campaign.pk)['eligible'], 0)

    @override_settings(RESEND_API_KEY='fake-for-tests')
    @patch('resend.Emails.send', return_value={'id': 'admin-test'})
    def test_admin_csv_and_test_email_forms(self, send):
        self.client.force_login(self.staff)
        url = '/admin/mailing/contact/import-csv/'
        self.assertEqual(self.client.get(url).status_code, 200)
        response = self.client.post(url, {'file': SimpleUploadedFile('data.csv', b'email\nadmin-import@example.com\n')})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Contact.objects.filter(email='admin-import@example.com').exists())
        url = f'/admin/mailing/campaign/{self.campaign.pk}/test-email/'
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertEqual(self.client.post(url, {'email': 'admin-test@example.com'}).status_code, 302)
        send.assert_called_once()
        self.assertEqual(self.campaign.recipients.count(), 0)

    def test_template_copied_at_queue_and_protected_history(self):
        template = EmailTemplate.objects.create(name='Reusable', subject='Template subject', text_content='Content')
        self.campaign.subject = ''
        self.campaign.text_content = ''
        self.campaign.template = template
        self.campaign.save()
        self.queued()
        template.subject = 'Later edit'
        template.save()
        self.campaign.refresh_from_db()
        self.assertEqual(self.campaign.subject, 'Template subject')
        self.assertEqual(self.client.delete(f'/api/email/contacts/{self.contact.pk}/').status_code, 400)

    @override_settings(RESEND_API_KEY='fake-for-tests', DEBUG=False, EMAIL_ALLOWED_TEST_RECIPIENTS={'only@example.com'})
    @patch('resend.Emails.send', return_value={'id': 'production-test'})
    def test_allowlist_disabled_in_production(self, send):
        self.assertEqual(self.client.post(self.endpoint('test'), {'email': 'another@example.com'}).status_code, 200)
        send.assert_called_once()

    @override_settings(RESEND_API_KEY='fake-for-tests')
    @patch('resend.Emails.send', return_value={'id': 'html-only'})
    def test_html_only_campaign_has_useful_text_alternative(self, send):
        self.campaign.html_content = '<p>Hello {{first_name}}</p>'
        self.campaign.text_content = ''
        self.campaign.save()
        self.queued()
        send_campaign.run(self.campaign.pk)
        self.assertIn('Hello Ada', send.call_args.args[0]['text'])

WEBHOOK_SECRET = 'whsec_' + base64.b64encode(b'isolated-webhook-signing-secret-32').decode()

@override_settings(RESEND_WEBHOOK_SECRET=WEBHOOK_SECRET)
class WebhookTests(BackendFixture, TestCase):
    def webhook(self, kind, event_id='event-1', message_id='message-1'):
        payload = json.dumps({'type': kind, 'created_at': timezone.now().isoformat(), 'data': {'email_id': message_id}})
        now = timezone.now()
        signature = Webhook(WEBHOOK_SECRET).sign(event_id, now, payload)
        return self.client.post('/api/email/webhooks/resend/', data=payload, content_type='application/json',
            HTTP_SVIX_ID=event_id, HTTP_SVIX_TIMESTAMP=str(int(now.timestamp())), HTTP_SVIX_SIGNATURE=signature)

    def sent_recipient(self):
        recipient = self.queued()
        recipient.provider_message_id = 'message-1'
        recipient.status = 'sent'
        recipient.sent_at = timezone.now()
        recipient.save()
        return recipient

    def test_valid_delivery_and_duplicate(self):
        recipient = self.sent_recipient()
        self.client.force_authenticate(None)
        self.assertEqual(self.webhook('email.delivered').status_code, 200)
        self.assertTrue(self.webhook('email.delivered').data['duplicate'])
        self.webhook('email.delivered', 'another-delivery')
        recipient.refresh_from_db()
        self.campaign.refresh_from_db()
        self.assertEqual(recipient.status, 'delivered')
        self.assertEqual(self.campaign.delivered_count, 1)
        self.assertEqual(EmailEvent.objects.count(), 2)

    def test_invalid_signature(self):
        self.assertEqual(self.client.post('/api/email/webhooks/resend/', {}, format='json').status_code, 400)
        self.assertEqual(EmailEvent.objects.count(), 0)

    def test_bounce_then_late_delivery(self):
        recipient = self.sent_recipient()
        self.webhook('email.bounced')
        self.webhook('email.delivered', 'late')
        self.contact.refresh_from_db()
        recipient.refresh_from_db()
        self.assertEqual(self.contact.status, 'bounced')
        self.assertEqual(recipient.status, 'bounced')
        self.assertTrue(Suppression.objects.filter(reason='hard_bounce').exists())

    def test_complaint(self):
        self.sent_recipient()
        self.webhook('email.complained')
        self.contact.refresh_from_db()
        self.assertEqual(self.contact.status, 'suppressed')
        self.assertTrue(Suppression.objects.filter(reason='complaint').exists())

    def test_open_click_unique_recipient_counts(self):
        recipient = self.sent_recipient()
        for kind in ('email.opened', 'email.clicked'):
            self.webhook(kind, kind + '-1')
            self.webhook(kind, kind + '-2')
        recipient.refresh_from_db()
        self.campaign.refresh_from_db()
        self.contact.refresh_from_db()
        self.assertIsNotNone(recipient.opened_at)
        self.assertIsNotNone(self.contact.last_email_opened_at)
        self.assertEqual((self.campaign.opened_count, self.campaign.clicked_count), (1, 1))

    def test_failure_and_suppressed_events(self):
        recipient = self.sent_recipient()
        self.webhook('email.failed')
        recipient.refresh_from_db()
        self.assertEqual(recipient.status, 'failed')
        self.webhook('email.suppressed', 'suppressed')
        self.assertTrue(Suppression.objects.filter(email=recipient.email).exists())

    @override_settings(RESEND_API_KEY='fake-for-tests')
    @patch('resend.Emails.send', return_value={'id': 'message-1'})
    def test_webhook_before_send_commit_is_reconciled(self, send):
        self.queued()
        self.webhook('email.delivered')
        self.assertIsNone(EmailEvent.objects.get().processed_at)
        send_campaign.run(self.campaign.pk)
        self.assertIsNotNone(EmailEvent.objects.get().processed_at)
        self.assertEqual(self.campaign.recipients.get().status, 'delivered')

    def test_unmatched_valid_event_saved(self):
        self.assertEqual(self.webhook('email.delivered', message_id='unknown').status_code, 200)
        self.assertEqual(EmailEvent.objects.count(), 1)

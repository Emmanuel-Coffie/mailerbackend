import io
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from openpyxl import Workbook
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient
from mailing.models import Contact, ContactList, Campaign, CampaignRecipient, Suppression
from mailing.services import import_contacts, build_payload


def workbook(sheets):
    book = Workbook()
    book.remove(book.active)
    for name, rows in sheets.items():
        sheet = book.create_sheet(name)
        for row in rows:
            sheet.append(row)
    stream = io.BytesIO()
    book.save(stream)
    return SimpleUploadedFile('contacts.xlsx', stream.getvalue())


class SpreadsheetTests(TestCase):
    def test_preview_detects_headers_and_groups_without_writing(self):
        result = import_contacts(workbook({'Partners': [
            ['E-mail Address', 'Full Name', 'Company', 'Segment'],
            ['ADA@example.com', 'Ada Lovelace', 'Example', 'Partners;Newsletter'],
        ]}), preview=True)
        self.assertEqual(result['valid'], 1)
        self.assertEqual({g['name'] for g in result['groups']}, {'Partners', 'Newsletter'})
        self.assertEqual(Contact.objects.count(), 0)
        self.assertEqual(ContactList.objects.count(), 0)

    def test_workbook_import_keeps_optouts_and_merges_duplicate_memberships(self):
        contact = Contact.objects.create(email='ada@example.com', first_name='Original', status='unsubscribed')
        result = import_contacts(workbook({'Audience': [
            ['Email', 'Full Name', 'Groups'],
            ['ADA@example.com', 'Changed Name', 'Partners'],
            ['ada@example.com', 'Changed Again', 'Newsletter'],
            ['sam@example.com', 'Sam Taylor', 'Partners'],
            ['invalid', 'Bad Address', 'Partners'],
        ]}))
        self.assertEqual((result['imported'], result['existing'], result['duplicates'], result['invalid']), (1, 1, 1, 1))
        contact.refresh_from_db()
        self.assertEqual((contact.status, contact.first_name), ('unsubscribed', 'Original'))
        self.assertTrue(Suppression.objects.filter(email=contact.email).exists())
        self.assertEqual(contact.contact_lists.count(), 2)
        self.assertEqual(Contact.objects.get(email='sam@example.com').last_name, 'Taylor')

    def test_sheet_and_company_fallback_and_idempotent_retry(self):
        sheets = {'Partners': [['Email', 'Company'], ['a@example.com', 'Acme']],
                  'Customers': [['Email'], ['b@example.com']]}
        import_contacts(workbook(sheets))
        result = import_contacts(workbook(sheets))
        self.assertEqual(result['imported'], 0)
        self.assertEqual(ContactList.objects.count(), 2)
        self.assertEqual(set(ContactList.objects.values_list('name', flat=True)), {'Acme', 'Customers'})

    def test_semicolon_csv_and_no_group_option(self):
        result = import_contacts(SimpleUploadedFile('contacts.csv', b'Email Address;First Name;Company\na@example.com;Ada;Acme\n'), group_by='none')
        self.assertEqual(result['imported'], 1)
        self.assertEqual(ContactList.objects.count(), 0)

    def test_invalid_file_and_ambiguous_columns_do_not_write(self):
        for upload in [SimpleUploadedFile('bad.xlsx', b'not a workbook'),
                       SimpleUploadedFile('bad.csv', b'email,email address\na@example.com,b@example.com')]:
            with self.assertRaises(ValidationError):
                import_contacts(upload)
        self.assertEqual(Contact.objects.count(), 0)

    def test_invalid_later_sheet_rolls_back_whole_import(self):
        with self.assertRaises(ValidationError):
            import_contacts(workbook({'Valid': [['Email'], ['a@example.com']], 'Invalid': [['Company'], ['Acme']]}))
        self.assertEqual(Contact.objects.count(), 0)


class UnsubscribeDeliveryTests(TestCase):
    def setUp(self):
        self.contact = Contact.objects.create(email='recipient@example.com')
        self.campaign = Campaign.objects.create(name='Test', subject='Hello', from_email='sender@example.com', from_name='GreenHaul',
            html_content='<html><body><a href="{{ unsubscribe_url }}">Unsubscribe</a></body></html>',
            text_content='Unsubscribe: {{unsubscribe_url}}')
        self.recipient = CampaignRecipient.objects.create(campaign=self.campaign, contact=self.contact, email=self.contact.email)
        self.url = f'/api/email/unsubscribe/{self.recipient.unsubscribe_token}/'

    def test_placeholder_resolves_and_no_duplicate_footer(self):
        url = 'https://api.example.com' + self.url
        payload = build_payload(self.campaign, self.contact.email, {}, url)
        self.assertNotIn('{{', payload['html'])
        self.assertEqual(payload['html'].count('Unsubscribe'), 1)
        self.assertIn(url, payload['html'])
        self.assertEqual(payload['headers']['List-Unsubscribe'], '<' + url + '>')

    @override_settings(FRONTEND_URL='https://mail.example.com')
    def test_browser_opens_designed_page_and_post_saves_preference(self):
        client = APIClient()
        response = client.get(self.url, HTTP_ACCEPT='text/html')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, 'https://mail.example.com/unsubscribe/' + self.recipient.unsubscribe_token)
        self.contact.refresh_from_db()
        self.assertEqual(self.contact.status, 'active')
        self.assertEqual(client.post(self.url).status_code, 200)
        self.assertEqual(client.post(self.url).status_code, 200)
        self.contact.refresh_from_db()
        self.assertEqual(self.contact.status, 'unsubscribed')

    def test_test_email_has_explained_preview_link(self):
        payload = build_payload(self.campaign, self.contact.email, {})
        self.assertIn('/unsubscribe/preview', payload['html'])
        self.assertNotIn('headers', payload)

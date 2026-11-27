import base64
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework.test import APIClient
from mailing.models import Campaign, CampaignAttachment
from mailing.services import build_payload

class AttachmentTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(User.objects.create_user('attachments', is_staff=True))
        self.campaign = Campaign.objects.create(name='Proposal', from_email='sender@example.com', subject='Proposal', text_content='Please see attached.')
        self.url = f'/api/email/campaigns/{self.campaign.pk}/attachments/'

    def test_upload_list_delivery_and_remove(self):
        response = self.client.post(self.url, {'file': SimpleUploadedFile('proposal.pdf', b'%PDF-test')}, format='multipart')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('content', response.data[0])
        self.assertEqual(self.client.get(self.url).data[0]['filename'], 'proposal.pdf')
        payload = build_payload(self.campaign, 'recipient@example.com', {})
        self.assertEqual(base64.b64decode(payload['attachments'][0]['content']), b'%PDF-test')
        self.assertEqual(self.client.delete(self.url + str(response.data[0]['id']) + '/').status_code, 204)
        self.assertEqual(CampaignAttachment.objects.count(), 0)

    def test_sent_campaign_and_anonymous_changes_are_rejected(self):
        self.campaign.status = 'queued'; self.campaign.save()
        self.assertEqual(self.client.post(self.url, {'file': SimpleUploadedFile('brief.txt', b'data')}).status_code, 400)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(self.url).status_code, 401)

    def test_size_limit_and_cross_campaign_delete(self):
        self.assertEqual(self.client.post(self.url, {'file': SimpleUploadedFile('large.pdf', b'a' * (3 * 1024 * 1024 + 1))}).status_code, 400)
        other = Campaign.objects.create(name='Other')
        attachment = CampaignAttachment.objects.create(campaign=other, filename='private.txt', content=b'private', size=7)
        self.assertEqual(self.client.delete(self.url + str(attachment.pk) + '/').status_code, 404)
        self.assertTrue(CampaignAttachment.objects.filter(pk=attachment.pk).exists())

    def test_count_limit(self):
        for i in range(5):
            CampaignAttachment.objects.create(campaign=self.campaign, filename=f'{i}.txt', content=b'a', size=1)
        self.assertEqual(self.client.post(self.url, {'file': SimpleUploadedFile('extra.txt', b'a')}).status_code, 400)

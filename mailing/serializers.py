from rest_framework import serializers
from .models import Contact, ContactList, EmailTemplate, Campaign, CampaignRecipient

class ContactSerializer(serializers.ModelSerializer):
    email = serializers.EmailField()
    class Meta:
        model = Contact
        fields = '__all__'
        read_only_fields = ['created_at', 'updated_at', 'last_email_sent_at', 'last_email_opened_at', 'unsubscribed_at', 'bounced_at']

    def validate_email(self, value):
        value = value.strip().lower()
        existing = Contact.objects.filter(email=value)
        if self.instance:
            existing = existing.exclude(pk=self.instance.pk)
        if existing.exists():
            raise serializers.ValidationError('A contact with this email already exists.')
        return value

class ContactListSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContactList
        fields = '__all__'

class EmailTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmailTemplate
        fields = '__all__'

class CampaignSerializer(serializers.ModelSerializer):
    class Meta:
        model = Campaign
        fields = '__all__'
        read_only_fields = ['status', 'scheduled_at', 'started_at', 'completed_at', 'total_recipients',
            'sent_count', 'delivered_count', 'bounced_count', 'failed_count', 'opened_count',
            'clicked_count', 'unsubscribed_count', 'created_at', 'updated_at']

    def validate(self, attrs):
        for field in ('subject', 'from_name'):
            if '\n' in attrs.get(field, '') or '\r' in attrs.get(field, ''):
                raise serializers.ValidationError({field: 'Line breaks are not allowed.'})
        return attrs

class RecipientSerializer(serializers.ModelSerializer):
    class Meta:
        model = CampaignRecipient
        exclude = ['delivery_payload', 'unsubscribe_token']

class ContactIDsSerializer(serializers.Serializer):
    contact_ids = serializers.PrimaryKeyRelatedField(queryset=Contact.objects.all(), many=True, allow_empty=False)

class ScheduleSerializer(serializers.Serializer):
    scheduled_at = serializers.DateTimeField()

class TestEmailSerializer(serializers.Serializer):
    email = serializers.EmailField()

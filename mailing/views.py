from django.conf import settings
from django.db import transaction, IntegrityError
from django.db.models import Q, Sum
from django.db.models.deletion import ProtectedError
from django.shortcuts import get_object_or_404
from rest_framework import viewsets
from rest_framework.decorators import action, api_view, authentication_classes, permission_classes
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from .models import Contact, ContactList, Campaign, EmailTemplate, CampaignRecipient
from .serializers import (ContactSerializer, ContactListSerializer, CampaignSerializer, EmailTemplateSerializer,
                          RecipientSerializer, ContactIDsSerializer, ScheduleSerializer, TestEmailSerializer)
from .services import (prepare_campaign, queue_campaign, schedule_campaign, cancel_campaign, import_contacts,
                       require_draft, unsubscribe_recipient, test_campaign, DeliveryError)
from .utils import render_content

class SafeDestroyMixin:
    def perform_destroy(self, instance):
        try:
            instance.delete()
        except ProtectedError:
            raise ValidationError('This record has delivery history and cannot be deleted.')

class ContactViewSet(SafeDestroyMixin, viewsets.ModelViewSet):
    queryset = Contact.objects.all()
    serializer_class = ContactSerializer
    search_fields = ['first_name', 'last_name', 'email', 'company', 'position']
    filterset_fields = ['status', 'company', 'contact_lists']
    ordering_fields = ['email', 'company', 'created_at', 'first_name', 'last_name']

    def perform_create(self, serializer):
        try:
            with transaction.atomic():
                serializer.save()
        except IntegrityError:
            raise ValidationError({'email': 'A contact with this email already exists.'})

    perform_update = perform_create

    @action(detail=False, methods=['post'], url_path='import')
    def import_csv(self, request):
        upload = request.FILES.get('file')
        if not upload:
            raise ValidationError('Provide a CSV in the file field (multipart/form-data).')
        return Response(import_contacts(upload, request.data.get('contact_list_id'), request.data.get('group_by', 'auto'), request.data.get('preview') == 'true'))

class ContactListViewSet(SafeDestroyMixin, viewsets.ModelViewSet):
    queryset = ContactList.objects.all()
    serializer_class = ContactListSerializer
    search_fields = ['name']

    def change_contacts(self, request, add):
        serializer = ContactIDsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        target = self.get_object()
        method = target.contacts.add if add else target.contacts.remove
        method(*serializer.validated_data['contact_ids'])
        return Response(self.get_serializer(target).data)

    @action(detail=True, methods=['post'], url_path='add-contacts')
    def add_contacts(self, request, pk=None):
        return self.change_contacts(request, True)

    @action(detail=True, methods=['post'], url_path='remove-contacts')
    def remove_contacts(self, request, pk=None):
        return self.change_contacts(request, False)

class EmailTemplateViewSet(SafeDestroyMixin, viewsets.ModelViewSet):
    queryset = EmailTemplate.objects.all()
    serializer_class = EmailTemplateSerializer
    search_fields = ['name', 'subject']

    @action(detail=True, methods=['post'])
    def preview(self, request, pk=None):
        template = self.get_object()
        if not isinstance(request.data, dict):
            raise ValidationError('Provide a JSON object of sample variables.')
        return Response(render_content(template.subject, template.html_content, template.text_content, request.data))

class CampaignViewSet(SafeDestroyMixin, viewsets.ModelViewSet):
    queryset = Campaign.objects.all()
    serializer_class = CampaignSerializer
    search_fields = ['name', 'subject']
    filterset_fields = ['status']
    ordering_fields = ['created_at', 'scheduled_at', 'name']

    def filter_queryset(self, queryset):
        # Recipient filters belong to the nested recipient collection.
        if self.action == 'recipients':
            return queryset
        return super().filter_queryset(queryset)

    @transaction.atomic
    def update(self, request, *args, **kwargs):
        campaign = Campaign.objects.select_for_update().get(pk=self.get_object().pk)
        require_draft(campaign)
        return super().update(request, *args, **kwargs)

    @transaction.atomic
    def destroy(self, request, *args, **kwargs):
        campaign = Campaign.objects.select_for_update().get(pk=self.get_object().pk)
        require_draft(campaign)
        campaign.recipients.all().delete()
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=['post'])
    def prepare(self, request, pk=None):
        return Response(prepare_campaign(self.get_object().pk))

    @action(detail=True, methods=['post'])
    def send(self, request, pk=None):
        campaign = queue_campaign(self.get_object().pk)
        return Response({'campaign_id': campaign.pk, 'status': campaign.status, 'recipients': campaign.total_recipients}, status=202)

    @action(detail=True, methods=['post'])
    def schedule(self, request, pk=None):
        serializer = ScheduleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        campaign = schedule_campaign(self.get_object().pk, serializer.validated_data['scheduled_at'])
        return Response(self.get_serializer(campaign).data)

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        return Response(self.get_serializer(cancel_campaign(self.get_object().pk)).data)

    @action(detail=True, methods=['post'])
    def test(self, request, pk=None):
        serializer = TestEmailSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        campaign = self.get_object()
        try:
            result = test_campaign(campaign, serializer.validated_data['email'])
        except DeliveryError as exc:
            return Response({'detail': str(exc)}, status=503 if exc.temporary else 400)
        return Response(result)

    @action(detail=True)
    def recipients(self, request, pk=None):
        recipients = self.get_object().recipients.all()
        for field in ('status', 'email', 'company'):
            if request.query_params.get(field):
                recipients = recipients.filter(**{field: request.query_params[field]})
        if request.query_params.get('search'):
            term = request.query_params['search']
            recipients = recipients.filter(Q(email__icontains=term) | Q(company__icontains=term) | Q(first_name__icontains=term) | Q(last_name__icontains=term))
        return self.get_paginated_response(RecipientSerializer(self.paginate_queryset(recipients), many=True).data)

    @action(detail=True)
    def analytics(self, request, pk=None):
        campaign = self.get_object()
        result = {name: getattr(campaign, name + '_count') for name in ('sent', 'delivered', 'bounced', 'failed', 'opened', 'clicked', 'unsubscribed')}
        result['total'] = campaign.total_recipients
        for rate, numerator, denominator in [('delivery', 'delivered', 'sent'), ('bounce', 'bounced', 'sent'),
            ('open', 'opened', 'delivered'), ('click', 'clicked', 'delivered'), ('unsubscribe', 'unsubscribed', 'sent')]:
            result[rate + '_rate'] = round(result[numerator] / result[denominator] * 100, 2) if result[denominator] else None
        return Response(result)

@api_view(['GET'])
def dashboard(request):
    result = {'total_contacts': Contact.objects.count(), 'total_campaigns': Campaign.objects.count()}
    for status in ('active', 'unsubscribed', 'bounced', 'suppressed'):
        result[status + '_contacts'] = Contact.objects.filter(status=status).count()
    for status in ('draft', 'scheduled', 'completed'):
        result[status + '_campaigns'] = Campaign.objects.filter(status=status).count()
    for name in ('sent', 'delivered', 'bounced', 'failed'):
        result['total_' + name] = Campaign.objects.aggregate(value=Sum(name + '_count'))['value'] or 0
    result['recent_campaigns'] = CampaignSerializer(Campaign.objects.all()[:5], many=True).data
    return Response(result)

@api_view(['GET'])
def settings_status(request):
    return Response({'provider': 'resend', 'api_configured': bool(settings.RESEND_API_KEY),
        'from_email_configured': bool(settings.RESEND_FROM_EMAIL), 'reply_to_configured': bool(settings.RESEND_REPLY_TO),
        'webhook_secret_configured': bool(settings.RESEND_WEBHOOK_SECRET)})

@api_view(['GET', 'POST'])
@authentication_classes([])
@permission_classes([AllowAny])
def unsubscribe(request, token):
    get_object_or_404(CampaignRecipient, unsubscribe_token=token)
    if request.method == 'GET' and 'text/html' in request.META.get('HTTP_ACCEPT', ''):
        from django.shortcuts import redirect
        from urllib.parse import quote
        return redirect(settings.FRONTEND_URL + '/unsubscribe/' + quote(token, safe=''))
    unsubscribe_recipient(token)
    return Response({'detail': 'You have been unsubscribed. You will receive no further marketing emails.'})

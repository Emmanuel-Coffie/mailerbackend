from django.contrib import admin, messages
from django import forms
from django.urls import path
from django.shortcuts import redirect, get_object_or_404
from django.template.response import TemplateResponse
from django.db import transaction
from rest_framework.exceptions import ValidationError
from .models import Contact, ContactList, Suppression, EmailTemplate, Campaign, CampaignRecipient, EmailEvent, Unsubscribe
from .services import prepare_campaign, queue_campaign, cancel_campaign, schedule_campaign, import_contacts, test_campaign, DeliveryError

class CSVImportForm(forms.Form):
    file = forms.FileField()
    contact_list = forms.ModelChoiceField(ContactList.objects.all(), required=False)

class TestEmailForm(forms.Form):
    email = forms.EmailField()

@admin.register(Contact)
class ContactAdmin(admin.ModelAdmin):
    change_list_template = 'admin/mailing/contact_list.html'
    list_display = ['email', 'first_name', 'last_name', 'company', 'status']
    search_fields = ['email', 'first_name', 'last_name', 'company']
    list_filter = ['status', 'contact_lists']
    readonly_fields = ['created_at', 'updated_at', 'last_email_sent_at', 'last_email_opened_at', 'unsubscribed_at', 'bounced_at']

    def get_urls(self):
        return [path('import-csv/', self.admin_site.admin_view(self.import_csv), name='mailing_contact_import')] + super().get_urls()

    def import_csv(self, request):
        if not self.has_add_permission(request):
            from django.core.exceptions import PermissionDenied
            raise PermissionDenied
        form = CSVImportForm(request.POST or None, request.FILES or None)
        if request.method == 'POST' and form.is_valid():
            try:
                target = form.cleaned_data['contact_list']
                result = import_contacts(form.cleaned_data['file'], target.pk if target else None)
                self.message_user(request, str(result))
                return redirect('admin:mailing_contact_changelist')
            except ValidationError as exc:
                form.add_error(None, str(exc.detail))
        return TemplateResponse(request, 'admin/mailing/form.html', {
            **self.admin_site.each_context(request), 'title': 'Import contacts from CSV', 'form': form, 'opts': self.model._meta})

@admin.register(ContactList)
class ContactListAdmin(admin.ModelAdmin):
    list_display = ['name', 'created_at']
    search_fields = ['name']
    filter_horizontal = ['contacts']

@admin.register(Suppression)
class SuppressionAdmin(admin.ModelAdmin):
    list_display = ['email', 'reason', 'created_at']
    search_fields = ['email']
    list_filter = ['reason']
    readonly_fields = ['created_at']

@admin.register(EmailTemplate)
class TemplateAdmin(admin.ModelAdmin):
    list_display = ['name', 'subject', 'updated_at']
    search_fields = ['name', 'subject']

@admin.register(Campaign)
class CampaignAdmin(admin.ModelAdmin):
    change_form_template = 'admin/mailing/campaign_form.html'
    list_display = ['name', 'status', 'scheduled_at', 'total_recipients', 'sent_count', 'failed_count']
    list_filter = ['status']
    search_fields = ['name', 'subject']
    filter_horizontal = ['contact_lists']
    actions = ['prepare', 'send', 'schedule', 'cancel']
    readonly_fields = ['status', 'started_at', 'completed_at', 'created_at', 'updated_at',
        'total_recipients', 'sent_count', 'delivered_count', 'bounced_count', 'failed_count', 'opened_count', 'clicked_count', 'unsubscribed_count']

    def get_urls(self):
        return [path('<int:pk>/test-email/', self.admin_site.admin_view(self.test_email), name='mailing_campaign_test')] + super().get_urls()

    def test_email(self, request, pk):
        campaign = get_object_or_404(Campaign, pk=pk)
        if not self.has_change_permission(request, campaign):
            from django.core.exceptions import PermissionDenied
            raise PermissionDenied
        form = TestEmailForm(request.POST or None)
        if request.method == 'POST' and form.is_valid():
            try:
                result = test_campaign(campaign, form.cleaned_data['email'])
                self.message_user(request, f'Test sent. Provider message ID: {result.get("id", "")}')
                return redirect('admin:mailing_campaign_change', pk)
            except (ValidationError, DeliveryError) as exc:
                form.add_error(None, str(exc))
        return TemplateResponse(request, 'admin/mailing/form.html', {
            **self.admin_site.each_context(request), 'title': f'Send test: {campaign.name}', 'form': form, 'opts': self.model._meta})

    def get_readonly_fields(self, request, obj=None):
        if obj and obj.status != 'draft':
            return [f.name for f in self.model._meta.fields] + ['contact_lists']
        return self.readonly_fields

    @transaction.atomic
    def changeform_view(self, request, object_id=None, form_url='', extra_context=None):
        if object_id and request.method == 'POST':
            Campaign.objects.select_for_update().filter(pk=object_id).first()
        return super().changeform_view(request, object_id, form_url, extra_context)

    def has_delete_permission(self, request, obj=None):
        return False

    def run_action(self, request, queryset, operation):
        for campaign in queryset:
            try:
                operation(campaign)
                self.message_user(request, f'{campaign.name}: action completed.')
            except ValidationError as exc:
                self.message_user(request, str(exc.detail), messages.ERROR)

    @admin.action(description='Prepare selected draft campaigns')
    def prepare(self, request, queryset):
        self.run_action(request, queryset, lambda c: prepare_campaign(c.pk))

    @admin.action(description='Queue selected draft campaigns for sending')
    def send(self, request, queryset):
        self.run_action(request, queryset, lambda c: queue_campaign(c.pk))

    @admin.action(description='Schedule drafts using their saved scheduled_at')
    def schedule(self, request, queryset):
        def apply(c):
            if not c.scheduled_at:
                raise ValidationError('Set scheduled_at on the draft first.')
            schedule_campaign(c.pk, c.scheduled_at)
        self.run_action(request, queryset, apply)

    @admin.action(description='Cancel selected campaigns')
    def cancel(self, request, queryset):
        self.run_action(request, queryset, lambda c: cancel_campaign(c.pk))

class HistoryAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False
    def has_delete_permission(self, request, obj=None):
        return False
    def get_readonly_fields(self, request, obj=None):
        return [f.name for f in self.model._meta.fields]

@admin.register(CampaignRecipient)
class RecipientAdmin(HistoryAdmin):
    list_display = ['email', 'campaign', 'status', 'sent_at', 'retry_count']
    search_fields = ['email', 'provider_message_id']
    list_filter = ['status', 'campaign']

@admin.register(EmailEvent)
class EventAdmin(HistoryAdmin):
    list_display = ['provider_event_id', 'event_type', 'occurred_at', 'processed_at']
    search_fields = ['provider_message_id', 'provider_event_id']
    list_filter = ['event_type']

@admin.register(Unsubscribe)
class UnsubscribeAdmin(HistoryAdmin):
    list_display = ['contact', 'campaign', 'created_at']
    search_fields = ['contact__email']

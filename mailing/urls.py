from django.urls import include, path
from rest_framework.routers import DefaultRouter
from .views import ContactViewSet, ContactListViewSet, EmailTemplateViewSet, CampaignViewSet, dashboard, settings_status, unsubscribe
from .webhooks import resend_webhook

router = DefaultRouter()
router.register('contacts', ContactViewSet)
router.register('lists', ContactListViewSet)
router.register('templates', EmailTemplateViewSet)
router.register('campaigns', CampaignViewSet)
urlpatterns = [path('', include(router.urls)), path('dashboard/', dashboard), path('settings/status/', settings_status),
    path('unsubscribe/<str:token>/', unsubscribe), path('webhooks/resend/', resend_webhook)]

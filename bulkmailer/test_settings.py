import os
os.environ.setdefault('SECRET_KEY', 'isolated-tests-only-not-a-production-secret-key-123456789')
os.environ['DEBUG'] = 'True'
from .settings import *  # noqa: F403
DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': BASE_DIR / 'test-local.sqlite3'}}
PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']
CELERY_BROKER_URL = 'memory://'
CELERY_RESULT_BACKEND = 'cache+memory://'
RESEND_API_KEY = ''
RESEND_FROM_EMAIL = 'sender@example.com'
SECURE_SSL_REDIRECT = False

STORAGES = {"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"}, "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}}

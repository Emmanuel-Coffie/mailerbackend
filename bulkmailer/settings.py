import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv


# ---------------------------------------------------------
# Base
# ---------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")


def env_list(name, default=""):
    """
    Convert comma-separated environment variables into
    a clean Python list.
    """
    return [
        item.strip().rstrip("/")
        for item in os.getenv(name, default).split(",")
        if item.strip()
    ]


# ---------------------------------------------------------
# Core Django settings
# ---------------------------------------------------------

DEBUG = os.getenv("DEBUG", "False").lower() == "true"

SECRET_KEY = os.getenv("SECRET_KEY", "")

if not SECRET_KEY:
    raise ImproperlyConfigured(
        "SECRET_KEY must be configured in .env or the environment."
    )


ALLOWED_HOSTS = env_list(
    "ALLOWED_HOSTS",
    "localhost,127.0.0.1",
)


# ---------------------------------------------------------
# Applications
# ---------------------------------------------------------

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    # Third party
    "rest_framework",
    "django_filters",
    "corsheaders",

    # Local apps
    "mailing",
]


# ---------------------------------------------------------
# Middleware
# ---------------------------------------------------------

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
     "whitenoise.middleware.WhiteNoiseMiddleware",

    # Must be before CommonMiddleware
    "corsheaders.middleware.CorsMiddleware",

    "django.contrib.sessions.middleware.SessionMiddleware",
    
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]


# ---------------------------------------------------------
# URLs / WSGI / ASGI
# ---------------------------------------------------------

ROOT_URLCONF = "bulkmailer.urls"

WSGI_APPLICATION = "bulkmailer.wsgi.application"
ASGI_APPLICATION = "bulkmailer.asgi.application"


# ---------------------------------------------------------
# Templates
# ---------------------------------------------------------

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

DATABASE_SSL_CA = os.getenv(
    "DATABASE_SSL_CA",
    str(BASE_DIR / "certs" / "ca.pem"),
)

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.mysql",
        "NAME": os.getenv("DATABASE_NAME", "bulkmailer"),
        "USER": os.getenv("DATABASE_USER", ""),
        "PASSWORD": os.getenv("DATABASE_PASSWORD", ""),
        "HOST": os.getenv("DATABASE_HOST", ""),
        "PORT": os.getenv("DATABASE_PORT", ""),
        "OPTIONS": {
            "charset": "utf8mb4",
            "init_command": "SET sql_mode='STRICT_TRANS_TABLES'",
            "ssl": {
                "ca": DATABASE_SSL_CA,
            },
        },
    }
}

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}
# ---------------------------------------------------------
# Password validation
# ---------------------------------------------------------

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME":
        "django.contrib.auth.password_validation."
        "UserAttributeSimilarityValidator"
    },
    {
        "NAME":
        "django.contrib.auth.password_validation."
        "MinimumLengthValidator"
    },
    {
        "NAME":
        "django.contrib.auth.password_validation."
        "CommonPasswordValidator"
    },
    {
        "NAME":
        "django.contrib.auth.password_validation."
        "NumericPasswordValidator"
    },
]


# ---------------------------------------------------------
# Internationalization
# ---------------------------------------------------------

LANGUAGE_CODE = "en-us"

TIME_ZONE = os.getenv("DEFAULT_TIMEZONE", "UTC")

USE_I18N = True
USE_TZ = True


# ---------------------------------------------------------
# Static files
# ---------------------------------------------------------

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# ---------------------------------------------------------
# Django REST Framework
# ---------------------------------------------------------

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],

    "DEFAULT_PERMISSION_CLASSES": [
        "mailing.permissions.IsEmailAdmin",
    ],

    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],

    "DEFAULT_PAGINATION_CLASS":
        "rest_framework.pagination.PageNumberPagination",

    "PAGE_SIZE": 50,
}


# ---------------------------------------------------------
# Frontend / backend URLs
# ---------------------------------------------------------

FRONTEND_URL = os.getenv(
    "FRONTEND_URL",
    "http://localhost:5173",
).strip().rstrip("/")


BACKEND_URL = os.getenv(
    "BACKEND_URL",
    "http://localhost:8000",
    
).strip().rstrip("/")


# ---------------------------------------------------------
# CORS
# ---------------------------------------------------------

CORS_ALLOWED_ORIGINS = env_list(
    "CORS_ALLOWED_ORIGINS",
    "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000,https://mailerfrontend.vercel.app",
)


# ---------------------------------------------------------
# CSRF
# ---------------------------------------------------------

CSRF_TRUSTED_ORIGINS = env_list(
    "CSRF_TRUSTED_ORIGINS",
    (
        "http://localhost:5173,"
        "http://127.0.0.1:5173,"
        "http://localhost:8000,"
        "http://127.0.0.1:8000,"
        "https://mailerfrontend.vercel.app,"
    ),
)


# ---------------------------------------------------------
# Redis / Celery
# ---------------------------------------------------------

REDIS_URL = os.getenv(
    "REDIS_URL",
    "redis://localhost:6379/0",
)

CELERY_BROKER_URL = os.getenv(
    "CELERY_BROKER_URL",
    REDIS_URL,
)

CELERY_RESULT_BACKEND = os.getenv(
    "CELERY_RESULT_BACKEND",
    REDIS_URL,
)

CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"

CELERY_ACCEPT_CONTENT = ["json"]

CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1


CELERY_BEAT_SCHEDULE = {
    "dispatch-due": {
        "task": "mailing.tasks.dispatch_due_campaigns",
        "schedule": 60.0,
    },
}


# ---------------------------------------------------------
# Resend email configuration
# ---------------------------------------------------------

RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
RESEND_WEBHOOK_SECRET = os.getenv(
    "RESEND_WEBHOOK_SECRET",
    "",
)

RESEND_FROM_EMAIL = os.getenv(
    "RESEND_FROM_EMAIL",
    "",
)

RESEND_FROM_NAME = os.getenv(
    "RESEND_FROM_NAME",
    "",
)

RESEND_REPLY_TO = os.getenv(
    "RESEND_REPLY_TO",
    "",
)


# ---------------------------------------------------------
# Email campaign settings
# ---------------------------------------------------------

EMAIL_BATCH_SIZE = max(
    1,
    min(
        int(os.getenv("EMAIL_BATCH_SIZE", "50")),
        100,
    ),
)

EMAIL_RETRY_LIMIT = int(
    os.getenv("EMAIL_RETRY_LIMIT", "3")
)

EMAIL_ALLOWED_TEST_RECIPIENTS = {
    value.strip().lower()
    for value in os.getenv(
        "EMAIL_ALLOWED_TEST_RECIPIENTS",
        "",
    ).split(",")
    if value.strip()
}


# ---------------------------------------------------------
# Upload configuration
# ---------------------------------------------------------

CSV_MAX_BYTES = int(
    os.getenv(
        "CSV_MAX_BYTES",
        "5242880",
    )
)

DATA_UPLOAD_MAX_MEMORY_SIZE = (
    CSV_MAX_BYTES + 65536
)


# ---------------------------------------------------------
# Security
# ---------------------------------------------------------

SECURE_SSL_REDIRECT = not DEBUG

SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG

SECURE_HSTS_SECONDS = (
    0 if DEBUG else 31536000
)

SECURE_HSTS_INCLUDE_SUBDOMAINS = not DEBUG
SECURE_HSTS_PRELOAD = not DEBUG


# Enable only when running behind a trusted reverse proxy.
if os.getenv(
    "TRUST_PROXY",
    "False",
).lower() == "true":

    SECURE_PROXY_SSL_HEADER = (
        "HTTP_X_FORWARDED_PROTO",
        "https",
    )


# ---------------------------------------------------------
# Logging
# ---------------------------------------------------------

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,

    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
        },
    },

    "loggers": {
        "mailing": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
    },
}
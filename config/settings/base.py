"""تنظیمات پایهٔ مشترک سامانه کاوه ۱۸۵ (Enterprise Django 6.x + DRF)."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import Any

from decouple import Csv, config

BASE_DIR = Path(__file__).resolve().parent.parent.parent

SECRET_KEY = config(
    "DJANGO_SECRET_KEY",
    default="kaveh185-dev-secret-key-do-not-use-in-prod-98f1a2b3c4d5e6f7a8b9c0d1e2f3",
)
PII_ENCRYPTION_KEY = config(
    "PII_ENCRYPTION_KEY",
    default=SECRET_KEY,
)
PII_BLIND_INDEX_KEY = config(
    "PII_BLIND_INDEX_KEY",
    default=SECRET_KEY,
)

DEBUG = config("DJANGO_DEBUG", default=False, cast=bool)
ALLOWED_HOSTS: list[str] = config(
    "DJANGO_ALLOWED_HOSTS",
    default="localhost,127.0.0.1,0.0.0.0,testserver",
    cast=Csv(),
)

APP_VERSION = config("APP_VERSION", default="1.0.0")
ADMIN_URL_PATH = config("DJANGO_ADMIN_URL", default="secure-kaveh185-admin/")

DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "drf_spectacular",
    "django_filters",
    "corsheaders",
]

LOCAL_APPS = [
    "apps.core",
    "apps.audit_logs",
    "apps.mosques",
    "apps.authentication",
    "apps.exam",
    "apps.notifications",
    "apps.reporting",
    "apps.command_center",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "apps.core.middleware.RequestIDMiddleware",
    "apps.core.middleware.PerformanceBudgetMiddleware",
    "apps.core.middleware.SecurityHeadersMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.core.middleware.APIVersionHeaderMiddleware",
]

ROOT_URLCONF = "config.urls"

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

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# پایگاه داده (قابل پیکربندی برای PostgreSQL، MySQL/MariaDB و SQLite)
DB_ENGINE = config("DB_ENGINE", default="django.db.backends.sqlite3")
DB_NAME = config("DB_NAME", default=str(BASE_DIR / "db.sqlite3"))
DB_USER = config("DB_USER", default="")
DB_PASSWORD = config("DB_PASSWORD", default="")
DB_HOST = config("DB_HOST", default="")
DB_PORT = config("DB_PORT", default="")

DATABASES: dict[str, dict[str, Any]] = {
    "default": {
        "ENGINE": DB_ENGINE,
        "NAME": DB_NAME,
    }
}
if DB_ENGINE != "django.db.backends.sqlite3":
    DATABASES["default"].update(
        {
            "USER": DB_USER,
            "PASSWORD": DB_PASSWORD,
            "HOST": DB_HOST,
            "PORT": DB_PORT,
            "CONN_MAX_AGE": config("DB_CONN_MAX_AGE", default=60, cast=int),
            "CONN_HEALTH_CHECKS": True,
        }
    )

# کش (پشتیبانی از Redis در استقرار کانتینری و LocMem/Database در هاست اشتراکی)
REDIS_URL = config("REDIS_URL", default="")
if REDIS_URL:
    CACHES: dict[str, dict[str, Any]] = {
        "default": {
            "BACKEND": "django_redis.cache.RedisCache",
            "LOCATION": REDIS_URL,
            "OPTIONS": {
                "CLIENT_CLASS": "django_redis.client.DefaultClient",
                "IGNORE_EXCEPTIONS": True,
            },
            "KEY_PREFIX": "kaveh185",
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "kaveh185-locmem-cache",
            "KEY_PREFIX": "kaveh185",
        }
    }

AUTH_USER_MODEL = "authentication.User"

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 8},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "fa-ir"
TIME_ZONE = "Asia/Tehran"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATIC_ROOT.mkdir(parents=True, exist_ok=True)
WHITENOISE_USE_FINDERS = True
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# تنظیمات Django REST Framework
REST_FRAMEWORK: dict[str, Any] = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "apps.authentication.jwt_auth.SessionAwareJWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_PAGINATION_CLASS": "apps.core.pagination.StandardLimitOffsetPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_FILTER_BACKENDS": ("django_filters.rest_framework.DjangoFilterBackend",),
    "EXCEPTION_HANDLER": "apps.core.exceptions.custom_exception_handler",
    "DEFAULT_THROTTLE_RATES": {
        "anon": config("THROTTLE_ANON", default="120/min"),
        "user": config("THROTTLE_USER", default="240/min"),
        "auth_register": config("THROTTLE_AUTH_REGISTER", default="30/min"),
        "auth_otp_request": config("THROTTLE_OTP_REQUEST", default="15/min"),
        "auth_otp_verify": config("THROTTLE_OTP_VERIFY", default="30/min"),
        "auth_login_password": config("THROTTLE_AUTH_LOGIN_PASSWORD", default="20/min"),
        "auth_sessions": config("THROTTLE_AUTH_SESSIONS", default="60/min"),
        "otp_request": config("THROTTLE_OTP_REQUEST", default="15/min"),
        "otp_verify": config("THROTTLE_OTP_VERIFY", default="30/min"),
        "exam_start": config("THROTTLE_EXAM_START", default="30/min"),
        "exam_answer": config("THROTTLE_EXAM_ANSWER", default="240/min"),
        "health_check": config("THROTTLE_HEALTH_PROBE", default="120/min"),
        "health_probe": config("THROTTLE_HEALTH_PROBE", default="120/min"),
    },
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(
        minutes=config("JWT_ACCESS_LIFETIME_MINUTES", default=360, cast=int)
    ),
    "REFRESH_TOKEN_LIFETIME": timedelta(
        days=config("JWT_REFRESH_LIFETIME_DAYS", default=7, cast=int)
    ),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "ALGORITHM": "HS256",
    "SIGNING_KEY": SECRET_KEY,
    "AUTH_HEADER_TYPES": ("Bearer",),
}

SPECTACULAR_SETTINGS: dict[str, Any] = {
    "TITLE": "Kaveh185 Competition & Cultural Mobilization API",
    "DESCRIPTION": (
        "مستندات جامع API بک‌اند سامانه مسابقه بزرگ فرهنگی و کتابخوانی هفته بسیج "
        "— حوزه مقاومت بسیج ۱۸۵ شهید کاوه (پوشش ۱۷ مسجد، آزمون ۵ سواله چهارگزینه‌ای تصادفی، "
        "کارنامه بدون افشای کلید، رتبه‌بندی زنده مساجد و کاوشگر قرعه‌کشی حضوری)"
    ),
    "VERSION": APP_VERSION,
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    "SCHEMA_PATH_PREFIX": r"/api/v1",
}

# تنظیمات CORS و پروکسی
CORS_ALLOW_ALL_ORIGINS = config("CORS_ALLOW_ALL_ORIGINS", default=False, cast=bool)
CORS_ALLOWED_ORIGINS: list[str] = config(
    "CORS_ALLOWED_ORIGINS",
    default="http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173",
    cast=Csv(),
)
TRUSTED_PROXY_CIDRS: list[str] = config(
    "TRUSTED_PROXY_CIDRS",
    default="127.0.0.1/32,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16",
    cast=Csv(),
)

# درگاه پیامکی و OTP
SMS_PROVIDER = config("SMS_PROVIDER", default="console")
SMS_API_URL = config("SMS_API_URL", default="")
SMS_API_KEY = config("SMS_API_KEY", default="")
SMS_SENDER_LINE = config("SMS_SENDER_LINE", default="3000185")
SMS_TIMEOUT_SECONDS = config("SMS_TIMEOUT_SECONDS", default=4.0, cast=float)
OTP_EXPOSE_DEBUG_CODE = config("OTP_EXPOSE_DEBUG_CODE", default=False, cast=bool)

# تنظیمات متریک‌ها، مستندات و گیت‌های امنیتی
METRICS_PUBLIC_ENABLED = config("METRICS_PUBLIC_ENABLED", default=False, cast=bool)
METRICS_SCRAPE_TOKEN = config("METRICS_SCRAPE_TOKEN", default="")
API_DOCS_PUBLIC = config("API_DOCS_PUBLIC", default=True, cast=bool)
ENFORCE_ADMIN_STEP_UP_MFA = config("ENFORCE_ADMIN_STEP_UP_MFA", default=False, cast=bool)
STEP_UP_MFA_MAX_AGE_SECONDS = config("STEP_UP_MFA_MAX_AGE_SECONDS", default=900, cast=int)
SQL_DEFAULT_QUERY_BUDGET = config("SQL_DEFAULT_QUERY_BUDGET", default=25, cast=int)

# تنظیمات Celery
CELERY_BROKER_URL = config("CELERY_BROKER_URL", default=REDIS_URL or "memory://")
CELERY_RESULT_BACKEND = config("CELERY_RESULT_BACKEND", default=REDIS_URL or "cache+memory://")
CELERY_TASK_ALWAYS_EAGER = config(
    "CELERY_TASK_ALWAYS_EAGER", default=not bool(REDIS_URL), cast=bool
)
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE

"""تنظیمات محیط اجرای تست‌های خودکار (`config.settings.test`)."""

from __future__ import annotations

from .base import *

DEBUG = False
OTP_EXPOSE_DEBUG_CODE = True
API_DOCS_PUBLIC = True
METRICS_PUBLIC_ENABLED = True
CELERY_TASK_ALWAYS_EAGER = True

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "kaveh185-test-cache",
    }
}

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"] = {
    "anon": "10000/min",
    "user": "10000/min",
    "auth_register": "10000/min",
    "auth_otp_request": "10000/min",
    "auth_otp_verify": "10000/min",
    "auth_login_password": "10000/min",
    "auth_sessions": "10000/min",
    "otp_request": "10000/min",
    "otp_verify": "10000/min",
    "exam_start": "10000/min",
    "exam_answer": "10000/min",
    "health_check": "10000/min",
    "health_probe": "10000/min",
}

"""تنظیمات محیط اجرای تست‌های خودکار (`config.settings.test`)."""

from __future__ import annotations

import os

from .base import *

DEBUG = False
OTP_EXPOSE_DEBUG_CODE = True
API_DOCS_PUBLIC = True
METRICS_PUBLIC_ENABLED = True
CELERY_TASK_ALWAYS_EAGER = True

# ─────────────────────────────────────────────────────────────────────────────
# پایگاه داده در تست‌ها
#
# پیش‌فرض SQLite حافظه‌ای است: سریع و بدون وابستگی بیرونی، مناسب CI.
#
# ولی SQLite همان MariaDB نیست. تفاوت‌های واقعی (نوع ستون‌ها، utf8mb4، رفتار
# تراکنش، محدودیت طول ایندکس) فقط وقتی دیده می‌شوند که روی همان موتور اجرا شود.
# پس اگر DB_ENGINE در محیط ست شده باشد، از آن استفاده می‌کنیم:
#
#     DB_ENGINE=django.db.backends.mysql DB_NAME=... pytest
#
# این کار اجازه می‌دهد همان تست‌ها روی MariaDB 11.4 هاست هم اجرا شوند،
# بدون اینکه CI کند یا به سرویس بیرونی وابسته شود.
# ─────────────────────────────────────────────────────────────────────────────
_env_engine = os.environ.get("DB_ENGINE", "").strip()

if _env_engine and _env_engine != "django.db.backends.sqlite3":
    DATABASES = {
        "default": {
            "ENGINE": _env_engine,
            "NAME": os.environ.get("DB_NAME", ""),
            "USER": os.environ.get("DB_USER", ""),
            "PASSWORD": os.environ.get("DB_PASSWORD", ""),
            "HOST": os.environ.get("DB_HOST", "localhost"),
            "PORT": os.environ.get("DB_PORT", ""),
            "TEST": {"NAME": os.environ.get("DB_TEST_NAME", "test_kaveh185")},
        }
    }
else:
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

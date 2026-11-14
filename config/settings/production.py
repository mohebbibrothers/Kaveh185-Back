"""تنظیمات سخت‌گیرانهٔ محیط پروداکشن (`config.settings.production`)."""

from __future__ import annotations

from decouple import Csv, config

from .base import *

DEBUG = False
OTP_EXPOSE_DEBUG_CODE = False
API_DOCS_PUBLIC = config("API_DOCS_PUBLIC", default=False, cast=bool)
METRICS_PUBLIC_ENABLED = config("METRICS_PUBLIC_ENABLED", default=False, cast=bool)

ALLOWED_HOSTS = config(
    "DJANGO_ALLOWED_HOSTS",
    default="kaveh185.ir,api.kaveh185.ir,localhost,127.0.0.1",
    cast=Csv(),
)

# هدرها و کوکی‌های امنیتی سطح پروداکشن (عبور از `manage.py check --deploy --fail-level WARNING`)
SECURE_SSL_REDIRECT = config("SECURE_SSL_REDIRECT", default=True, cast=bool)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SECURE = True
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = "Lax"

SECURE_HSTS_SECONDS = config("SECURE_HSTS_SECONDS", default=31536000, cast=int)
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
X_FRAME_OPTIONS = "DENY"

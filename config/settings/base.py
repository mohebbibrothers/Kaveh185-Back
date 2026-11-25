"""تنظیمات پایهٔ مشترک سامانه کاوه ۱۸۵ (Enterprise Django 6.x + DRF)."""

from __future__ import annotations

import ipaddress
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

# ─────────────────────────────────────────────────────────────────────────────
# پل به لایهٔ رمزنگاری
#
# چرا این سه خط؟ `apps/core/crypto.py` کلید را از `FIELD_ENCRYPTION_KEY` و
# `FIELD_HASH_KEY` می‌خواند، ولی این فایل تنها `PII_*` را ست می‌کرد. نتیجه:
# مقدار `PII_ENCRYPTION_KEY` در .env نوشته می‌شد و هیچ‌وقت استفاده نمی‌شد و
# رمزنگاری بی‌سروصدا به `SECRET_KEY` برمی‌گشت. اگر روزی SECRET_KEY عوض شود،
# همهٔ داده‌های هویتیِ ذخیره‌شده دیگر قابل رمزگشایی نیستند — و اگر کسی فقط
# دیتابیس را بدزدد، با همان SECRET_KEY می‌تواند بخواند. این پل، دو کلید را
# از هم جدا می‌کند تا چرخش SECRET_KEY به از دست رفتن PII منجر نشود.
# ─────────────────────────────────────────────────────────────────────────────
FIELD_ENCRYPTION_KEY = PII_ENCRYPTION_KEY
FIELD_HASH_KEY = PII_BLIND_INDEX_KEY


DEBUG = config("DJANGO_DEBUG", default=False, cast=bool)
ALLOWED_HOSTS: list[str] = config(
    "DJANGO_ALLOWED_HOSTS",
    default="localhost,127.0.0.1,0.0.0.0,testserver",
    cast=Csv(),
)


def _is_public_domain(host: str) -> bool:
    """آیا این هاست یک دامنهٔ واقعی است که «www.» گرفتن برایش معنا دارد؟

    IPها، localhost، testserver، الگوهای * و . رد می‌شوند — هم بی‌معناست،
    هم یکی از آن‌ها (آدرس همهٔ اینترفیس‌ها) نباید هرگز در این فهرست ظاهر شود.
    """
    if host.startswith(("*", ".", "www.")) or ":" in host:
        return False
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return "." in host
    return False


def _with_www(hosts: list[str]) -> list[str]:
    """افزودن نسخهٔ `www.` هر دامنه، بدون نیاز به ویرایش دستی `.env`.

    چرا لازم است: Passenger روی این هاست، دامنهٔ اصلی را هم با هاست‌نیم
    `www.` تحویل می‌دهد. اگر `www.kaveh185.ir` در فهرست نباشد، جنگو
    `DisallowedHost` می‌دهد و کاربر صفحهٔ خطای ۴۰۰ می‌بیند — خطایی که
    هیچ ربطی به فرانت ندارد و سخت پیدا می‌شود.
    """
    out = list(hosts)
    for host in hosts:
        if not _is_public_domain(host):
            continue
        candidate = "www." + host
        if candidate not in out:
            out.append(candidate)
    return out


ALLOWED_HOSTS = _with_www(ALLOWED_HOSTS)

APP_VERSION = config("APP_VERSION", default="1.0.0")
ADMIN_URL_PATH = config("DJANGO_ADMIN_URL", default="secure-kaveh185-admin/")

# ── مسیرهای ورود/خروج ────────────────────────────────────────────────────
# پیش‌فرض جنگو `/accounts/profile/` است که در این پروژه وجود ندارد؛ نتیجه‌اش
# این بود که ادمین بعد از ورود موفق، ۴۰۴ می‌گرفت. هر سه مسیر از همان
# ADMIN_URL_PATH ساخته می‌شوند تا اگر آدرس پنل عوض شد، اینها هم همراه بیایند.
_ADMIN_PREFIX = "/" + ADMIN_URL_PATH.strip("/")
LOGIN_URL = f"{_ADMIN_PREFIX}/login/"
LOGIN_REDIRECT_URL = f"{_ADMIN_PREFIX}/"
LOGOUT_REDIRECT_URL = f"{_ADMIN_PREFIX}/login/"

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
    "apps.gallery",
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
    # ۴۰۴ِ گویا زیرِ پیشوندِ پنل: اگر مسیری از پنل پیدا نشد و کاربر staff بود،
    # به‌جای صفحهٔ مبهم، علتِ محتمل و دستورِ تشخیص نشان داده می‌شود
    # (`apps/core/middleware_help.py`). باید **پیش از** FrontendMiddleware
    # بیاید تا آن یکی ۴۰۴ را به صفحهٔ فرانت تبدیل نکند.
    "apps.core.middleware_help.AdminRouteHintMiddleware",
    # ⚠️ باید آخرین باشد: فقط درخواست‌هایی را می‌گیرد که جنگو برایشان ۴۰۴
    # داده است (یعنی مسیری در بک‌اند نیست) و آن‌ها را به فرانت ایستا می‌دهد.
    # اگر پیش از بقیه بیاید، می‌تواند مسیرهای API را ببلعد.
    "apps.core.frontend.FrontendMiddleware",
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
# ⚠️ بک‌اندِ SQLite را عمداً به `apps.core.db_sqlite` بردیم.
# دلیلش امنیتی/پایداری است، نه زیبایی: با بک‌اندِ استاندارد، SQLite در حالتِ
# ژورنالِ `DELETE` **کلِ فایل** را هنگامِ نوشتن قفل می‌کند و در پیکِ آزمون
# خواندن‌ها با «database is locked» می‌شکنند — یعنی سایت بدونِ هیچ تغییری در
# کد «قطع» می‌شود. بک‌اندِ ما WAL + busy_timeout + synchronous=NORMAL را روی
# هر اتصال تنظیم می‌کند (توضیحِ کامل در همان فایل). اگر `DB_ENGINE` را به
# MySQL تغییر دهید، این بک‌اند به‌کل بی‌اثر می‌شود.
DB_ENGINE = config(
    "DB_ENGINE",
    default="apps.core.db_sqlite",
    cast=lambda v: (
        "apps.core.db_sqlite"
        if v.strip() in {"", "django.db.backends.sqlite3", "sqlite3"}
        else v.strip()
    ),
)
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
if not DB_ENGINE.endswith(("sqlite3", "db_sqlite")):
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

# ── فرانت ایستای Next (سروشده از درون جنگو) ─────────────────────────────
# پوشه‌ای که خروجی `next build` (حالت export) درونش قرار می‌گیرد. مسیر
# در تولید با متغیر محیطی `FRONTEND_DIST` روی هاست تعیین می‌شود؛ پیش‌فرض
# `<BASE_DIR>/frontend` است و اگر خالی/نبود، سایت صفحهٔ ۵۰۳ فارسی می‌دهد
# و API دست‌نخورده کار می‌کند. جزئیات: `apps/core/frontend.py`.
FRONTEND_DIST = config("FRONTEND_DIST", default=str(BASE_DIR / "frontend"))

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
# دامنه‌های مجاز مرورگر. `kaveh185.ir` (پیش‌نمایش Vercel) و دامنهٔ اصلی از روز اول
# حاضرند تا هرگز Insecure CORS در کنسول مرورگر دیده نشود. پیش‌نمایش‌های خودکار
# Vercel با الگوی wildcard در `CORS_ALLOWED_ORIGIN_REGEXES` پوشش داده می‌شوند.
CORS_ALLOWED_ORIGINS: list[str] = config(
    "CORS_ALLOWED_ORIGINS",
    default=(
        "http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173,"
        "https://kaveh185.ir,https://www.kaveh185.ir"
    ),
    cast=Csv(),
)
CORS_ALLOWED_ORIGIN_REGEXES: list[str] = config(
    "CORS_ALLOWED_ORIGIN_REGEXES",
    default=r"^https://kaveh185(-[a-z0-9]+)*\.vercel\.app$",
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

# ── رباتِ بله: کانالِ جایگزینِ پیامک برای کدِ تأیید ───────────────────────
# تا وقتی پنلِ پیامکی (با اینماد) در دسترس نیست، کدِ یک‌بارمصرف از این ربات
# می‌رود. `BALE_BOT_TOKEN` را از @BotFatherِ بله بگیر و در `.env` بگذار؛
# اگر خالی باشد، ارسال از راهِ بله انجام نمی‌شود و فقط مسیرِ پیامک/کدِ محلی
# می‌ماند (هیچ خطای کاربری رخ نمی‌دهد).
BALE_BOT_TOKEN = config("BALE_BOT_TOKEN", default="")
BALE_BOT_USERNAME = config("BALE_BOT_USERNAME", default="")
BALE_API_BASE = config("BALE_API_BASE", default="https://tapi.bale.ai")
#: متنِ راهنمای «شروع» که در پیامِ اولِ ربات می‌آید.
BALE_WEBHOOK_SECRET = config("BALE_WEBHOOK_SECRET", default="")
#: نشانیِ کاملِ وب‌هوک. اگر خالی باشد از `ALLOWED_HOSTS` ساخته می‌شود؛ ولی
#: چون روی این هاست `api.` هم `www.` هم بدونِ پیشوند به یک اپ می‌رسند، بهترین
#: کار pin کردنِ آن در `.env` است تا هیچ دستوری حدس نزند.
BALE_WEBHOOK_URL = config("BALE_WEBHOOK_URL", default="")
#: «آیا تأییدِ شماره با کد، در ثبت‌نام اجباری است؟»
#:
#: ⚠️ سیاستِ فعال (آزمونِ میدانیِ حوزه، آبان ۱۴۰۵): **خاموش**. تصمیمِ صریحِ
#: کارفرما بود: «فعلاً بیخیالِ کدِ تأیید شو؛ کاربر اطلاعات را بزند و مستقیم
#: وارد آزمون شود.» دلیلِ عملی هم داشت: تحویلِ کد از بله به شرطِ «شروعِ ربات
#: توسط کاربر» وابسته است و در آزمونِ واقعی کد به دستِ همه نرسید.
#:
#: با خاموش‌بودن، `register_or_enter_participant` نشست را بی‌کد صادر می‌کند و
#: `IsVerifiedParticipant` هم شرطِ تأیید را اعمال نمی‌کند. برای روشن‌کردن،
#: فقط `BALE_OTP_MANDATORY=true` را در `.env` بگذارید — هیچ تغییری در کد لازم
#: نیست و هر دو لایه با هم روشن می‌شوند.
#:
#: ⚠️ هشدارِ امنیتیِ باقی: با خاموش‌بودن، هر کسی که شماره و کدملیِ یک نفرِ
#: ثبت‌نام‌شده را بداند می‌تواند به‌جای او نشست بگیرد (شماره = هویت). در آزمونِ
#: رسمیِ امتیازدار، این را دوباره روشن کنید.
BALE_OTP_MANDATORY = config("BALE_OTP_MANDATORY", default=False, cast=bool)
BALE_START_HINT = config(
    "BALE_START_HINT", default="برای دریافت کد تأیید، شمارهٔ همراه خود را همین‌جا بفرستید."
)
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

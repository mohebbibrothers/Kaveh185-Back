"""گارد سراسری ضدسوءاستفاده برای حفاظت از بودجهٔ پنل پیامکی و جلوگیری از SMS Bombing."""

from __future__ import annotations

import logging

from django.conf import settings
from django.core.cache import cache

from apps.core.exceptions import RateLimitDomainError

logger = logging.getLogger("apps.authentication")


def enforce_otp_anti_abuse(*, phone_number: str, ip_address: str) -> None:
    """بررسی سقف درخواست OTP به تفکیک شماره، IP و سقف سراسری سامانه."""
    global_limit = int(getattr(settings, "AUTH_OTP_GLOBAL_THRESHOLD", 500))
    window_sec = int(getattr(settings, "AUTH_OTP_GLOBAL_WINDOW_SECONDS", 60))
    per_phone_limit = int(getattr(settings, "AUTH_OTP_PER_PHONE_LIMIT", 5))
    per_ip_limit = int(getattr(settings, "AUTH_OTP_PER_IP_LIMIT", 20))

    phone_key = f"kaveh185:otp:phone:{phone_number}"
    ip_key = f"kaveh185:otp:ip:{ip_address}"
    global_key = "kaveh185:otp:global"

    try:
        phone_count = int(cache.get(phone_key) or 0)
        ip_count = int(cache.get(ip_key) or 0)
        global_count = int(cache.get(global_key) or 0)

        if phone_count >= per_phone_limit:
            raise RateLimitDomainError(
                "تعداد درخواست کد تایید برای این شماره بیش از حد مجاز است. لطفاً چند دقیقه صبر کنید.",
                code="otp_phone_rate_limited",
            )
        if ip_count >= per_ip_limit:
            raise RateLimitDomainError(
                "تعداد درخواست کد تایید از شبکهٔ شما بیش از حد مجاز است.",
                code="otp_ip_rate_limited",
            )
        if global_count >= global_limit:
            raise RateLimitDomainError(
                "سامانهٔ پیامکی در حال حاضر با ترافیک بالا مواجه است. لطفاً یک دقیقه دیگر تلاش کنید.",
                code="otp_global_rate_limited",
            )

        cache.set(phone_key, phone_count + 1, timeout=window_sec)
        cache.set(ip_key, ip_count + 1, timeout=window_sec)
        cache.set(global_key, global_count + 1, timeout=window_sec)
    except RateLimitDomainError:
        raise
    except Exception:
        logger.warning("otp_anti_abuse_cache_unavailable")

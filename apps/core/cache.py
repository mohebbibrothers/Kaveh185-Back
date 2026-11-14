"""موتور کش ترکیبی کاوه ۱۸۵: نسخه‌گذاری اتمیک بر پایهٔ Epoch + الگوی SWR با قفل Dogpile.

چرا این معماری:
    ۱) ابطال مبتنی بر Epoch (`epoch:<namespace>`): به جای حذف تک‌تک کلیدها، با هر
       تغییر در مشارکت مسجد یا تنظیمات آزمون، شمارندهٔ نسخه یک واحد افزایش می‌یابد و
       تمام کلیدهای قبلی بلافاصله از دید خوانندگان نامعتبر می‌شوند.
    ۲) الگوی Stale-While-Revalidate (`cache_get_or_set_swr`): تا پایان `soft_ttl`
       دادهٔ تازه برگردانده می‌شود؛ بین `soft_ttl` و `hard_ttl` یک درخواست قفل بازسازی
       (`lock`) را می‌گیرد و بقیه بدون انتظار، دادهٔ قبلی را دریافت می‌کنند تا هرگز
       Cache Stampede در زمان اوج مسابقه رخ ندهد.
    ۳) ایمنی در برابر خرابی (`_safe_get` / `_safe_set`): اگر کش موقتاً در دسترس نباشد،
       سرویس از روی دیتابیس پاسخ می‌دهد و هرگز به کاربر خطای ۵۰۰ نمی‌دهد.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any, Final

from django.core.cache import cache

from .cache_policy import get_cache_policy

logger = logging.getLogger("apps.core.cache")

EPOCH_TTL_SECONDS: Final[int] = 60 * 60 * 24 * 30  # ۳۰ روز


def _safe_get(key: str) -> Any | None:
    """خواندن ایمن از کش؛ خطای زیرساخت کش هرگز درخواست کاربر را نمی‌شکند."""
    try:
        return cache.get(key)
    except Exception:
        logger.warning("cache_read_failed key=%s", key)
        return None


def _safe_set(key: str, value: Any, timeout: int | None) -> bool:
    """نوشتن ایمن در کش با مدیریت استثنا."""
    try:
        cache.set(key, value, timeout=timeout)
        return True
    except Exception:
        logger.warning("cache_write_failed key=%s", key)
        return False


def _safe_add(key: str, value: Any, timeout: int | None) -> bool:
    """افزودن کلید فقط در صورت عدم وجود (برای قفل Dogpile و مقداردهی اولیه Epoch)."""
    try:
        return bool(cache.add(key, value, timeout=timeout))
    except Exception:
        logger.warning("cache_add_failed key=%s", key)
        return False


def epoch_key(domain: str) -> str:
    """ساخت کلید شمارندهٔ نسخه (Epoch) برای یک دامنه."""
    policy = get_cache_policy(domain)
    return f"epoch:{policy.namespace}"


def get_epoch(domain: str) -> int:
    """خواندن شمارهٔ نسخهٔ فعلی یک دامنه (پیش‌فرض ۱)."""
    raw = _safe_get(epoch_key(domain))
    if raw is None:
        return 1
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 1


def bump_epoch(domain: str) -> int:
    """افزایش اتمیک نسخهٔ کش دامنه؛ تمام کلیدهای قبلی آن دامنه بلافاصله منقضی می‌شوند."""
    key = epoch_key(domain)
    try:
        cache.add(key, 1, timeout=EPOCH_TTL_SECONDS)
        new_val = int(cache.incr(key))
        cache.touch(key, timeout=EPOCH_TTL_SECONDS)
        return new_val
    except Exception:
        next_val = get_epoch(domain) + 1
        _safe_set(key, next_val, timeout=EPOCH_TTL_SECONDS)
        return next_val


def build_versioned_key(domain: str, suffix: str) -> str:
    """ساخت کلید کش نسخه‌دار شامل شمارهٔ Epoch فعلی دامنه."""
    policy = get_cache_policy(domain)
    epoch = get_epoch(domain)
    return f"{policy.namespace}:v{epoch}:{suffix}"


def cache_get_or_set_swr[T](
    *,
    domain: str,
    key_suffix: str,
    producer: Callable[[], T],
    soft_ttl: int | None = None,
    hard_ttl: int | None = None,
) -> T:
    """دریافت یا محاسبهٔ مقدار کش با الگوی Stale-While-Revalidate و قفل ضد هجوم."""
    policy = get_cache_policy(domain)
    effective_soft = soft_ttl if soft_ttl is not None else policy.soft_ttl
    effective_hard = hard_ttl if hard_ttl is not None else policy.hard_ttl
    full_key = build_versioned_key(domain, key_suffix)
    lock_key = f"{full_key}:lock"
    now = time.time()

    cached_envelope = _safe_get(full_key)
    if isinstance(cached_envelope, dict) and "value" in cached_envelope:
        soft_expires_at = float(cached_envelope.get("soft_expires_at", 0.0))
        if now < soft_expires_at:
            return cached_envelope["value"]  # type: ignore[no-any-return]

        # در بازهٔ Stale هستیم: اگر قفل بازسازی در دست درخواست دیگری است، مقدار قبلی را بده
        if not _safe_add(lock_key, 1, timeout=policy.lock_ttl):
            return cached_envelope["value"]  # type: ignore[no-any-return]

        try:
            fresh_value = producer()
            _safe_set(
                full_key,
                {
                    "value": fresh_value,
                    "soft_expires_at": time.time() + effective_soft,
                },
                timeout=effective_hard,
            )
            return fresh_value
        except Exception:
            logger.warning("swr_producer_failed_serving_stale key=%s", full_key)
            return cached_envelope["value"]  # type: ignore[no-any-return]

    # Cache miss کامل
    fresh_value = producer()
    _safe_set(
        full_key,
        {
            "value": fresh_value,
            "soft_expires_at": time.time() + effective_soft,
        },
        timeout=effective_hard,
    )
    return fresh_value

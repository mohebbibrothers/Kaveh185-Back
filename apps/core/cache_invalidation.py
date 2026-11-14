"""ابطال کش رویدادمحور همراه با الگوی Durable Outbox برای همگام‌سازی فرانت‌اند و بک‌اند.

وقتی کاربری آزمون را به پایان می‌رساند یا ادمین تنظیمات/مساجد را تغییر می‌دهد:
۱) نسخهٔ Epoch دامنه در کش بک‌اند به‌صورت اتمیک افزایش می‌یابد.
۲) در صورت فعال بودن Outbox، یک رکورد `CacheInvalidationEvent` ثبت می‌شود تا حتی
   اگر سرور فرانت‌اند موقتاً در دسترس نباشد، بازاعتبارسنجی تگ‌ها و مسیرها از دست نرود.
"""

from __future__ import annotations

import logging

import requests
from django.conf import settings
from django.utils import timezone

from .cache import bump_epoch
from .cache_policy import get_cache_policy
from .choices import CacheInvalidationStatus
from .models import CacheInvalidationEvent

logger = logging.getLogger("apps.core.cache")


def invalidate_domain_cache(
    domain: str,
    *,
    reason: str = "",
    record_outbox: bool = True,
) -> int:
    """ابطال فوری کش یک دامنه در بک‌اند و ثبت رخداد بازاعتبارسنجی برای فرانت‌اند."""
    policy = get_cache_policy(domain)
    new_epoch = bump_epoch(domain)

    if record_outbox and getattr(settings, "CACHE_INVALIDATION_OUTBOX_ENABLED", True):
        CacheInvalidationEvent.objects.create(
            domain=domain,
            reason=reason[:160],
            tags=list(policy.frontend_tags),
            paths=list(policy.frontend_paths),
            status=CacheInvalidationStatus.PENDING,
        )
    return new_epoch


def process_invalidation_event(event: CacheInvalidationEvent) -> bool:
    """پردازش یک رکورد `CacheInvalidationEvent` و ارسال درخواست بازاعتبارسنجی به فرانت‌اند."""
    max_attempts = int(getattr(settings, "CACHE_INVALIDATION_MAX_ATTEMPTS", 10))
    reval_enabled = bool(getattr(settings, "FRONTEND_REVALIDATION_ENABLED", False))
    reval_url = str(getattr(settings, "FRONTEND_REVALIDATION_URL", "")).strip()
    reval_secret = str(getattr(settings, "FRONTEND_REVALIDATION_SECRET", "")).strip()
    timeout = int(getattr(settings, "FRONTEND_REVALIDATION_TIMEOUT", 5))

    event.status = CacheInvalidationStatus.PROCESSING
    event.attempts += 1
    event.save(update_fields=["status", "attempts", "updated_at"])

    if not reval_enabled or not reval_url:
        event.status = CacheInvalidationStatus.SUCCEEDED
        event.processed_at = timezone.now()
        event.last_error = ""
        event.save(update_fields=["status", "processed_at", "last_error", "updated_at"])
        return True

    try:
        headers = {"Content-Type": "application/json"}
        if reval_secret:
            headers["X-Revalidate-Secret"] = reval_secret
        resp = requests.post(
            reval_url,
            json={"tags": event.tags, "paths": event.paths, "domain": event.domain},
            headers=headers,
            timeout=timeout,
        )
        resp.raise_for_status()
        event.status = CacheInvalidationStatus.SUCCEEDED
        event.processed_at = timezone.now()
        event.last_error = ""
        event.save(update_fields=["status", "processed_at", "last_error", "updated_at"])
        return True
    except Exception as exc:
        event.last_error = str(exc)[:500]
        if event.attempts >= max_attempts:
            event.status = CacheInvalidationStatus.DEAD
        else:
            event.status = CacheInvalidationStatus.FAILED
        event.save(update_fields=["status", "last_error", "updated_at"])
        logger.warning(
            "frontend_revalidation_failed event_id=%s attempts=%s err=%s",
            event.id,
            event.attempts,
            exc,
        )
        return False


def process_pending_invalidation_batch(*, limit: int = 100) -> dict[str, int]:
    """پردازش دسته‌ای رخدادهای معوق ابطال کش."""
    events = list(
        CacheInvalidationEvent.objects.filter(
            status__in=[CacheInvalidationStatus.PENDING, CacheInvalidationStatus.FAILED],
        ).order_by("created_at", "id")[:limit]
    )
    succeeded = 0
    failed = 0
    for event in events:
        if process_invalidation_event(event):
            succeeded += 1
        else:
            failed += 1
    return {"processed": len(events), "succeeded": succeeded, "failed": failed}

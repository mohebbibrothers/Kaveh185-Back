"""تسک‌های پس‌زمینهٔ Celery برای پردازش Outbox کش، پیام‌ها و پاک‌سازی کلیدهای منقضی."""

from __future__ import annotations

from celery import shared_task

from .cache_invalidation import process_pending_invalidation_batch
from .idempotency import purge_expired_keys
from .outbox import relay_pending_outbox


@shared_task(name="apps.core.tasks.process_pending_cache_invalidation_events_task")
def process_pending_cache_invalidation_events_task(limit: int = 100) -> dict[str, int]:
    """پردازش دسته‌ای رخدادهای ابطال کش فرانت‌اند."""
    return process_pending_invalidation_batch(limit=limit)


@shared_task(name="apps.core.tasks.relay_pending_outbox_task")
def relay_pending_outbox_task(limit: int = 100) -> dict[str, int]:
    """تحویل پیام‌های معوق در جدول Transactional Outbox."""
    return relay_pending_outbox(limit=limit)


@shared_task(name="apps.core.tasks.purge_expired_idempotency_keys_task")
def purge_expired_idempotency_keys_task(batch: int = 1000) -> int:
    """پاک‌سازی کلیدهای هم‌توانی منقضی‌شده."""
    return purge_expired_keys(batch=batch)

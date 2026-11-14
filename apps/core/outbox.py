"""الگوی Transactional Outbox برای ارسال تضمین‌شدهٔ پیامک‌ها و رویدادهای دامنه‌ای.

چرا این الگو:
    پایان دادن به آزمون و صدور کارنامه هرگز نباید به خاطر قطعی یا کندی لحظه‌ای
    پنل پیامکی شکست بخورد. پیام در همان تراکنش دیتابیس در جدول `OutboxMessage`
    ثبت شده و سپس به‌صورت ایمن ارسال می‌شود.
"""

from __future__ import annotations

import logging
from typing import Any

from django.conf import settings
from django.utils import timezone

from .choices import OutboxStatus
from .models import OutboxMessage

logger = logging.getLogger("apps.core")


def enqueue_outbox(
    *,
    topic: str,
    recipient: str,
    payload: dict[str, Any],
    deliver_immediately: bool = True,
) -> OutboxMessage:
    """ثبت یک پیام در جدول Transactional Outbox و تلاش برای تحویل فوری ایمن."""
    message = OutboxMessage.objects.create(
        topic=topic,
        recipient=recipient,
        payload=payload,
        status=OutboxStatus.PENDING,
        scheduled_at=timezone.now(),
    )
    if deliver_immediately and getattr(settings, "OUTBOX_INLINE_DISPATCH", True):
        dispatch_outbox_message(message)
    return message


def dispatch_outbox_message(message: OutboxMessage) -> bool:
    """تحویل یک پیام از جدول Outbox به سرویس مقصد (مانند درگاه پیامک)."""
    from apps.notifications.services import deliver_outbox_sms

    max_attempts = int(getattr(settings, "OUTBOX_MAX_ATTEMPTS", 5))
    message.status = OutboxStatus.PROCESSING
    message.attempts += 1
    message.save(update_fields=["status", "attempts", "updated_at"])

    try:
        if message.topic.startswith("sms."):
            deliver_outbox_sms(message)
        message.status = OutboxStatus.SENT
        message.processed_at = timezone.now()
        message.last_error = ""
        message.save(update_fields=["status", "processed_at", "last_error", "updated_at"])
        return True
    except Exception as exc:
        message.last_error = str(exc)[:500]
        message.status = (
            OutboxStatus.DEAD if message.attempts >= max_attempts else OutboxStatus.FAILED
        )
        message.save(update_fields=["status", "last_error", "updated_at"])
        logger.warning(
            "outbox_dispatch_failed id=%s topic=%s err=%s",
            message.id,
            message.topic,
            exc,
        )
        return False


def relay_pending_outbox(*, limit: int = 100) -> dict[str, int]:
    """پردازش دسته‌ای پیام‌های معوق در جدول Outbox."""
    now = timezone.now()
    rows = list(
        OutboxMessage.objects.filter(
            status__in=[OutboxStatus.PENDING, OutboxStatus.FAILED],
            scheduled_at__lte=now,
        ).order_by("scheduled_at", "id")[:limit]
    )
    sent = 0
    failed = 0
    for row in rows:
        if dispatch_outbox_message(row):
            sent += 1
        else:
            failed += 1
    return {"processed": len(rows), "sent": sent, "failed": failed}

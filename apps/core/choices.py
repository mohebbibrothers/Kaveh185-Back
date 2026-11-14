"""مقادیر ثابت و انتخاب‌های وضعیت در لایهٔ زیرساخت مشترک (Core)."""

from __future__ import annotations

from django.db import models


class CacheInvalidationStatus(models.TextChoices):
    """وضعیت پردازش رخدادهای ابطال کش در الگوی Outbox."""

    PENDING = "pending", "در انتظار پردازش"
    PROCESSING = "processing", "در حال پردازش"
    SUCCEEDED = "succeeded", "موفق"
    FAILED = "failed", "ناموفق (قابل تلاش مجدد)"
    DEAD = "dead", "متوقف‌شده (نیازمند بررسی ادمین)"


class OutboxStatus(models.TextChoices):
    """وضعیت تحویل پیام‌ها در الگوی Transactional Outbox."""

    PENDING = "pending", "در صف ارسال"
    PROCESSING = "processing", "در حال ارسال"
    SENT = "sent", "ارسال‌شده"
    FAILED = "failed", "خطا در ارسال"
    DEAD = "dead", "غیرقابل ارسال"


class IdempotencyOutcome(models.TextChoices):
    """نتیجهٔ بررسی کلید هم‌توانی (`Idempotency-Key`)."""

    RESERVED = "reserved", "کلید رزرو شد — عملیات اجرا شود"
    REPLAY = "replay", "پاسخ قبلی بازپخش شود"
    CONFLICT = "conflict", "تعارض کلید با درخواست متفاوت"
    IN_PROGRESS = "in_progress", "درخواست هم‌زمان در حال پردازش است"

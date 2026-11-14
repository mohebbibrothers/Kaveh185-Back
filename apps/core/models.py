"""مدل‌های زیرساختی مشترک برای کل پروژهٔ کاوه ۱۸۵ (Kaveh185).

شامل:
- `BaseModel`: مدل پایه با زمان‌های ایجاد/ویرایش و رفتار حذف نرم (Soft Delete).
- `CacheInvalidationEvent`: جدول Outbox پایدار برای ابطال مطمئن کش فرانت‌اند.
- `IdempotencyKey`: ذخیرهٔ اثر انگشت و پاسخ درخواست‌ها برای تضمین «یک‌بار اثر».
- `OutboxMessage`: جدول Transactional Outbox برای ارسال تضمین‌شدهٔ پیامک و رخدادها.
"""

from __future__ import annotations

from typing import Any

from django.db import models
from django.utils import timezone

from .choices import CacheInvalidationStatus, OutboxStatus


class SoftDeleteQuerySet(models.QuerySet):
    """کوئری‌ست پشتیبان حذف نرم (`is_active=False`) و حذف فیزیکی صریح (`hard_delete`)."""

    def active(self) -> SoftDeleteQuerySet:
        """فیلتر کردن فقط رکوردهای فعال."""
        return self.filter(is_active=True)

    def soft_delete(self) -> int:
        """غیرفعال کردن دسته‌ای رکوردها بدون حذف فیزیکی از دیتابیس."""
        return self.update(is_active=False, updated_at=timezone.now())

    def hard_delete(self) -> tuple[int, dict[str, int]]:
        """حذف فیزیکی واقعی رکوردها از دیتابیس."""
        return super().delete()


class ActiveManager(models.Manager):
    """منیجر پیش‌فرض مدل‌های پایه با دسترسی به متدهای حذف نرم."""

    def get_queryset(self) -> SoftDeleteQuerySet:
        """بازگرداندن SoftDeleteQuerySet."""
        return SoftDeleteQuerySet(self.model, using=self._db)


class BaseModel(models.Model):
    """مدل انتزاعی پایه برای تمام مدل‌های دامنهٔ کاوه ۱۸۵."""

    created_at = models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="تاریخ ایجاد")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="تاریخ به‌روزرسانی")
    is_active = models.BooleanField(default=True, db_index=True, verbose_name="فعال")

    objects = ActiveManager()
    all_objects = models.Manager()  # noqa: DJ012

    class Meta:
        abstract = True
        ordering = ["-created_at", "-id"]

    def soft_delete(self) -> None:
        """غیرفعال کردن نرم رکورد جاری."""
        self.is_active = False
        self.save(update_fields=["is_active", "updated_at"])


class CacheInvalidationEvent(BaseModel):
    """رخداد ابطال کش پایدار (Durable Outbox) برای همگام‌سازی کش بک‌اند و فرانت‌اند."""

    domain = models.CharField(max_length=64, db_index=True, verbose_name="دامنه کش")
    reason = models.CharField(max_length=160, blank=True, default="", verbose_name="دلیل ابطال")
    tags = models.JSONField(default=list, blank=True, verbose_name="تگ‌های فرانت‌اند")
    paths = models.JSONField(default=list, blank=True, verbose_name="مسیرهای فرانت‌اند")
    status = models.CharField(
        max_length=24,
        choices=CacheInvalidationStatus.choices,
        default=CacheInvalidationStatus.PENDING,
        db_index=True,
        verbose_name="وضعیت",
    )
    attempts = models.PositiveSmallIntegerField(default=0, verbose_name="تعداد تلاش")
    last_error = models.TextField(blank=True, default="", verbose_name="آخرین خطا")
    processed_at = models.DateTimeField(null=True, blank=True, verbose_name="زمان پردازش")

    class Meta:
        verbose_name = "رخداد ابطال کش"
        verbose_name_plural = "رخدادهای ابطال کش"
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["status", "created_at"], name="cache_inv_status_created_idx"),
        ]

    def __str__(self) -> str:
        """نمایش متنی رخداد ابطال کش."""
        return f"{self.domain}:{self.status} ({self.id})"


class IdempotencyKey(BaseModel):
    """ذخیرهٔ کلیدهای هم‌توانی (`Idempotency-Key`) برای جلوگیری از اجرای تکراری عملیات نوشتن."""

    key = models.CharField(max_length=128, verbose_name="کلید هم‌توانی")
    scope = models.CharField(max_length=128, verbose_name="دامنه/مسیر")
    actor_ref = models.CharField(max_length=64, blank=True, default="", verbose_name="شناسه کنشگر")
    request_fingerprint = models.CharField(
        max_length=64,
        blank=True,
        default="",
        verbose_name="اثر انگشت بدنه درخواست",
    )
    response_status = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        verbose_name="کد وضعیت پاسخ",
    )
    response_body = models.JSONField(null=True, blank=True, verbose_name="بدنه پاسخ ذخیره‌شده")
    locked_at = models.DateTimeField(null=True, blank=True, verbose_name="زمان قفل")
    expires_at = models.DateTimeField(db_index=True, verbose_name="زمان انقضا")

    class Meta:
        verbose_name = "کلید هم‌توانی"
        verbose_name_plural = "کلیدهای هم‌توانی"
        constraints = [
            models.UniqueConstraint(fields=["key", "scope"], name="uniq_idempotency_key_scope"),
        ]
        indexes = [
            models.Index(fields=["expires_at"], name="idem_expires_idx"),
        ]

    def __str__(self) -> str:
        """نمایش خوانای کلید هم‌توانی."""
        return f"{self.scope}:{self.key}"


class OutboxMessage(BaseModel):
    """پیام خروجی تراکنشی (Transactional Outbox) برای تضمین تحویل پیامک و رویدادها."""

    topic = models.CharField(max_length=80, db_index=True, verbose_name="موضوع پیام")
    recipient = models.CharField(max_length=64, db_index=True, verbose_name="گیرنده")
    payload: Any = models.JSONField(default=dict, blank=True, verbose_name="محتوای پیام")
    status = models.CharField(
        max_length=24,
        choices=OutboxStatus.choices,
        default=OutboxStatus.PENDING,
        db_index=True,
        verbose_name="وضعیت ارسال",
    )
    attempts = models.PositiveSmallIntegerField(default=0, verbose_name="تعداد تلاش")
    last_error = models.TextField(blank=True, default="", verbose_name="آخرین خطا")
    scheduled_at = models.DateTimeField(
        default=timezone.now, db_index=True, verbose_name="زمان‌بندی"
    )
    processed_at = models.DateTimeField(null=True, blank=True, verbose_name="زمان ارسال")

    class Meta:
        verbose_name = "پیام Outbox"
        verbose_name_plural = "پیام‌های Outbox"
        ordering = ["scheduled_at", "id"]
        indexes = [
            models.Index(fields=["status", "scheduled_at"], name="outbox_status_sched_idx"),
        ]

    def __str__(self) -> str:
        """نمایش خوانای پیام Outbox."""
        return f"{self.topic} -> {self.recipient} ({self.status})"

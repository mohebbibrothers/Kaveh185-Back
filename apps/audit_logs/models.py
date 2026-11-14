"""مدل تغییرناپذیر حسابرسی (`AuditLog`) با زنجیرهٔ هش پیوسته (Tamper-Evident Hash Chain)."""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db import models
from django.utils import timezone

from .choices import AuditAction


class ImmutableAuditQuerySet(models.QuerySet):
    """کوئری‌ست محافظت‌شده که هرگونه حذف یا ویرایش دسته‌ای لاگ‌های حسابرسی را مسدود می‌کند."""

    def update(self, **kwargs: Any) -> int:
        """جلوگیری از ویرایش دسته‌ای رکوردهای حسابرسی."""
        del kwargs
        raise PermissionDenied("رکوردهای حسابرسی تغییرناپذیر هستند و امکان ویرایش ندارند.")

    def delete(self) -> tuple[int, dict[str, int]]:
        """جلوگیری از حذف دسته‌ای رکوردهای حسابرسی."""
        raise PermissionDenied("رکوردهای حسابرسی غیرقابل‌حذف هستند.")


class AuditLog(models.Model):
    """رکورد حسابرسی فارنزیک با پیوند زنجیرهٔ هش SHA-256 به رکورد قبلی."""

    chain_index = models.PositiveBigIntegerField(
        unique=True, db_index=True, verbose_name="شماره زنجیره"
    )
    hash_version = models.PositiveSmallIntegerField(default=1, verbose_name="نسخه الگوریتم هش")
    previous_hash = models.CharField(max_length=64, verbose_name="هش رکورد قبلی")
    event_hash = models.CharField(
        max_length=64, unique=True, db_index=True, verbose_name="هش این رخداد"
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
        verbose_name="کاربر کنشگر",
    )
    actor_label = models.CharField(
        max_length=160, blank=True, default="", verbose_name="عنوان کنشگر"
    )
    action = models.CharField(
        max_length=64,
        choices=AuditAction.choices,
        db_index=True,
        verbose_name="نوع عملیات",
    )
    resource_type = models.CharField(max_length=64, db_index=True, verbose_name="نوع منبع")
    resource_id = models.CharField(max_length=64, db_index=True, verbose_name="شناسه منبع")
    reason = models.CharField(max_length=300, blank=True, default="", verbose_name="دلیل ثبت‌شده")

    ip_address = models.CharField(max_length=64, blank=True, default="", verbose_name="آدرس IP")
    user_agent = models.CharField(
        max_length=300, blank=True, default="", verbose_name="مرورگر/دستگاه"
    )
    path = models.CharField(max_length=255, blank=True, default="", verbose_name="مسیر HTTP")
    method = models.CharField(max_length=16, blank=True, default="", verbose_name="متد HTTP")
    request_id = models.CharField(
        max_length=64, blank=True, default="", db_index=True, verbose_name="شناسه درخواست"
    )

    changes: Any = models.JSONField(default=dict, blank=True, verbose_name="تغییرات")
    extra_data: Any = models.JSONField(default=dict, blank=True, verbose_name="داده‌های تکمیلی")
    created_at = models.DateTimeField(default=timezone.now, db_index=True, verbose_name="زمان ثبت")

    objects = ImmutableAuditQuerySet.as_manager()

    class Meta:
        verbose_name = "لاگ حسابرسی"
        verbose_name_plural = "لاگ‌های حسابرسی"
        ordering = ["-chain_index"]
        indexes = [
            models.Index(fields=["action", "created_at"], name="audit_action_created_idx"),
            models.Index(fields=["resource_type", "resource_id"], name="audit_resource_lookup_idx"),
        ]

    def __str__(self) -> str:
        """نمایش متنی رکورد حسابرسی."""
        return f"#{self.chain_index} {self.action} [{self.resource_type}:{self.resource_id}]"

    def save(self, *args: Any, **kwargs: Any) -> None:
        """اجازهٔ درج فقط برای رکورد جدید و مسدود کردن هرگونه تغییر پس از ایجاد."""
        if self.pk is not None:
            raise PermissionDenied("رکوردهای حسابرسی پس از ثبت غیرقابل‌ویرایش هستند.")
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        """مسدود کردن حذف تک‌رکوردی لاگ‌های حسابرسی."""
        del args, kwargs
        raise PermissionDenied("رکوردهای حسابرسی غیرقابل‌حذف هستند.")

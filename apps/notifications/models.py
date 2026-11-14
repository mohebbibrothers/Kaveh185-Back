"""مدل لاگ ارسال پیامک‌های سامانه کاوه ۱۸۵."""

from __future__ import annotations

from django.db import models

from apps.core.models import BaseModel

from .choices import SMSCategory, SMSDeliveryStatus


class SMSDeliveryLog(BaseModel):
    """رکورد ممیزی و وضعیت ارسال هر پیامک در سامانه."""

    recipient_phone = models.CharField(
        max_length=15,
        db_index=True,
        verbose_name="شماره موبایل گیرنده",
    )
    category = models.CharField(
        max_length=24,
        choices=SMSCategory.choices,
        default=SMSCategory.THANK_YOU,
        db_index=True,
        verbose_name="نوع پیامک",
    )
    provider = models.CharField(
        max_length=32,
        default="console",
        verbose_name="درگاه پیامکی",
    )
    message_text = models.TextField(verbose_name="متن پیامک")
    status = models.CharField(
        max_length=16,
        choices=SMSDeliveryStatus.choices,
        default=SMSDeliveryStatus.SENT,
        db_index=True,
        verbose_name="وضعیت ارسال",
    )
    provider_message_id = models.CharField(
        max_length=120,
        blank=True,
        default="",
        verbose_name="شناسه رهگیری درگاه",
    )
    error_message = models.TextField(
        blank=True,
        default="",
        verbose_name="پیام خطا",
    )

    class Meta:
        verbose_name = "لاگ ارسال پیامک"
        verbose_name_plural = "لاگ‌های ارسال پیامک"
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        """نمایش خوانای لاگ پیامک."""
        return f"SMS[{self.category}] -> {self.recipient_phone} ({self.status})"

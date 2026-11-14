"""مقادیر ثابت دسته‌بندی و وضعیت ارسال پیامک‌ها."""

from __future__ import annotations

from django.db import models


class SMSCategory(models.TextChoices):
    """نوع پیامک ارسالی در سامانه کاوه ۱۸۵."""

    OTP = "otp", "کد تایید یک‌بارمصرف (OTP)"
    THANK_YOU = "thank_you", "پیامک تشکر پایان آزمون و لینک کانال‌ها"
    ANNOUNCEMENT = "announcement", "اطلاع‌رسانی عمومی / قرعه‌کشی"


class SMSDeliveryStatus(models.TextChoices):
    """وضعیت تحویل پیامک در درگاه پیامکی."""

    SENT = "sent", "ارسال‌شده"
    FAILED = "failed", "خطا در ارسال"

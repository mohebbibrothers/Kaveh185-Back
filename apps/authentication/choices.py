"""مقادیر ثابت نقش‌های کاربری، اهداف OTP و سیگنال‌های ریسک در کاوه ۱۸۵."""

from __future__ import annotations

from django.db import models


class UserRole(models.TextChoices):
    """نقش‌های دسترسی کاربران در سامانهٔ کاوه ۱۸۵."""

    PARTICIPANT = "participant", "شرکت‌کننده در مسابقه"
    OPERATOR = "operator", "اپراتور / پشتیبان"
    ADMIN = "admin", "مدیر کل سامانه"


class OTPPurpose(models.TextChoices):
    """هدف ارسال کد یک‌بارمصرف پیامکی (OTP)."""

    REGISTER = "register", "ثبت‌نام و ورود به آزمون"
    LOGIN = "login", "ورود به حساب"


class RiskSignalType(models.TextChoices):
    """انواع سیگنال‌های ریسک امنیتی و ضدتقلب."""

    IP_CHANGE_DURING_EXAM = "ip_change_during_exam", "تغییر ناگهانی IP در حین آزمون"
    RAPID_ANSWERING = "rapid_answering", "پاسخ‌دهی غیرطبیعی و فوق‌سریع به سوالات"
    EXCESSIVE_OTP_ATTEMPTS = "excessive_otp_attempts", "تلاش‌های مکرر ناموفق OTP"
    MULTI_DEVICE_CONFLICT = "multi_device_conflict", "تلاش هم‌زمان از چند دستگاه"


class RiskSeverity(models.TextChoices):
    """شدت سیگنال ریسک امنیتی."""

    LOW = "low", "کم"
    MEDIUM = "medium", "متوسط"
    HIGH = "high", "بالا"

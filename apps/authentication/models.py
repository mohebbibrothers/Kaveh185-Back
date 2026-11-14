"""مدل‌های هویت کاربران، چالش‌های OTP، نشست‌های فعال (`AuthSession`) و سیگنال‌های ریسک."""

from __future__ import annotations

import uuid
from typing import Any

from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models
from django.utils import timezone

from apps.core.crypto import blind_index, encrypt_pii, mask_national_id, mask_phone
from apps.core.jalali import calculate_age, format_jalali_date
from apps.core.models import BaseModel
from apps.core.uuid7 import uuid7

from .choices import OTPPurpose, RiskSeverity, RiskSignalType, UserRole
from .managers import UserManager


class User(AbstractBaseUser, PermissionsMixin):
    """مدل اصلی کاربر و شرکت‌کننده در سامانهٔ مسابقه کاوه ۱۸۵."""

    phone_number = models.CharField(
        max_length=15,
        unique=True,
        db_index=True,
        verbose_name="شماره تماس",
    )
    national_id = models.CharField(
        max_length=10,
        unique=True,
        db_index=True,
        verbose_name="کد ملی",
    )
    national_id_encrypted = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name="کد ملی رمزنگاری‌شده (AES-GCM)",
    )
    national_id_hash = models.CharField(
        max_length=64,
        blank=True,
        default="",
        db_index=True,
        verbose_name="ایندکس کور کد ملی (HMAC-SHA256)",
    )
    first_name = models.CharField(max_length=80, verbose_name="نام")
    last_name = models.CharField(max_length=100, verbose_name="نام خانوادگی")
    birth_date = models.DateField(null=True, blank=True, db_index=True, verbose_name="تاریخ تولد")

    mosque = models.ForeignKey(
        "mosques.Mosque",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="participants",
        verbose_name="مسجد انتخابی",
    )

    role = models.CharField(
        max_length=24,
        choices=UserRole.choices,
        default=UserRole.PARTICIPANT,
        db_index=True,
        verbose_name="نقش کاربر",
    )
    is_phone_verified = models.BooleanField(default=False, verbose_name="تأیید تلفن همراه")
    is_active = models.BooleanField(default=True, db_index=True, verbose_name="فعال")
    is_staff = models.BooleanField(default=False, verbose_name="دسترسی پنل ادمین")

    mfa_enabled = models.BooleanField(default=False, verbose_name="فعال بودن TOTP دومرحله‌ای")
    mfa_secret_encrypted = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name="راز رمزنگاری‌شدهٔ TOTP",
    )
    mfa_recovery_codes: Any = models.JSONField(
        default=list,
        blank=True,
        verbose_name="هش کدهای بازیابی MFA",
    )

    created_at = models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="زمان ثبت‌نام")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="آخرین ویرایش")

    objects = UserManager()

    USERNAME_FIELD = "phone_number"
    REQUIRED_FIELDS = ["national_id", "first_name", "last_name"]

    class Meta:
        verbose_name = "کاربر / شرکت‌کننده"
        verbose_name_plural = "کاربران و شرکت‌کنندگان"
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["phone_number"], name="uniq_user_phone_number"),
            models.UniqueConstraint(fields=["national_id"], name="uniq_user_national_id"),
        ]
        indexes = [
            models.Index(fields=["mosque", "is_active"], name="user_mosque_active_idx"),
            models.Index(fields=["role", "is_active"], name="user_role_active_idx"),
        ]

    def save(self, *args: Any, **kwargs: Any) -> None:
        """همگام‌سازی خودکار فیلدهای رمزنگاری و ایندکس کور کدملی پیش از ذخیره."""
        if self.national_id:
            self.national_id_hash = blind_index(self.national_id, purpose="national_id")
            if not self.national_id_encrypted:
                self.national_id_encrypted = encrypt_pii(self.national_id)
        super().save(*args, **kwargs)

    @property
    def full_name(self) -> str:
        """نام و نام خانوادگی کامل کاربر."""
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def birth_date_jalali(self) -> str:
        """نمایش شمسی تاریخ تولد کاربر (`1382/06/15`)."""
        return format_jalali_date(self.birth_date)

    @property
    def age(self) -> int | None:
        """محاسبهٔ سن کامل کاربر به سال."""
        return calculate_age(self.birth_date)

    @property
    def age_years(self) -> int | None:
        """نام مستعار برای سن کامل کاربر به سال."""
        return self.age

    @property
    def national_id_masked(self) -> str:
        """کدملی پوشانده‌شده برای نمایش عمومی."""
        return mask_national_id(self.national_id)

    @property
    def phone_masked(self) -> str:
        """شماره تماس پوشانده‌شده برای نمایش عمومی."""
        return mask_phone(self.phone_number)

    def __str__(self) -> str:
        """نمایش متنی کاربر."""
        return f"{self.full_name} ({self.phone_number})"


class OTPChallenge(BaseModel):
    """رکورد چالش کد یک‌بارمصرف (OTP) با هش نمک‌دار (Salted SHA-256)."""

    phone_number = models.CharField(max_length=15, db_index=True, verbose_name="شماره تماس")
    purpose = models.CharField(
        max_length=24,
        choices=OTPPurpose.choices,
        default=OTPPurpose.REGISTER,
        verbose_name="هدف OTP",
    )
    code_salt = models.CharField(max_length=32, verbose_name="نمک هش کد")
    code_hash = models.CharField(max_length=64, verbose_name="هش کد OTP")
    attempts = models.PositiveSmallIntegerField(default=0, verbose_name="تعداد تلاش ناموفق")
    is_verified = models.BooleanField(default=False, db_index=True, verbose_name="تأییدشده")
    expires_at = models.DateTimeField(db_index=True, verbose_name="زمان انقضا")
    verified_at = models.DateTimeField(null=True, blank=True, verbose_name="زمان تأیید")
    ip_address = models.CharField(
        max_length=64, blank=True, default="", verbose_name="IP درخواست‌کننده"
    )

    class Meta:
        verbose_name = "چالش OTP"
        verbose_name_plural = "چالش‌های OTP"
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(
                fields=["phone_number", "is_verified", "expires_at"], name="otp_lookup_idx"
            ),
        ]

    def __str__(self) -> str:
        """نمایش خوانای چالش OTP."""
        return f"OTP {self.phone_number} ({self.purpose})"


class AuthSession(BaseModel):
    """نشست کاربری مقید به توکن JWT (`sid`) با قابلیت مشاهدهٔ دستگاه و ابطال آنی."""

    session_uid = models.UUIDField(
        default=uuid7,
        unique=True,
        editable=False,
        db_index=True,
        verbose_name="شناسه یکتای نشست (sid)",
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="auth_sessions",
        verbose_name="کاربر",
    )
    refresh_jti = models.CharField(
        max_length=64,
        blank=True,
        default="",
        db_index=True,
        verbose_name="شناسه توکن Refresh (jti)",
    )
    device_label = models.CharField(
        max_length=120, blank=True, default="", verbose_name="برچسب دستگاه"
    )
    user_agent = models.CharField(max_length=300, blank=True, default="", verbose_name="User-Agent")
    ip_address = models.CharField(max_length=64, blank=True, default="", verbose_name="آدرس IP")
    network_prefix = models.CharField(
        max_length=64, blank=True, default="", verbose_name="پیشوند شبکه"
    )
    last_seen_at = models.DateTimeField(
        default=timezone.now, db_index=True, verbose_name="آخرین فعالیت"
    )
    mfa_verified_at = models.DateTimeField(
        null=True, blank=True, verbose_name="زمان آخرین تأیید MFA"
    )
    is_revoked = models.BooleanField(default=False, db_index=True, verbose_name="باطل‌شده")
    revoked_at = models.DateTimeField(null=True, blank=True, verbose_name="زمان ابطال")
    revoked_reason = models.CharField(
        max_length=160, blank=True, default="", verbose_name="دلیل ابطال"
    )

    class Meta:
        verbose_name = "نشست کاربری"
        verbose_name_plural = "نشست‌های کاربری"
        ordering = ["-last_seen_at", "-id"]
        indexes = [
            models.Index(
                fields=["user", "is_revoked", "-last_seen_at"], name="session_user_active_idx"
            ),
        ]

    def __str__(self) -> str:
        """نمایش خوانای نشست کاربری."""
        status_str = "revoked" if self.is_revoked else "active"
        return f"{self.user_id}:{self.session_uid} ({status_str})"

    @property
    def sid_str(self) -> str:
        """نمایش رشته‌ای `session_uid`."""
        val: uuid.UUID | str = self.session_uid
        return str(val)


class AuthRiskSignal(BaseModel):
    """سیگنال‌های ریسک امنیتی و ناهنجاری‌های رفتاری (قابل بررسی توسط ادمین)."""

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="risk_signals",
        verbose_name="کاربر مرتبط",
    )
    signal_type = models.CharField(
        max_length=48,
        choices=RiskSignalType.choices,
        db_index=True,
        verbose_name="نوع سیگنال",
    )
    severity = models.CharField(
        max_length=16,
        choices=RiskSeverity.choices,
        default=RiskSeverity.MEDIUM,
        db_index=True,
        verbose_name="شدت ریسک",
    )
    ip_address = models.CharField(max_length=64, blank=True, default="", verbose_name="آدرس IP")
    details: Any = models.JSONField(default=dict, blank=True, verbose_name="جزئیات فنی")
    is_reviewed = models.BooleanField(
        default=False, db_index=True, verbose_name="بررسی‌شده توسط ادمین"
    )
    reviewed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_risk_signals",
        verbose_name="بررسی‌کننده",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True, verbose_name="زمان بررسی")
    review_note = models.CharField(
        max_length=300, blank=True, default="", verbose_name="یادداشت بررسی"
    )

    class Meta:
        verbose_name = "سیگنال ریسک امنیتی"
        verbose_name_plural = "سیگنال‌های ریسک امنیتی"
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        """نمایش خوانای سیگنال ریسک."""
        return f"{self.signal_type} ({self.severity}) user={self.user_id}"

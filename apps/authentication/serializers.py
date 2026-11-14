"""سریالایزرهای ورودی و خروجی برای ثبت‌نام، ورود، پروفایل، نشست‌ها، MFA و مدیریت کاربران."""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

from .models import AuthRiskSignal, AuthSession, User
from .validators import (
    normalize_and_validate_national_id,
    normalize_and_validate_phone,
    parse_and_validate_birth_date,
)


class ParticipantRegistrationInputSerializer(serializers.Serializer):
    """قرارداد ورودی ثبت‌نام و ورود شرکت‌کنندگان در مسابقه کاوه ۱۸۵."""

    first_name = serializers.CharField(
        max_length=80,
        help_text="نام کوچک شرکت‌کننده (مثلاً علی)",
    )
    last_name = serializers.CharField(
        max_length=100,
        help_text="نام خانوادگی شرکت‌کننده (مثلاً محمدی)",
    )
    national_id = serializers.CharField(
        max_length=16,
        help_text="کد ملی ۱۰ رقمی معتبر ایران (یکتا برای هر نفر)",
    )
    phone_number = serializers.CharField(
        max_length=20,
        help_text="شماره تلفن همراه (مثلاً 09123456789 — یکتا برای هر نفر)",
    )
    birth_date = serializers.CharField(
        max_length=20,
        help_text="تاریخ تولد به شمسی (مثلاً 1382/06/15) یا میلادی (2003-09-06)",
    )
    mosque_id = serializers.IntegerField(
        help_text="شناسه مسجد انتخابی از لیست کشویی مساجد حوزه ۱۸۵ شهید کاوه",
    )

    def validate_national_id(self, value: str) -> str:
        """نرمال‌سازی و بررسی صحت الگوریتم کدملی."""
        return normalize_and_validate_national_id(value)

    def validate_phone_number(self, value: str) -> str:
        """نرمال‌سازی و بررسی صحت شماره موبایل."""
        return normalize_and_validate_phone(value)

    def validate_birth_date(self, value: str) -> Any:
        """پارس و بررسی بازهٔ تاریخ تولد."""
        return parse_and_validate_birth_date(value)


class UserProfileOutputSerializer(serializers.ModelSerializer):
    """سریالایزر خروجی پروفایل کاربر به همراه مسجد و وضعیت آمادگی ورود به آزمون."""

    full_name = serializers.CharField(read_only=True)
    birth_date_jalali = serializers.CharField(read_only=True)
    age = serializers.IntegerField(read_only=True)
    mosque_id = serializers.IntegerField(read_only=True)
    mosque_name = serializers.SerializerMethodField()
    mosque_code = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "first_name",
            "last_name",
            "full_name",
            "national_id",
            "phone_number",
            "birth_date",
            "birth_date_jalali",
            "age",
            "mosque",
            "mosque_id",
            "mosque_name",
            "mosque_code",
            "role",
            "is_phone_verified",
            "mfa_enabled",
            "created_at",
        ]

    def get_mosque_name(self, obj: User) -> str | None:
        """نام مسجد انتخاب‌شده توسط کاربر."""
        return obj.mosque.name if obj.mosque else None

    def get_mosque_code(self, obj: User) -> str | None:
        """کد مسجد انتخاب‌شده توسط کاربر."""
        return obj.mosque.code if obj.mosque else None


class ProfileUpdateInputSerializer(serializers.Serializer):
    """سریالایزر ویرایش اطلاعات هویتی و مسجد پیش از شروع آزمون."""

    first_name = serializers.CharField(max_length=80, required=False)
    last_name = serializers.CharField(max_length=100, required=False)
    birth_date = serializers.CharField(max_length=20, required=False)
    mosque_id = serializers.IntegerField(required=False)


class OTPRequestInputSerializer(serializers.Serializer):
    """درخواست ارسال کد یک‌بارمصرف پیامکی (OTP)."""

    phone_number = serializers.CharField(max_length=20)

    def validate_phone_number(self, value: str) -> str:
        """نرمال‌سازی شماره تماس."""
        return normalize_and_validate_phone(value)


class OTPVerifyInputSerializer(serializers.Serializer):
    """تأیید کد یک‌بارمصرف پیامکی (OTP)."""

    phone_number = serializers.CharField(max_length=20)
    code = serializers.CharField(max_length=10)

    def validate_phone_number(self, value: str) -> str:
        """نرمال‌سازی شماره تماس."""
        return normalize_and_validate_phone(value)


class PasswordLoginInputSerializer(serializers.Serializer):
    """ورود با رمز عبور (مخصوص ادمین و اپراتورها)."""

    identifier = serializers.CharField(
        max_length=32,
        help_text="شماره تماس یا کدملی مدیر/اپراتور",
    )
    password = serializers.CharField(write_only=True, max_length=128)


class TokenRefreshInputSerializer(serializers.Serializer):
    """درخواست تمدید توکن دسترسی با استفاده از توکن Refresh."""

    refresh = serializers.CharField(required=False, allow_blank=True)


class AuthSessionOutputSerializer(serializers.ModelSerializer):
    """نمایش اطلاعات نشست فعال کاربر."""

    session_uid = serializers.CharField(source="sid_str", read_only=True)

    class Meta:
        model = AuthSession
        fields = [
            "id",
            "session_uid",
            "device_label",
            "ip_address",
            "network_prefix",
            "created_at",
            "last_seen_at",
            "mfa_verified_at",
            "is_revoked",
        ]


class MFACodeInputSerializer(serializers.Serializer):
    """ورودی کد ६ رقمی TOTP یا کد بازیابی."""

    code = serializers.CharField(max_length=32)


class AdminUserUpdateInputSerializer(serializers.Serializer):
    """سریالایزر ویرایش کاربر توسط ادمین."""

    first_name = serializers.CharField(max_length=80, required=False)
    last_name = serializers.CharField(max_length=100, required=False)
    birth_date = serializers.CharField(max_length=20, required=False)
    mosque_id = serializers.IntegerField(required=False)
    role = serializers.ChoiceField(
        choices=["participant", "operator", "admin"],
        required=False,
    )
    is_active = serializers.BooleanField(required=False)
    is_phone_verified = serializers.BooleanField(required=False)


class AuthRiskSignalSerializer(serializers.ModelSerializer):
    """سریالایزر نمایش سیگنال‌های ریسک امنیتی برای بررسی ادمین."""

    user_phone = serializers.SerializerMethodField()
    user_full_name = serializers.SerializerMethodField()

    class Meta:
        model = AuthRiskSignal
        fields = [
            "id",
            "user",
            "user_phone",
            "user_full_name",
            "signal_type",
            "severity",
            "ip_address",
            "details",
            "is_reviewed",
            "reviewed_by",
            "reviewed_at",
            "review_note",
            "created_at",
        ]

    def get_user_phone(self, obj: AuthRiskSignal) -> str | None:
        """شماره تماس کاربر مرتبط با سیگنال ریسک."""
        return obj.user.phone_number if obj.user else None

    def get_user_full_name(self, obj: AuthRiskSignal) -> str | None:
        """نام کامل کاربر مرتبط با سیگنال ریسک."""
        return obj.user.full_name if obj.user else None


class RiskReviewInputSerializer(serializers.Serializer):
    """ورودی ثبت یادداشت بررسی سیگنال ریسک توسط ادمین."""

    review_note = serializers.CharField(
        max_length=300, required=False, allow_blank=True, default=""
    )

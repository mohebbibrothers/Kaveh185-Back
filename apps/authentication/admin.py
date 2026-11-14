"""پیکربندی پنل ادمین جنگو برای کاربران، چالش‌های OTP، نشست‌ها و سیگنال‌های ریسک."""

from __future__ import annotations

from django.contrib import admin

from .models import AuthRiskSignal, AuthSession, OTPChallenge, User


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    """مدیریت کاربران و شرکت‌کنندگان در پنل ادمین جنگو."""

    list_display = (
        "id",
        "full_name",
        "phone_number",
        "national_id",
        "mosque",
        "role",
        "is_phone_verified",
        "is_active",
        "created_at",
    )
    list_filter = ("role", "is_active", "is_phone_verified", "mosque")
    search_fields = ("first_name", "last_name", "phone_number", "national_id")
    readonly_fields = ("national_id_hash", "created_at", "updated_at")


@admin.register(AuthSession)
class AuthSessionAdmin(admin.ModelAdmin):
    """مدیریت نشست‌های فعال کاربران در پنل ادمین جنگو."""

    list_display = (
        "id",
        "session_uid",
        "user",
        "device_label",
        "ip_address",
        "is_revoked",
        "last_seen_at",
        "created_at",
    )
    list_filter = ("is_revoked",)
    search_fields = ("user__phone_number", "user__national_id", "ip_address", "device_label")
    readonly_fields = ("session_uid", "created_at", "updated_at")


@admin.register(OTPChallenge)
class OTPChallengeAdmin(admin.ModelAdmin):
    """نمایش چالش‌های OTP در پنل ادمین جنگو."""

    list_display = (
        "id",
        "phone_number",
        "purpose",
        "is_verified",
        "attempts",
        "expires_at",
        "created_at",
    )
    list_filter = ("purpose", "is_verified")
    search_fields = ("phone_number", "ip_address")
    readonly_fields = ("code_salt", "code_hash", "created_at", "updated_at")


@admin.register(AuthRiskSignal)
class AuthRiskSignalAdmin(admin.ModelAdmin):
    """نمایش سیگنال‌های ریسک امنیتی در پنل ادمین جنگو."""

    list_display = (
        "id",
        "user",
        "signal_type",
        "severity",
        "is_reviewed",
        "ip_address",
        "created_at",
    )
    list_filter = ("signal_type", "severity", "is_reviewed")
    search_fields = ("user__phone_number", "ip_address", "review_note")
    readonly_fields = ("created_at", "updated_at")

"""کلاس‌های مجوز دسترسی (RBAC & Step-Up MFA Permissions) در سامانهٔ کاوه ۱۸۵."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.utils import timezone
from rest_framework.permissions import BasePermission

from apps.core.exceptions import ForbiddenDomainError, StepUpMfaRequiredError

from .choices import UserRole
from .constants import STEP_UP_MFA_FRESH_SECONDS


class IsAdminUser(BasePermission):
    """دسترسی مختص مدیران کل سامانه (`role=admin` یا `is_superuser=True`)."""

    message = "شما دسترسی مدیریتی (ادمین) برای انجام این عملیات را ندارید."

    def has_permission(self, request: Any, view: Any) -> bool:
        """بررسی نقش ادمین."""
        del view
        user = getattr(request, "user", None)
        return bool(
            user
            and user.is_authenticated
            and (
                getattr(user, "role", "") == UserRole.ADMIN or getattr(user, "is_superuser", False)
            )
        )


class IsOperatorOrAdmin(BasePermission):
    """دسترسی مختص اپراتورها و مدیران کل سامانه."""

    message = "این بخش فقط برای مدیران و اپراتورهای حوزه ۱۸۵ شهید کاوه مجاز است."

    def has_permission(self, request: Any, view: Any) -> bool:
        """بررسی نقش اپراتور یا ادمین."""
        del view
        user = getattr(request, "user", None)
        return bool(
            user
            and user.is_authenticated
            and (
                getattr(user, "role", "") in {UserRole.ADMIN, UserRole.OPERATOR}
                or getattr(user, "is_superuser", False)
            )
        )


IsAdminRole = IsOperatorOrAdmin


class IsParticipantProfileReady(BasePermission):
    """بررسی تکمیل بودن اطلاعات هویتی و انتخاب مسجد پیش از ورود به آزمون."""

    message = (
        "برای ورود به آزمون، تکمیل نام، کدملی، شماره تماس، تاریخ تولد و انتخاب مسجد الزامی است."
    )

    def has_permission(self, request: Any, view: Any) -> bool:
        """بررسی کامل بودن فیلدهای هویتی و مسجد انتخابی شرکت‌کننده."""
        del view
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return False
        return bool(
            user.first_name
            and user.last_name
            and user.national_id
            and user.phone_number
            and user.birth_date
            and user.mosque_id
        )


class IsVerifiedParticipant(IsParticipantProfileReady):
    """بررسی آماده بودن پروفایل شرکت‌کننده + تأیید OTP در صورتی که سوییچ زندهٔ OTP فعال باشد."""

    message = "برای شرکت در آزمون ابتدا شماره موبایل خود را با کد یک‌بارمصرف تایید نمایید."

    def has_permission(self, request: Any, view: Any) -> bool:
        """بررسی کامل بودن اطلاعات هویتی و در صورت لزوم تایید شماره موبایل."""
        if not super().has_permission(request, view):
            return False
        user = request.user
        from apps.exam.selectors import get_or_create_exam_configuration

        config = get_or_create_exam_configuration()
        if config.require_otp_before_exam and not getattr(user, "is_phone_verified", False):
            raise ForbiddenDomainError(
                "بر اساس تنظیمات فعلی آزمون، پیش از ورود به آزمون باید شماره موبایل خود را با کد OTP تایید کنید.",
                code="otp_verification_required",
            )
        return True


class HasFreshMfa(BasePermission):
    """الزام تأیید دومرحله‌ای تازه (Step-Up MFA) در صورتی که ادمین MFA را روی حسابش فعال کرده باشد."""

    message = "برای انجام این عملیات حساس، تأیید دومرحله‌ای تازه الزامی است."

    def has_permission(self, request: Any, view: Any) -> bool:
        """بررسی تازگی زمان تأیید MFA روی نشست جاری."""
        del view
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return False
        if not getattr(user, "mfa_enabled", False):
            return True
        auth_session = getattr(request, "auth_session", None)
        if auth_session is None or auth_session.mfa_verified_at is None:
            raise StepUpMfaRequiredError()
        cutoff = timezone.now() - timedelta(seconds=STEP_UP_MFA_FRESH_SECONDS)
        if auth_session.mfa_verified_at < cutoff:
            raise StepUpMfaRequiredError()
        return True

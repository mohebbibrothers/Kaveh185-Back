"""کلاس‌های محدودکنندهٔ نرخ درخواست (Rate Limiting / Throttles) برای احراز هویت."""

from __future__ import annotations

from rest_framework.throttling import AnonRateThrottle, UserRateThrottle


class RegistrationRateThrottle(AnonRateThrottle):
    """محدودکنندهٔ نرخ ثبت‌نام و ورود به آزمون."""

    scope = "auth_register"


class OTPRequestRateThrottle(AnonRateThrottle):
    """محدودکنندهٔ نرخ درخواست ارسال کد OTP."""

    scope = "auth_otp_request"


class OTPVerifyRateThrottle(AnonRateThrottle):
    """محدودکنندهٔ نرخ بررسی کد OTP (جلوگیری از Brute-Force)."""

    scope = "auth_otp_verify"


class PasswordLoginRateThrottle(AnonRateThrottle):
    """محدودکنندهٔ نرخ ورود با رمز عبور (مخصوص ادمین/اپراتور)."""

    scope = "auth_login_password"


class SessionManagementRateThrottle(UserRateThrottle):
    """محدودکنندهٔ نرخ مدیریت نشست‌های فعال."""

    scope = "auth_sessions"

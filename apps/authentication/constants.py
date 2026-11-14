"""ثابت‌های تنظیماتی ماژول احراز هویت و نشست‌ها."""

from __future__ import annotations

from typing import Final

OTP_LENGTH: Final[int] = 6
OTP_TTL_SECONDS: Final[int] = 180
OTP_MAX_VERIFY_ATTEMPTS: Final[int] = 5
SESSION_TOUCH_INTERVAL_SECONDS: Final[int] = 60
STEP_UP_MFA_FRESH_SECONDS: Final[int] = 600
SESSION_REVOKED_MESSAGE: Final[str] = (
    "نشست کاربری شما لغو شده یا منقضی شده است. لطفاً مجدداً وارد شوید."
)
ACCESS_COOKIE_NAME: Final[str] = "kaveh185_access"
REFRESH_COOKIE_NAME: Final[str] = "kaveh185_refresh"

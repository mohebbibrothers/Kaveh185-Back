"""کلاس `SessionAwareJWTAuthentication` — احراز هویت JWT مقید به نشست با پشتیبانی از هدر و کوکی.

ویژگی‌های امنیتی:
۱) هر توکن JWT دارای claimِ `sid` است که آن را به رکورد `AuthSession` متصل می‌کند.
۲) به‌محض اینکه کاربر یا ادمین یک نشست را revoke کند، توکن در اولین درخواست بعدی `401` می‌شود.
۳) فیلد `last_seen_at` نشست با آستانهٔ ۶۰ ثانیه به‌روزرسانی می‌شود.
۴) علاوه بر هدر استاندارد `Authorization: Bearer <token>`، کوکی `HttpOnly` به نام
   `kaveh185_access` نیز به عنوان fallback پشتیبانی می‌شود تا فرانت‌اند در هر دو معماری
   بتواند بدون مانع کار کند.
"""

from __future__ import annotations

from typing import Any

from drf_spectacular.contrib.rest_framework_simplejwt import SimpleJWTScheme
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication

from .constants import ACCESS_COOKIE_NAME, SESSION_REVOKED_MESSAGE


class SessionAwareJWTAuthentication(JWTAuthentication):
    """احراز هویت JWT با بررسی زنده بودن نشست (`AuthSession`) و لمس زمان آخرین فعالیت."""

    def authenticate(self, request: Any) -> Any:
        """احراز هویت از طریق هدر Authorization یا کوکی HttpOnly."""
        header = self.get_header(request)
        if header is None:
            raw_cookie = request.COOKIES.get(ACCESS_COOKIE_NAME)
            if not raw_cookie:
                return None
            raw_token = raw_cookie.encode("utf-8") if isinstance(raw_cookie, str) else raw_cookie
        else:
            raw_token = self.get_raw_token(header)
            if raw_token is None:
                return None

        validated_token = self.get_validated_token(raw_token)
        user = self.get_user(validated_token)

        from .services import validate_and_touch_session

        session_obj = validate_and_touch_session(user=user, token_claims=validated_token)
        if session_obj is None:
            raise AuthenticationFailed(SESSION_REVOKED_MESSAGE)

        request.auth_session = session_obj
        return user, validated_token


class SessionAwareJWTAuthenticationScheme(SimpleJWTScheme):
    """معرفی اسکیمای `SessionAwareJWTAuthentication` به `drf-spectacular` برای تولید OpenAPI."""

    target_class = "apps.authentication.jwt_auth.SessionAwareJWTAuthentication"
    name = "jwtAuth"

"""کنترل دسترسی هوشمند به مستندات OpenAPI / Swagger / ReDoc.

در محیط توسعه (`DEBUG=True`) یا زمانی که `API_DOCS_ALLOW_ANONYMOUS=True` باشد،
مستندات برای تسهیل اتصال تیم فرانت‌اند باز است؛ در محیط تولیدِ سخت‌گیرانه فقط
کاربران احرازشدهٔ ادمین/اپراتور به آن دسترسی دارند.
"""

from __future__ import annotations

from typing import Any

from django.conf import settings
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)
from rest_framework.permissions import BasePermission


class CanViewAPIDocs(BasePermission):
    """مجوز مشاهدهٔ اسکیمای OpenAPI و رابط‌های Swagger/ReDoc."""

    message = "مشاهدهٔ مستندات API در این محیط نیازمند دسترسی مدیریتی است."

    def has_permission(self, request: Any, view: Any) -> bool:
        """بررسی تنظیمات محیط یا سطح دسترسی کاربر."""
        del view
        if getattr(settings, "DEBUG", False) or getattr(
            settings,
            "API_DOCS_ALLOW_ANONYMOUS",
            True,
        ):
            return True
        user = getattr(request, "user", None)
        return bool(
            user
            and user.is_authenticated
            and (
                getattr(user, "is_staff", False)
                or getattr(user, "role", "") in {"admin", "operator"}
            )
        )


class GatedSpectacularAPIView(SpectacularAPIView):
    """ارائهٔ فایل اسکیمای OpenAPI با کنترل دسترسی."""

    permission_classes = [CanViewAPIDocs]


class GatedSpectacularSwaggerView(SpectacularSwaggerView):
    """نمایش رابط تعاملی Swagger UI با کنترل دسترسی."""

    permission_classes = [CanViewAPIDocs]


class GatedSpectacularRedocView(SpectacularRedocView):
    """نمایش رابط مستندات ReDoc با کنترل دسترسی."""

    permission_classes = [CanViewAPIDocs]

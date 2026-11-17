"""نماهای عمومیِ گالری.

── چرا `AllowAny` و بی‌احراز هویت؟ ──────────────────────────────────────
این محتوا بخشی از صفحهٔ اول است و پیش از هر ورودی دیده می‌شود. اگر
احراز هویت لازم داشت، مهمان صفحهٔ نیمه‌خالی می‌دید. هیچ دادهٔ شخصی هم
در پاسخ نیست (فقط تصویر و عنوان و متنِ منتشرشده).
"""

from __future__ import annotations

from typing import Any

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.responses import success_response

from .selectors import get_leader_gallery, get_martyrs


class PublicLeaderGalleryAPIView(APIView):
    """تصاویر رهبر انقلاب که در باکس «کتاب و کلام» صفحهٔ اول می‌آیند."""

    permission_classes = [AllowAny]
    authentication_classes: list[Any] = []

    @extend_schema(
        tags=["Gallery"],
        summary="تصاویر رهبر انقلاب و کلام همراهِ هر تصویر",
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request: Request) -> Response:
        """فهرست مرتب‌شدهٔ تصاویر فعال.

        کلید `leader` عمداً یک کلید تازه است (نه آرایهٔ بی‌نام) تا اگر
        روزی فیلد دیگری اضافه شد، قرارداد نشکند.
        """
        items = get_leader_gallery(request)
        return success_response(
            data={"leader": items, "count": len(items)},
            message="تصاویر رهبر انقلاب با موفقیت دریافت شد.",
        )


class PublicMartyrsAPIView(APIView):
    """نوار شهدای بالای فوتر."""

    permission_classes = [AllowAny]
    authentication_classes: list[Any] = []

    @extend_schema(
        tags=["Gallery"],
        summary="فهرست شهدا برای نوار تصویری بالای فوتر",
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request: Request) -> Response:
        """فهرست مرتب‌شدهٔ شهدای فعال."""
        items = get_martyrs(request)
        return success_response(
            data={"martyrs": items, "count": len(items)},
            message="فهرست شهدا با موفقیت دریافت شد.",
        )


class PublicGalleryAPIView(APIView):
    """هر دو مجموعه در یک پاسخ — برای وقتی کلاینت هر دو را می‌خواهد."""

    permission_classes = [AllowAny]
    authentication_classes: list[Any] = []

    @extend_schema(
        tags=["Gallery"],
        summary="گالری کامل: تصاویر رهبر + نوار شهدا در یک پاسخ",
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request: Request) -> Response:
        """ترکیب دو سلکتور؛ هر کدام کش مستقل خودش را دارد."""
        leader = get_leader_gallery(request)
        martyrs = get_martyrs(request)
        return success_response(
            data={"leader": leader, "martyrs": martyrs},
            message="گالری با موفقیت دریافت شد.",
        )

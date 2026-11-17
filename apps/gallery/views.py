"""نمای عمومی گالری — یک مسیر، دو منبع، پاسخ استاندارد پروژه."""

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


class GalleryAPIView(APIView):
    """گالری کامل: تصاویر رهبر + شهدا در یک پاسخ.

    چرا یک مسیر و نه دو؟ صفحهٔ اول به هر دو نیاز دارد و دو درخواستِ موازی
    برای داده‌ای که همیشه با هم مصرف می‌شود، فقط یک رفت‌وبرگشت اضافه است.
    مسیرهای تفکیک‌شده (`/leader/` و `/martyrs/`) هم می‌مانند تا اگر روزی
    صفحه‌ای فقط یکی را خواست، مجبور به گرفتن هر دو نشود.
    """

    permission_classes = [AllowAny]
    authentication_classes: list[Any] = []

    @extend_schema(
        tags=["Gallery (Public)"],
        summary="گالری محتوایی صفحهٔ اول (تصاویر رهبر و نوار شهدا)",
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request: Request) -> Response:
        """بازگرداندن هر دو فهرست با آدرس مطلق تصاویر."""
        leader = get_leader_gallery(request)
        martyrs = get_martyrs(request)
        return success_response(
            data={"leader": leader, "martyrs": martyrs},
            message="گالری صفحهٔ اول دریافت شد.",
        )


class LeaderGalleryAPIView(APIView):
    """فقط تصاویر رهبر انقلاب."""

    permission_classes = [AllowAny]
    authentication_classes: list[Any] = []

    @extend_schema(
        tags=["Gallery (Public)"],
        summary="تصاویر رهبر انقلاب همراه با کلام هر تصویر",
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request: Request) -> Response:
        """بازگرداندن فهرست مرتب تصاویر فعال."""
        items = get_leader_gallery(request)
        return success_response(
            data={"items": items, "count": len(items)},
            message="تصاویر رهبر انقلاب دریافت شد.",
        )


class MartyrsAPIView(APIView):
    """فقط نوار شهدا."""

    permission_classes = [AllowAny]
    authentication_classes: list[Any] = []

    @extend_schema(
        tags=["Gallery (Public)"],
        summary="شهدای نوار گردان بالای فوتر",
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request: Request) -> Response:
        """بازگرداندن فهرست مرتب شهدای فعال."""
        items = get_martyrs(request)
        return success_response(
            data={"items": items, "count": len(items)},
            message="فهرست شهدا دریافت شد.",
        )

"""ویوهای متادیتا و اطلاعات پایهٔ سامانهٔ کاوه ۱۸۵ (`/api/v1/meta/`)."""

from __future__ import annotations

from typing import Any

from django.conf import settings
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from .jalali import today_jalali
from .responses import success_response


class ServiceMetaResponseSerializer(serializers.Serializer):
    """سریالایزر مستندسازی پاسخ متادیتای سرویس."""

    service = serializers.CharField()
    title = serializers.CharField()
    organizer = serializers.CharField()
    schema_version = serializers.CharField()
    today_jalali = serializers.CharField()
    timezone = serializers.CharField()


class ServiceMetaAPIView(APIView):
    """ارائهٔ اطلاعات نسخهٔ API، تاریخ شمسی سرور، منطقهٔ زمانی و مشخصات حوزه ۱۸۵ شهید کاوه."""

    permission_classes = [AllowAny]
    authentication_classes: list[Any] = []

    @extend_schema(
        tags=["System & Health"],
        summary="دریافت متادیتای سرویس و نسخهٔ قرارداد API",
        responses={200: ServiceMetaResponseSerializer},
    )
    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """برگرداندن متادیتای زمان اجرای سامانه."""
        del request, args, kwargs
        payload = {
            "service": "kaveh185",
            "title": "سامانه مسابقه بزرگ فرهنگی و کتابخوانی هفته بسیج — کاوه ۱۸۵",
            "organizer": "حوزه مقاومت بسیج ۱۸۵ شهید کاوه",
            "schema_version": "v1",
            "today_jalali": today_jalali(separator="/"),
            "timezone": str(getattr(settings, "TIME_ZONE", "Asia/Tehran")),
        }
        return success_response(
            data=payload,
            message="متادیتای سرویس کاوه ۱۸۵ با موفقیت دریافت شد.",
        )

"""ویوهای متادیتا، کاتالوگ کشف API و اطلاعات پایهٔ سامانهٔ کاوه ۱۸۵."""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from .jalali import format_jalali_datetime, today_jalali
from .responses import success_response


class ServiceMetaResponseSerializer(serializers.Serializer):
    """سریالایزر مستندسازی پاسخ متادیتای سرویس."""

    service = serializers.CharField()
    title = serializers.CharField()
    organizer = serializers.CharField()
    schema_version = serializers.CharField()
    today_jalali = serializers.CharField()
    server_time_iso = serializers.CharField()
    server_time_jalali = serializers.CharField()
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
        now = timezone.now()
        payload = {
            "service": "kaveh185",
            "title": "سامانه مسابقه بزرگ فرهنگی و کتابخوانی هفته بسیج — کاوه ۱۸۵",
            "organizer": "حوزه مقاومت بسیج ۱۸۵ شهید کاوه",
            "schema_version": "v1",
            "today_jalali": today_jalali(separator="/"),
            "server_time_iso": now.isoformat(),
            "server_time_jalali": format_jalali_datetime(now),
            "timezone": str(getattr(settings, "TIME_ZONE", "Asia/Tehran")),
        }
        return success_response(
            data=payload,
            message="متادیتای سرویس کاوه ۱۸۵ با موفقیت دریافت شد.",
        )


class APIRootDiscoveryView(APIView):
    """کاتالوگ کشف مسیرهای اصلی سامانه برای توسعه‌دهندگان فرانت‌اند در ریشهٔ سرویس (`/api/v1/`)."""

    permission_classes = [AllowAny]
    authentication_classes: list[Any] = []

    @extend_schema(
        operation_id="api_v1_discovery_retrieve",
        tags=["System & Health"],
        summary="کاتالوگ کشف اندپوینت‌ها و مستندات سامانه کاوه ۱۸۵ (API Discovery)",
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """برگرداندن نقشهٔ مسیرهای کلیدی عمومی، شرکت‌کننده، ادمین و مستندات Swagger/ReDoc."""
        del request, args, kwargs
        now = timezone.now()
        payload = {
            "service": "kaveh185-backend",
            "title": "سامانه مسابقه بزرگ فرهنگی و کتابخوانی هفته بسیج — حوزه مقاومت بسیج ۱۸۵ شهید کاوه",
            "version": "1.0.0",
            "schema_version": "v1",
            "server_time_iso": now.isoformat(),
            "server_time_jalali": format_jalali_datetime(now),
            "documentation": {
                "swagger_ui": "/api/v1/docs/",
                "redoc": "/api/v1/redoc/",
                "openapi_schema": "/api/v1/schema/",
            },
            "public_endpoints": {
                "landing_bootstrap": "/api/v1/core/bootstrap/",
                "exam_status": "/api/v1/exam/status/",
                "mosques_dropdown": "/api/v1/mosques/",
                "mosques_leaderboard": "/api/v1/mosques/leaderboard/",
                "receipt_verify": "/api/v1/exam/receipt/{tracking_code}/",
                "health_live": "/api/v1/health/live/",
                "health_ready": "/api/v1/health/ready/",
            },
            "participant_endpoints": {
                "register": "/api/v1/auth/register/",
                "otp_request": "/api/v1/auth/otp/request/",
                "otp_verify": "/api/v1/auth/otp/verify/",
                "exam_start": "/api/v1/exam/start/",
                "exam_current": "/api/v1/exam/current/",
                "exam_answer": "/api/v1/exam/answer/",
                "exam_finish": "/api/v1/exam/finish/",
                "exam_report_card": "/api/v1/exam/report-card/",
            },
            "admin_endpoints": {
                "password_login": "/api/v1/auth/login/password/",
                "command_center": "/api/v1/admin/command-center/",
                "exam_config": "/api/v1/exam/admin/config/",
                "questions_crud": "/api/v1/exam/admin/questions/",
                "live_analytics_dashboard": "/api/v1/reporting/admin/dashboard/",
                "lottery_participant_explorer": "/api/v1/reporting/admin/participants/",
                "live_lottery_draw": "/api/v1/reporting/admin/lottery/draw/",
                "excel_7sheet_export": "/api/v1/reporting/admin/export.xlsx",
            },
        }
        return success_response(
            data=payload,
            message="به سامانه بک‌اند مسابقه کتابخوانی هفته بسیج (حوزه ۱۸۵ شهید کاوه) خوش آمدید.",
        )


@extend_schema(exclude=True)
class RootDiscoveryAliasView(APIRootDiscoveryView):
    """مسیر ریشهٔ دامنه (`/`) بدون تکرار در اسکیمای OpenAPI."""

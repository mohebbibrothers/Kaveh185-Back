"""ویوهای بررسی سلامت و آمادگی عملیاتی (`/api/v1/health/`, `/ready/`, `/detailed/`)."""

from __future__ import annotations

from typing import Any

from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.responses import error_response, success_response

from .checks import build_detailed_health_report, check_cache, check_database
from .serializers import BasicHealthSerializer, DetailedHealthSerializer
from .throttles import HealthCheckThrottle


class HealthPingAPIView(APIView):
    """بررسی سریع زنده بودن پروسهٔ وب‌سرور (Liveness Probe)."""

    permission_classes = [AllowAny]
    authentication_classes: list[Any] = []
    throttle_classes = [HealthCheckThrottle]

    @extend_schema(
        tags=["System & Health"],
        summary="بررسی زنده بودن سرویس (Liveness)",
        responses={200: BasicHealthSerializer},
    )
    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """پاسخ سریع Liveness."""
        del request, args, kwargs
        return success_response(
            data={"status": "healthy", "service": "kaveh185"},
            message="سرویس کاوه ۱۸۵ در حال اجراست.",
        )


class HealthReadyAPIView(APIView):
    """بررسی آمادگی سرویس برای پذیرش ترافیک (Readiness Probe — دیتابیس و کش)."""

    permission_classes = [AllowAny]
    authentication_classes: list[Any] = []
    throttle_classes = [HealthCheckThrottle]

    @extend_schema(
        tags=["System & Health"],
        summary="بررسی آمادگی سرویس (Readiness)",
        responses={200: BasicHealthSerializer},
    )
    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """بررسی اتصال دیتابیس و کش برای ارکستریتور/Load Balancer."""
        del request, args, kwargs
        db_info = check_database()
        cache_info = check_cache()
        if db_info["status"] != "healthy":
            return error_response(
                message="سرویس هنوز آمادهٔ پذیرش ترافیک نیست.",
                errors={"database": db_info, "cache": cache_info},
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                code="service_not_ready",
            )
        return success_response(
            data={
                "status": "ready",
                "service": "kaveh185",
                "database": db_info,
                "cache": cache_info,
            },
            message="سرویس آمادهٔ پذیرش ترافیک است.",
        )


class HealthDetailedAPIView(APIView):
    """بررسی تشخیصی عمیق تمام زیرسیستم‌های سامانهٔ کاوه ۱۸۵."""

    permission_classes = [AllowAny]
    authentication_classes: list[Any] = []
    throttle_classes = [HealthCheckThrottle]

    @extend_schema(
        tags=["System & Health"],
        summary="گزارش تشخیصی جامع سلامت زیرسیستم‌ها",
        responses={200: DetailedHealthSerializer},
    )
    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """برگرداندن گزارش کامل سلامت دیتابیس، کش، مایگریشن‌ها، زنجیرهٔ حسابرسی و پیامک."""
        del request, args, kwargs
        report = build_detailed_health_report()
        http_status = (
            status.HTTP_503_SERVICE_UNAVAILABLE
            if report["overall_status"] == "unhealthy"
            else status.HTTP_200_OK
        )
        if http_status != status.HTTP_200_OK:
            return error_response(
                message="برخی زیرسیستم‌های حیاتی دچار اختلال هستند.",
                errors=report,
                status_code=http_status,
                code="system_unhealthy",
            )
        return success_response(
            data=report,
            message="گزارش تشخیصی سلامت با موفقیت تولید شد.",
        )

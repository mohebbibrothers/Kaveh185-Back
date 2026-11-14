"""ویوی اکسپورت متریک‌های Prometheus برای مسیر `/api/v1/metrics/`."""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.http import HttpResponse
from drf_spectacular.utils import extend_schema
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.views import APIView

from .exceptions import ForbiddenDomainError


class PrometheusMetricsView(APIView):
    """ارائهٔ متریک‌های زمان اجرای سرور با فرمت استاندارد Prometheus."""

    permission_classes = [AllowAny]
    authentication_classes: list[Any] = []

    @extend_schema(
        tags=["Observability"],
        summary="دریافت متریک‌های Prometheus",
        responses={200: {"type": "string"}},
    )
    def get(self, request: Request, *args: Any, **kwargs: Any) -> HttpResponse:
        """برگرداندن خروجی متنی متریک‌ها با بررسی توکن اختیاری در محیط تولید."""
        expected_token = str(getattr(settings, "METRICS_AUTH_TOKEN", "")).strip()
        if expected_token:
            auth_header = str(request.headers.get("Authorization", "")).strip()
            if auth_header != f"Bearer {expected_token}":
                raise ForbiddenDomainError(
                    "دسترسی به متریک‌ها نیازمند توکن معتبر است.",
                    code="metrics_forbidden",
                )
        payload = generate_latest()
        return HttpResponse(payload, content_type=CONTENT_TYPE_LATEST)

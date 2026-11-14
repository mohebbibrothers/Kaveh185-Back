"""میان‌افزارهای زیرساختی کاوه ۱۸۵: شناسهٔ رهگیری، بودجهٔ کارایی، هدرهای امنیتی و نسخه‌بندی."""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from typing import Any

from django.db import connection
from django.http import HttpRequest, HttpResponse

from .metrics import (
    HTTP_DB_QUERY_COUNT,
    HTTP_DB_QUERY_TIME_SECONDS,
    HTTP_REQUESTS_TOTAL,
    HTTP_SLOW_REQUESTS_TOTAL,
)
from .performance import QueryPerformanceTracker
from .performance_contracts import resolve_performance_budget
from .responses import set_current_trace_id
from .uuid7 import uuid7_hex

_SAFE_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._-]{8,64}$")


class RequestIDMiddleware:
    """تزریق و انتشار شناسهٔ یکتای درخواست (`X-Request-ID` / `X-Trace-ID`) در کل چرخه."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        """ذخیرهٔ حلقهٔ بعدی میان‌افزار."""
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        """استخراج یا تولید شناسهٔ امن درخواست و درج آن در پاسخ."""
        incoming = (
            request.headers.get("X-Request-ID") or request.headers.get("X-Trace-ID") or ""
        ).strip()
        request_id = incoming if _SAFE_REQUEST_ID_RE.match(incoming) else uuid7_hex()
        request.request_id = request_id  # type: ignore[attr-defined]
        set_current_trace_id(request_id)

        response = self.get_response(request)
        response["X-Request-ID"] = request_id
        response["X-Trace-ID"] = request_id
        return response


class PerformanceBudgetMiddleware:
    """سنجش زمان پاسخ و تعداد کوئری‌های دیتابیس و تزریق هدرهای Performance Contract."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        """ذخیرهٔ حلقهٔ بعدی میان‌افزار."""
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        """اندازه‌گیری زمان، شمارش کوئری‌های SQL و ثبت متریک‌های Prometheus."""
        tracker = QueryPerformanceTracker()
        start_time = time.perf_counter()
        budget = resolve_performance_budget(request.path)

        with connection.execute_wrapper(tracker):
            response = self.get_response(request)

        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
        response["X-Response-Time-ms"] = f"{elapsed_ms:.2f}"
        response["X-Performance-Budget-ms"] = str(budget.max_response_ms)
        response["X-DB-Query-Count"] = str(tracker.query_count)
        response["X-DB-Time-ms"] = f"{tracker.total_time_ms:.2f}"

        HTTP_REQUESTS_TOTAL.labels(
            method=request.method,
            status=str(response.status_code),
        ).inc()
        HTTP_DB_QUERY_COUNT.observe(tracker.query_count)
        HTTP_DB_QUERY_TIME_SECONDS.observe(tracker.total_time_ms / 1000.0)
        if elapsed_ms > budget.max_response_ms:
            HTTP_SLOW_REQUESTS_TOTAL.labels(method=request.method).inc()

        return response


class SecurityHeadersMiddleware:
    """تزریق هدرهای امنیتی مرورگر (Defense-in-Depth) و محافظت از کش پاسخ‌های خطا."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        """ذخیرهٔ حلقهٔ بعدی میان‌افزار."""
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        """اعمال هدرهای امنیتی استاندارد روی تمام پاسخ‌ها."""
        response = self.get_response(request)
        response.setdefault("X-Content-Type-Options", "nosniff")
        response.setdefault("X-Frame-Options", "DENY")
        response.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.setdefault(
            "Permissions-Policy",
            "accelerometer=(), camera=(), geolocation=(), gyroscope=(), microphone=(), payment=(), usb=()",
        )
        if not request.path.startswith(("/api/docs", "/api/redoc", "/admin")):
            response.setdefault(
                "Content-Security-Policy",
                "default-src 'none'; frame-ancestors 'none'; base-uri 'none'",
            )
        if response.status_code >= 400:
            response["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
        return response


class APIVersionHeaderMiddleware:
    """افزودن هدر نسخهٔ قرارداد API (`X-API-Version: v1`) روی تمام مسیرهای `/api/v1/`."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        """ذخیرهٔ حلقهٔ بعدی میان‌افزار."""
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> Any:
        """افزودن هدر نسخهٔ API."""
        response = self.get_response(request)
        if request.path.startswith("/api/v1/"):
            response.setdefault("X-API-Version", "v1")
        return response

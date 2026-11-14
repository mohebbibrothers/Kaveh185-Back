"""فرمت استاندارد و یکپارچهٔ پاسخ‌های API (Response Envelope) برای سامانهٔ کاوه ۱۸۵.

چرا این قرارداد طراحی شده است:
    ترکیبی از بهترین ویژگی‌های Setad-Jang (پایداری کلیدهای `success`، `status_code`،
    `message`، `data` و `errors` به همراه بازگشت کد ۲۰۰ در عملیات حذف جهت حفظ یکپارچگی
    بدنهٔ JSON برای فرانت‌اند) و Mahdieh (کلید ماشینی پایدار `code` و شناسهٔ رهگیری
    `trace_id` مطابق استاندارد RFC 9457).
"""

from __future__ import annotations

from contextvars import ContextVar
from typing import Any

from rest_framework import status
from rest_framework.response import Response

from .uuid7 import uuid7_hex

_CURRENT_TRACE_ID: ContextVar[str] = ContextVar("kaveh185_trace_id", default="")


def get_current_trace_id() -> str:
    """بازگرداندن شناسهٔ رهگیری (`trace_id`) درخواست جاری یا ساخت یک شناسهٔ جدید."""
    val = _CURRENT_TRACE_ID.get()
    return val if val else uuid7_hex()


def set_current_trace_id(trace_id: str) -> None:
    """تنظیم شناسهٔ رهگیری (`trace_id`) برای چرخهٔ درخواست جاری."""
    _CURRENT_TRACE_ID.set(trace_id)


def success_response(
    *,
    data: Any = None,
    message: str = "عملیات با موفقیت انجام شد.",
    status_code: int = status.HTTP_200_OK,
    code: str = "ok",
    meta: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> Response:
    """ساخت پاسخ موفق استاندارد در قالب Envelope یکپارچه."""
    payload: dict[str, Any] = {
        "success": True,
        "status_code": status_code,
        "code": code,
        "message": message,
        "trace_id": get_current_trace_id(),
        "data": data,
    }
    if meta is not None:
        payload["meta"] = meta
    return Response(payload, status=status_code, headers=headers)


def created_response(
    *,
    data: Any = None,
    message: str = "با موفقیت ایجاد شد.",
    code: str = "created",
    headers: dict[str, str] | None = None,
) -> Response:
    """ساخت پاسخ استاندارد HTTP 201 Created."""
    return success_response(
        data=data,
        message=message,
        status_code=status.HTTP_201_CREATED,
        code=code,
        headers=headers,
    )


def deleted_response(
    *,
    message: str = "با موفقیت حذف شد.",
    code: str = "deleted",
) -> Response:
    """ساخت پاسخ استاندارد برای عملیات حذف (عمداً HTTP 200 با `data: null` برای حفظ Envelope)."""
    return success_response(
        data=None,
        message=message,
        status_code=status.HTTP_200_OK,
        code=code,
    )


def error_response(
    *,
    message: str = "درخواست نامعتبر است.",
    errors: Any = None,
    status_code: int = status.HTTP_400_BAD_REQUEST,
    code: str = "bad_request",
    headers: dict[str, str] | None = None,
) -> Response:
    """ساخت پاسخ خطای استاندارد در قالب Envelope یکپارچه همراه با `code` ماشینی و `trace_id`."""
    payload: dict[str, Any] = {
        "success": False,
        "status_code": status_code,
        "code": code,
        "message": message,
        "trace_id": get_current_trace_id(),
        "errors": errors if errors is not None else {},
    }
    response = Response(payload, status=status_code, headers=headers)
    response["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
    return response

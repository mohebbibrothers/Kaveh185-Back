"""استثناهای دامنه‌ای و هندلر مرکزی خطاها برای قرارداد API کاوه ۱۸۵ (Kaveh185).

تمام خطاهای DRF، جنگو و دامنه از این لایه عبور می‌کنند تا خروجی همیشه دارای:
- `success: false`
- `status_code`
- `code` (کد ماشینی پایدار برای شرط‌گذاری در فرانت‌اند)
- `message` (پیام فارسی گویا برای نمایش به کاربر)
- `trace_id` (شناسهٔ یکتای رهگیری در لاگ‌ها)
- `errors` (جزئیات فیلدبه‌فیلد خطاها)
باشد.
"""

from __future__ import annotations

import logging
from typing import Any

from django.core.exceptions import (
    ObjectDoesNotExist,
    PermissionDenied,
    ValidationError as DjangoValidationError,
)
from django.http import Http404
from rest_framework import status
from rest_framework.exceptions import (
    APIException,
    AuthenticationFailed,
    MethodNotAllowed,
    NotAuthenticated,
    NotFound,
    ParseError,
    PermissionDenied as DRFPermissionDenied,
    Throttled,
    ValidationError as DRFValidationError,
)
from rest_framework.response import Response
from rest_framework.views import exception_handler

from .responses import error_response, get_current_trace_id

logger = logging.getLogger("apps.core")


class DomainError(Exception):
    """کلاس پایه برای تمام خطاهای منطق کسب‌وکار و دامنه (مستقل از لایهٔ HTTP)."""

    default_message = "خطایی در اجرای عملیات رخ داد."
    default_code = "domain_error"
    default_status = status.HTTP_400_BAD_REQUEST

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        status_code: int | None = None,
        errors: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        """مقداردهی استثنای دامنه."""
        self.message = message or self.default_message
        self.code = code or self.default_code
        self.status_code = status_code or self.default_status
        self.errors = errors or {}
        self.headers = headers
        super().__init__(self.message)


class ValidationDomainError(DomainError):
    """خطای اعتبارسنجی قوانین دامنه (HTTP 422 یا 400)."""

    default_message = "اطلاعات واردشده معتبر نیست."
    default_code = "validation_error"
    default_status = status.HTTP_400_BAD_REQUEST


class ConflictDomainError(DomainError):
    """تعارض با وضعیت موجود، مثلاً تکرار کدملی/تلفن یا شرکت مجدد در آزمون (HTTP 409)."""

    default_message = "این عملیات با وضعیت فعلی در تضاد است."
    default_code = "conflict"
    default_status = status.HTTP_409_CONFLICT


class NotFoundDomainError(DomainError):
    """عدم وجود منبع درخواستی (HTTP 404)."""

    default_message = "مورد درخواستی یافت نشد."
    default_code = "not_found"
    default_status = status.HTTP_404_NOT_FOUND


class ForbiddenDomainError(DomainError):
    """عدم مجوز دسترسی یا بسته بودن بازهٔ زمانی آزمون (HTTP 403)."""

    default_message = "شما مجوز انجام این عملیات را ندارید."
    default_code = "forbidden"
    default_status = status.HTTP_403_FORBIDDEN


class UnauthorizedDomainError(DomainError):
    """نیاز به ورود یا نامعتبر بودن نشست/توکن (HTTP 401)."""

    default_message = "احراز هویت نامعتبر است یا نشست شما منقضی شده است."
    default_code = "unauthorized"
    default_status = status.HTTP_401_UNAUTHORIZED


class StepUpMfaRequiredError(ForbiddenDomainError):
    """نیاز به تأیید دومرحله‌ای تازه (Step-Up MFA) برای عملیات حساس ادمین."""

    default_message = "برای انجام این عملیات حساس، تأیید دومرحله‌ای تازه (TOTP) الزامی است."
    default_code = "step_up_required"
    default_status = status.HTTP_403_FORBIDDEN


class ExamWindowClosedError(ForbiddenDomainError):
    """خطای تلاش برای شروع آزمون خارج از بازهٔ زمانی مجاز."""

    default_message = "در حال حاضر امکان شرکت در آزمون وجود ندارد."
    default_code = "exam_window_closed"
    default_status = status.HTTP_403_FORBIDDEN


class RateLimitDomainError(DomainError):
    """عبور از سقف نرخ مجاز درخواست‌ها (HTTP 429)."""

    default_message = "تعداد درخواست‌های شما بیش از حد مجاز است. لطفاً کمی صبر کنید."
    default_code = "rate_limited"
    default_status = status.HTTP_429_TOO_MANY_REQUESTS


def _extract_first_message(detail: Any, fallback: str) -> str:
    """استخراج یک پیام متنی خوانا از ساختارهای تودرتوی خطای DRF."""
    if isinstance(detail, str):
        return detail
    if isinstance(detail, list) and detail:
        return _extract_first_message(detail[0], fallback)
    if isinstance(detail, dict):
        if "detail" in detail:
            return _extract_first_message(detail["detail"], fallback)
        if "non_field_errors" in detail:
            return _extract_first_message(detail["non_field_errors"], fallback)
        for val in detail.values():
            msg = _extract_first_message(val, "")
            if msg:
                return msg
    return fallback


def custom_exception_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    """هندلر یکپارچهٔ خطاها برای تبدیل تمام استثناها به Envelope استاندارد کاوه ۱۸۵."""
    if isinstance(exc, DomainError):
        return error_response(
            message=exc.message,
            errors=exc.errors,
            status_code=exc.status_code,
            code=exc.code,
            headers=exc.headers,
        )

    if isinstance(exc, DjangoValidationError):
        errors_dict = exc.message_dict if hasattr(exc, "message_dict") else {"detail": exc.messages}
        return error_response(
            message=_extract_first_message(errors_dict, "اطلاعات واردشده معتبر نیست."),
            errors=errors_dict,
            status_code=status.HTTP_400_BAD_REQUEST,
            code="validation_error",
        )

    if isinstance(exc, (Http404, ObjectDoesNotExist)):
        return error_response(
            message="مورد درخواستی یافت نشد.",
            errors={},
            status_code=status.HTTP_404_NOT_FOUND,
            code="not_found",
        )

    if isinstance(exc, PermissionDenied) and not isinstance(exc, DRFPermissionDenied):
        return error_response(
            message="شما دسترسی لازم برای این عملیات را ندارید.",
            errors={},
            status_code=status.HTTP_403_FORBIDDEN,
            code="permission_denied",
        )

    drf_response = exception_handler(exc, context)
    if drf_response is not None:
        status_code = drf_response.status_code
        headers: dict[str, str] = {}
        for k, v in drf_response.items():
            if k.lower() in {"retry-after", "www-authenticate"}:
                headers[k] = v

        if isinstance(exc, DRFValidationError):
            return error_response(
                message=_extract_first_message(drf_response.data, "اطلاعات ورودی نامعتبر است."),
                errors=drf_response.data,
                status_code=status.HTTP_400_BAD_REQUEST,
                code="validation_error",
                headers=headers or None,
            )
        if isinstance(exc, (NotAuthenticated, AuthenticationFailed)):
            return error_response(
                message=_extract_first_message(
                    drf_response.data,
                    "احراز هویت انجام نشده یا توکن نامعتبر است.",
                ),
                errors=drf_response.data if isinstance(drf_response.data, dict) else {},
                status_code=status.HTTP_401_UNAUTHORIZED,
                code="authentication_failed"
                if isinstance(exc, AuthenticationFailed)
                else "not_authenticated",
                headers=headers or None,
            )
        if isinstance(exc, DRFPermissionDenied):
            return error_response(
                message=_extract_first_message(
                    drf_response.data,
                    "شما دسترسی لازم برای این عملیات را ندارید.",
                ),
                errors=drf_response.data if isinstance(drf_response.data, dict) else {},
                status_code=status.HTTP_403_FORBIDDEN,
                code="permission_denied",
                headers=headers or None,
            )
        if isinstance(exc, NotFound):
            return error_response(
                message=_extract_first_message(drf_response.data, "مورد درخواستی یافت نشد."),
                errors={},
                status_code=status.HTTP_404_NOT_FOUND,
                code="not_found",
                headers=headers or None,
            )
        if isinstance(exc, MethodNotAllowed):
            return error_response(
                message="متد HTTP ارسالی برای این مسیر مجاز نیست.",
                errors={},
                status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
                code="method_not_allowed",
                headers=headers or None,
            )
        if isinstance(exc, ParseError):
            return error_response(
                message="ساختار بدنهٔ درخواست (JSON) معتبر نیست.",
                errors={},
                status_code=status.HTTP_400_BAD_REQUEST,
                code="malformed_body",
                headers=headers or None,
            )
        if isinstance(exc, Throttled):
            wait = getattr(exc, "wait", None)
            retry_seconds = int(wait) if wait else 60
            headers["Retry-After"] = str(retry_seconds)
            return error_response(
                message="تعداد درخواست‌های شما بیش از حد مجاز است. لطفاً کمی صبر کنید.",
                errors={"retry_after_seconds": retry_seconds},
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                code="rate_limited",
                headers=headers,
            )
        if isinstance(exc, APIException):
            return error_response(
                message=_extract_first_message(
                    drf_response.data, "خطایی در پردازش درخواست رخ داد."
                ),
                errors=drf_response.data if isinstance(drf_response.data, dict) else {},
                status_code=status_code,
                code=getattr(exc, "default_code", "api_error"),
                headers=headers or None,
            )

    logger.error(
        "Unhandled server exception trace_id=%s exc=%s",
        get_current_trace_id(),
        exc,
        exc_info=exc,
    )
    return error_response(
        message="خطای داخلی سرور رخ داده است. کد رهگیری را به پشتیبانی اعلام کنید.",
        errors={},
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        code="internal_server_error",
    )

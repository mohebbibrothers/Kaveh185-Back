"""ویوهای نازک HTTP برای مشاهدهٔ لاگ پیامک‌ها، پردازش صف Outbox و ارسال پیامک تستی توسط ادمین."""

from __future__ import annotations

import logging
from typing import Any

from django.conf import settings
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.authentication.permissions import IsAdminRole
from apps.authentication.throttles import OTPRequestRateThrottle
from apps.core.outbox import relay_pending_outbox
from apps.core.pagination import StandardLimitOffsetPagination
from apps.core.responses import success_response

from .bale import BaleError, bale_is_configured, get_me, send_bale_message
from .choices import SMSCategory
from .selectors import get_sms_delivery_logs_queryset
from .serializers import AdminSendTestSMSInputSerializer, SMSDeliveryLogSerializer
from .services import (
    bale_chat_for_phone,
    consume_bale_code,
    normalize_bale_phone,
    remember_bale_chat,
    send_sms_message,
)

logger = logging.getLogger(__name__)


class AdminSMSDeliveryLogListAPIView(APIView):
    """مشاهدهٔ فهرست لاگ پیامک‌های ارسالی (OTP و پیامک تشکر) توسط ادمین."""

    permission_classes = [IsAuthenticated, IsAdminRole]

    @extend_schema(
        tags=["Admin - Notifications & SMS"],
        summary="فهرست لاگ پیامک‌های ارسالی (OTP و تشکر پایان آزمون)",
        parameters=[
            OpenApiParameter(name="category", type=str, required=False),
            OpenApiParameter(name="status", type=str, required=False),
            OpenApiParameter(name="search", type=str, required=False),
        ],
        responses={200: SMSDeliveryLogSerializer(many=True)},
    )
    def get(self, request: Request) -> Response:
        """بازگرداندن فهرست صفحه‌بندی‌شدهٔ لاگ پیامک‌ها."""
        qs = get_sms_delivery_logs_queryset(
            category=str(request.query_params.get("category", "")),
            status=str(request.query_params.get("status", "")),
            search=str(request.query_params.get("search", "")),
        )
        paginator = StandardLimitOffsetPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        serializer = SMSDeliveryLogSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


class AdminSendTestSMSAPIView(APIView):
    """ارسال پیامک تستی یا اطلاع‌رسانی توسط ادمین."""

    permission_classes = [IsAuthenticated, IsAdminRole]

    @extend_schema(
        tags=["Admin - Notifications & SMS"],
        summary="ارسال پیامک تستی یا اطلاع‌رسانی توسط ادمین",
        request=AdminSendTestSMSInputSerializer,
        responses={201: SMSDeliveryLogSerializer},
    )
    def post(self, request: Request) -> Response:
        """ارسال پیامک به شماره موبایل مشخص‌شده."""
        serializer = AdminSendTestSMSInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        log = send_sms_message(
            recipient_phone=serializer.validated_data["recipient_phone"],
            message_text=serializer.validated_data["message_text"],
            category=SMSCategory.ANNOUNCEMENT,
        )
        return success_response(
            data=SMSDeliveryLogSerializer(log).data,
            message="پیامک با موفقیت پردازش شد.",
            status_code=status.HTTP_201_CREATED,
        )


class AdminFlushOutboxAPIView(APIView):
    """پردازش دستی صف پیام‌های Outbox در انتظار ارسال توسط ادمین."""

    permission_classes = [IsAuthenticated, IsAdminRole]

    @extend_schema(
        tags=["Admin - Notifications & SMS"],
        summary="پردازش و ارسال پیام‌های در انتظار در صف Outbox",
        request=None,
        responses={200: OpenApiTypes.OBJECT},
    )
    def post(self, request: Request) -> Response:
        """پردازش پیام‌های در صف Outbox."""
        del request
        stats = relay_pending_outbox(limit=100)
        return success_response(
            data=stats,
            message="صف پیام‌های Outbox پردازش شد.",
        )


def _safe_bale_reply(chat_id: int, text: str) -> bool:
    """پاسخ به کاربر در بله — بدونِ آنکه خطا کلِ وب‌هوک را بشکند.

    چرا مهم است؟ اگر توکن تنظیم نشده باشد یا بله قطع شود، پرتابِ استثنا
    پاسخِ ۵۰۰ می‌دهد؛ بله آن را «تحویل نشد» می‌بیند و **همان آپدیت را
    بی‌پایان دوباره می‌فرستد**. یک تنظیمِ جاافتاده نباید به حلقهٔ بی‌پایان
    تبدیل شود. پس همیشه ۲۰۰ برمی‌گردانیم و فقط لاگ می‌گیریم.
    """
    try:
        return send_bale_message(chat_id, text).ok
    except BaleError as exc:
        logger.warning("پاسخِ بله ارسال نشد (chat=%s): %s", chat_id, exc)
        return False


def _bale_username() -> str:
    """نامِ کاربریِ ربات: اول از تنظیمات، و اگر خالی بود از خودِ بله.

    چرا از بله هم می‌پرسیم؟ چون نامی که در فرمِ ثبت‌نام به کاربر نشان می‌دهیم
    باید همان رباتی باشد که واقعاً پیام می‌دهد؛ یک «_» جابه‌جا در تنظیمات،
    کاربر را به رباتِ دیگری می‌فرستد و کدش هیچ‌وقت نمی‌آید.
    """
    configured = str(getattr(settings, "BALE_BOT_USERNAME", "") or "").strip().lstrip("@")
    if configured:
        return configured
    try:
        return str(get_me().get("username") or "")
    except BaleError:
        return ""


class BaleWebhookAPIView(APIView):
    """دریافتِ آپدیت‌های رباتِ بله (وب‌هوک) — پلِ «کد اتصال» ⇄ «شماره همراه».

    چرا وب‌هوک و نه فقط polling؟ روی هاستِ اشتراکی، cron هر دقیقه یک‌بار
    اجرا می‌شود و کاربر باید تا ۶۰ ثانیه منتظر بماند. وب‌هوک همان لحظه جواب
    می‌دهد. اگر وب‌هوک در دسترس نبود، دستورِ `bale_inbox` همان کار را با
    تأخیر انجام می‌دهد — هر دو یک مسیرِ منطقی را صدا می‌زنند.
    """

    permission_classes: list[Any] = []
    authentication_classes: list[Any] = []
    throttle_classes: list[Any] = []

    @extend_schema(
        tags=["Notifications & Bale"],
        summary="بازرسی دسترس‌پذیری وب‌هوک بله (برای setWebhook)",
        request=None,
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request: Request) -> Response:
        """پاسخِ سلامت — بله در پاسخِ `setWebhook` وضعیتِ این نشانی را گزارش می‌کند.

        چرا GET لازم است؟ بعضی میزبان‌ها پیش از ثبتِ وب‌هوک یک درخواستِ ساده
        می‌زنند و اگر ۴۰۵ بگیرند، ثبت را رد می‌کنند. هم‌چنین این پاسخ نشان
        می‌دهد که مسیر واقعاً به اپلیکیشنِ درست وصل است.
        """
        return Response(
            {
                "ok": True,
                "service": "kaveh185-bale-webhook",
                "configured": bale_is_configured(),
                "secret_required": bool(str(getattr(settings, "BALE_WEBHOOK_SECRET", "") or "")),
            }
        )

    def _authorized(self, request: Request) -> bool:
        """آیا درخواست از بله آمده است؟

        بله هدرِ `X-Bale-Secret` را **نمی‌فرستد**؛ آنچه می‌فرستد هدرِ
        `X-Telegram-Bot-Api-Secret-Token` است (همان `secret_token`ی که در
        `setWebhook` می‌دهیم). اگر فقط اولی را می‌پذیرفتیم، کلید بی‌اثر
        می‌شد و وب‌هوک برای همه باز می‌ماند — یعنی هر کسی می‌توانست
        گفتگوی خودش را به شمارهٔ دلخواه بچسباند. هر دو هدر پذیرفته می‌شوند
        تا با هر دو سبکِ مستندسازی سازگار باشد.
        """
        expected = str(getattr(settings, "BALE_WEBHOOK_SECRET", "") or "")
        if not expected:
            return True
        provided = {
            request.headers.get("X-Bale-Secret", ""),
            request.headers.get("X-Telegram-Bot-Api-Secret-Token", ""),
        }
        return expected in provided

    @extend_schema(
        tags=["Notifications & Bale"],
        summary="وب‌هوک دریافت آپدیت‌های ربات بله (تنظیم‌شده با secret)",
        request=None,
        responses={200: OpenApiTypes.OBJECT},
    )
    def post(self, request: Request) -> Response:
        """پردازشِ یک آپدیت: ثبتِ شماره، مصرفِ کدِ اتصال، یا پاسخِ راهنما."""
        if not self._authorized(request):
            return Response({"ok": False}, status=status.HTTP_403_FORBIDDEN)

        payload = request.data if isinstance(request.data, dict) else {}
        message = payload.get("message") or {}
        chat = message.get("chat") or {}
        chat_id = chat.get("id")
        if chat_id is None:
            return Response({"ok": True, "handled": "no_chat"})

        text = str(message.get("text") or "").strip()
        sender = message.get("from") or {}

        linked = consume_bale_code(raw_text=text, chat=chat)
        if linked.get("matched"):
            reply = (
                "اتصال برقرار شد ✅\n"
                "از این پس پیام‌ها و کدهای تأییدِ سامانه در همین گفتگو می‌آید.\n"
                "به سامانه برگردید و ادامه دهید."
            )
            handled = "linked"
        else:
            phone = normalize_bale_phone(text)
            if phone:
                remember_bale_chat(
                    chat_id=int(chat_id),
                    phone_number=phone,
                    first_name=str(sender.get("first_name") or ""),
                    username=str(sender.get("username") or ""),
                )
                reply = (
                    "شمارهٔ شما ثبت شد ✅\n"
                    "حالا به سامانه برگردید. اگر سامانه کدی برای اتصال نشان می‌دهد، "
                    "همان کد را همین‌جا بفرستید."
                )
                handled = "phone"
            elif text.startswith("/start"):
                reply = (
                    "سلام 👋\n"
                    "این رباتِ مسابقهٔ کتاب‌خوانی حوزهٔ ۱۸۵ شهید کاوه است.\n\n"
                    "برای اتصال، کدی که سامانه نشان می‌دهد را همین‌جا بفرستید — "
                    "یا شمارهٔ همراه خود را به شکلِ 09121234567."
                )
                handled = "start"
            else:
                reply = (
                    "کدِ اتصال یا شمارهٔ همراه را بفرستید.\n"
                    "کدِ اتصال را از صفحهٔ ثبت‌نامِ سامانه بردارید (مثلِ A7K2QF)."
                )
                handled = "unknown"

        delivered = _safe_bale_reply(int(chat_id), reply)
        return Response({"ok": True, "handled": handled, "replied": delivered})


class BaleChannelStatusAPIView(APIView):
    """وضعیتِ کانالِ بله برای یک شماره (آیا کد می‌تواند از بله برود؟).

    فرانت پیش از نمایشِ دکمهٔ «دریافت کد در بله» همین را می‌پرسد تا کاربر
    دکمهٔ بی‌فایده نبیند. پاسخ هیچ کد یا اطلاعاتِ شخصی برنمی‌گرداند.
    """

    permission_classes = [AllowAny]
    authentication_classes: list[Any] = []
    throttle_classes = [OTPRequestRateThrottle]

    @extend_schema(
        tags=["Notifications & Bale"],
        summary="وضعیت اتصال بله برای یک شماره همراه",
        parameters=[OpenApiParameter(name="phone_number", type=str, required=True)],
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request: Request) -> Response:
        """بازگرداندنِ وضعیتِ کانال (بدونِ افشای اینکه شماره در سامانه هست یا نه)."""
        phone = normalize_bale_phone(str(request.query_params.get("phone_number", "")))
        return Response(
            {
                "ok": True,
                "data": {
                    "bale_configured": bale_is_configured(),
                    "bot_username": _bale_username(),
                    "linked": bool(phone) and bale_chat_for_phone(phone) is not None,
                },
            }
        )

"""ویوهای نازک HTTP برای مشاهدهٔ لاگ پیامک‌ها، پردازش صف Outbox و ارسال پیامک تستی توسط ادمین."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from typing import Any

from django.conf import settings
from django.utils import timezone
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
from .bale_intent import bot_deep_link, contact_request_keyboard
from .choices import SMSCategory
from .selectors import get_sms_delivery_logs_queryset
from .serializers import AdminSendTestSMSInputSerializer, SMSDeliveryLogSerializer
from .services import (
    bale_chat_for_phone,
    consume_bale_code,
    issue_bale_code,
    link_chat_by_contact,
    normalize_bale_phone,
    phone_for_chat,
    prepare_otp_text,
    record_bale_delivery,
    redeem_intent,
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


def _resend_otp_via_bale(*, phone_number: str, chat_id: int) -> bool:
    """کدِ چالشِ فعال را برای کاربر به بله می‌فرستد.

    ⚠️ محدودیتِ صادقانه: کد فقط به‌صورتِ هش ذخیره می‌شود و بازیابی‌شدنی نیست.
    پس این تابع یک کدِ **تازه** برای همان شماره می‌سازد (چالشِ قبلی باطل
    می‌شود) و همان را می‌فرستد؛ کاربر کدی که در صفحه دیده را باید همان‌جا وارد
    کند یا «ارسال دوباره» را بزند. اگر ساختِ کد ممکن نبود، False.
    """
    from apps.authentication.services import create_and_send_otp

    del chat_id  # ارسال از مسیرِ لینکِ ثبت‌شده انجام می‌شود
    try:
        create_and_send_otp(phone_number=phone_number)
    except Exception:  # pragma: no cover - مسیرِ جانبی نباید وب‌هوک را بشکند
        logger.warning("ارسالِ کدِ تازه از بله ناموفق بود (phone=%s)", phone_number)
        return False
    return True


def process_bale_message(
    *,
    chat: dict[str, Any],
    text: str,
    sender: dict[str, Any] | None = None,
    contact: dict[str, Any] | None = None,
    keyboard: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """پردازشِ یک پیامِ ورودیِ بله — با این فرض که **کاربر هیچ‌چیز تایپ نمی‌کند**.

    ── تصمیمِ محصولی ───────────────────────────────────────────────────────
    کاربرِ ما مکالمه با ربات نمی‌خواهد؛ فقط می‌خواهد کدِ ورود بگیرد و در آزمون
    شرکت کند. پس ربات حق ندارد از او «کدِ اتصال» یا «شماره با دست» بخواهد.
    تنها چیزی که می‌فرستد: یک دکمهٔ «ارسالِ شمارهٔ من» و بعد، خودِ کدِ تأیید.

    ── سه مسیرِ ورود، به ترتیبِ اولویت ─────────────────────────────────────
    ۱) **پیامِ `contact`** (دکمهٔ رسمیِ بله) ⇒ اتصالِ خودکار + ارسالِ فوریِ کد.
    ۲) **پیوندِ عمیق** (`/start <intent>`) ⇒ اتصالِ خودکار + ارسالِ فوریِ کد.
    ۳) **`/start`ِ خالی** ⇒ فقط دکمهٔ «ارسالِ شمارهٔ من»؛ هیچ متنی خواسته نمی‌شود.
       (اگر کاربر پیامِ دیگری بفرستد، همان دکمه را دوباره می‌گیرد — بدونِ
       سرزنش و بدونِ دستورِ تایپ.)

    ⚠️ این تابع تنها منبعِ حقیقت است: وب‌هوک، `bale_inbox` و `bale_worker` همه
    همین را صدا می‌زنند.

    خروجی: `{"handled", "reply", "keyboard", "resend_otp_for", "otp_code"}`.
    اگر `otp_code` پر باشد، لایهٔ ارسال همان را به‌جای `reply` می‌فرستد (پیامِ
    کد متنِ مخصوصِ خودش را دارد).
    """
    sender = sender or {}
    chat_id = int(chat.get("id") or 0)
    greeting = str(sender.get("first_name") or chat.get("first_name") or "").strip()

    # ── ۱) دکمهٔ «ارسالِ شمارهٔ من» ────────────────────────────────────────
    if contact:
        result = link_chat_by_contact(chat=chat, contact=contact)
        if not result.get("linked"):
            return {
                "handled": "contact_unlinked",
                "reply": (
                    "این شماره در سامانهٔ مسابقه ثبت نشده است.\n"
                    "اول در سامانه با همین شماره ثبت‌نام کنید، بعد به همین گفتگو برگردید."
                ),
                "keyboard": None,
            }
        phone = str(result.get("phone_number") or "")
        code = _issue_and_send_otp(phone=phone, chat_id=chat_id)
        if code:
            return {
                "handled": "contact_linked",
                "reply": "",
                "otp_code": code,
                "resend_otp_for": phone,
            }
        return {
            "handled": "contact_linked",
            "reply": ("شمارهٔ شما ثبت شد ✅\nحالا در سامانه «دریافتِ کد» را بزنید؛ کد همین‌جا می‌آید."),
        }

    raw = str(text or "").strip()

    # «/start <payload>» — بله پارامترِ پیوندِ عمیق را همین‌طور می‌فرستد.
    payload = raw[6:].strip() if raw.lower().startswith("/start") else ""

    # ── ۲) پیوندِ عمیق (اولویتِ اول، چون خودکار است) ──────────────────────
    for candidate in (payload, raw):
        if not candidate:
            continue
        redeemed = redeem_intent(raw_text=candidate, chat=chat)
        if not redeemed.get("matched"):
            continue
        phone = str(redeemed.get("phone_number") or "")
        code = _issue_and_send_otp(phone=phone, chat_id=chat_id)
        return {
            "handled": "intent_linked",
            "reply": "" if code else "شمارهٔ شما تأیید شد ✅",
            "otp_code": code,
            "resend_otp_for": phone,
        }

    # ── ۲ب) کدِ دستی: فقط اگر خودتان خواستید تایپ کنید (مسیرِ پشتیبان) ────
    for candidate in (raw, payload):
        if not candidate:
            continue
        legacy = consume_bale_code(raw_text=candidate, chat=chat)
        if not legacy.get("matched"):
            continue
        phone = str(legacy.get("phone_number") or "")
        code = _issue_and_send_otp(phone=phone, chat_id=chat_id)
        return {
            "handled": "linked",
            "reply": "" if code else "اتصال برقرار شد ✅",
            "otp_code": code,
            "resend_otp_for": phone,
        }

    # ── ۲ج) شمارهٔ تایپ‌شده: مسیرِ پشتیبانِ قدیمی، برای سازگاری ────────────
    # ⚠️ ما هرگز این را از کاربر نمی‌خواهیم؛ ولی اگر کسی خودش شماره را فرستاد،
    # بی‌پاسخ نمی‌ماند و همان کد را می‌گیرد (بدونِ اینکه مسیرِ اصلی خراب شود).
    guessed = normalize_bale_phone(raw)
    if guessed:
        linked_by_phone = link_chat_by_contact(chat=chat, contact={"phone_number": guessed})
        if linked_by_phone.get("linked"):
            code = _issue_and_send_otp(phone=guessed, chat_id=chat_id)
            return {
                "handled": "phone",
                "reply": "" if code else "شمارهٔ شما ثبت شد ✅",
                "otp_code": code,
                "resend_otp_for": guessed,
            }

    # ── ۳) «شروع» یا هر پیامِ دیگر: فقط یک دکمه، هیچ تایپی ────────────────
    if chat_id and phone_for_chat(chat_id):
        # این گفتگو از قبل به شماره‌ای وصل است؛ کد را دوباره بفرست.
        phone = phone_for_chat(chat_id)
        code = _issue_and_send_otp(phone=phone, chat_id=chat_id) if phone else ""
        return {
            "handled": "already_linked",
            "reply": "" if code else "شمارهٔ شما قبلاً ثبت شده است.",
            "otp_code": code,
            "resend_otp_for": phone,
        }

    hello = f"{greeting} عزیز، " if greeting else ""
    return {
        "handled": "start" if raw.lower().startswith("/start") or not raw else "unknown",
        "reply": (
            f"{hello}خوش آمدید 👋\n"
            "برای دریافتِ کدِ ورود، فقط دکمهٔ زیر را بزنید — نیازی به نوشتنِ چیزی نیست.\n\n"
            "اگر دکمه را نمی‌بینید، از همین صفحه در سامانه دکمهٔ «ارسالِ شماره در بله» را بزنید.\n\n"
            "راهِ پشتیبان: «کدِ اتصال»ی که سامانه به شما نشان می‌دهد را همین‌جا بفرستید."
        ),
        "keyboard": contact_request_keyboard(),
    }


def _issue_and_send_otp(*, phone: str, chat_id: int) -> str:
    """یک کدِ تأییدِ تازه می‌سازد و **همان را** در همین گفتگو می‌فرستد.

    ── چرا کدِ تازه و نه کدِ قبلی؟ ─────────────────────────────────────────
    کد فقط به‌صورتِ هش ذخیره می‌شود و بازیابی‌شدنی نیست (تصمیمِ امنیتیِ درست).
    پس تنها راهِ صادقانه این است که چالشِ تازه بسازیم و **همان کد** را در متنِ
    پیام بگذاریم؛ کاربر همان را در سایت وارد می‌کند. چالشِ قبلی باطل می‌شود،
    پس هیچ کدِ دومی هم بیرون نمی‌ماند.

    خروجی: خودِ کد (برای متنِ پیام) یا رشتهٔ خالی اگر ارسال/ساخت ممکن نبود.
    """
    del chat_id  # ارسال از مسیرِ لینکِ ثبت‌شده انجام می‌شود (همان گفتگو)
    from apps.authentication.services import create_and_send_otp

    try:
        result = create_and_send_otp(phone_number=phone)
    except Exception:  # pragma: no cover - مسیرِ جانبی نباید تحویل را بشکند
        logger.warning("ساخت/ارسالِ کدِ تازه از بله ناموفق بود (phone=%s)", phone)
        return ""
    return str(result.get("channel_code") or result.get("debug_code") or "")


def _fingerprint(secret: str) -> str:
    """اثرِ انگشتِ کلید: ۶ کاراکترِ اولِ SHA-256 یا رشتهٔ خالی.

    چرا؟ شایع‌ترین علتِ ۴۰۳ این است که `.env` و بله **دو کلیدِ متفاوت** دارند
    (کلید را عوض کردید و دوباره ثبت نکردید، یا `\r` انتهای خط). با این مقدار
    می‌شود از مرورگر دید کدام کلید در اپ است، و در `bale_doctor` کنارِ کلیدِ
    ثبت‌شده در بله گذاشت — بدونِ آنکه خودِ راز جایی نوشته شود.
    """
    if not secret:
        return ""
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()[:6]


def _safe_bale_reply(chat_id: int, text: str, keyboard: dict[str, Any] | None = None) -> bool:
    """پاسخ به کاربر در بله — بدونِ آنکه خطا کلِ وب‌هوک را بشکند.

    چرا مهم است؟ اگر توکن تنظیم نشده باشد یا بله قطع شود، پرتابِ استثنا
    پاسخِ ۵۰۰ می‌دهد؛ بله آن را «تحویل نشد» می‌بیند و **همان آپدیت را
    بی‌پایان دوباره می‌فرستد**. یک تنظیمِ جاافتاده نباید به حلقهٔ بی‌پایان
    تبدیل شود. پس همیشه ۲۰۰ برمی‌گردانیم و فقط لاگ می‌گیریم.
    """
    try:
        return send_bale_message(chat_id, text, keyboard).ok
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
    # ⚠️ این مسیر از بیرون (بله) فراخوانی می‌شود و کوکی/توکنِ مرورگر ندارد؛
    # CSRF هیچ معنایی این‌جا ندارد و اگر فعال بماند، درخواستِ بله با ۴۰۳ رد
    # می‌شود — دقیقاً همان «ربات ساکت است» که سخت پیدا می‌شود.
    csrf_exempt = True

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
        secret = str(getattr(settings, "BALE_WEBHOOK_SECRET", "") or "")
        return Response(
            {
                "ok": True,
                "service": "kaveh185-bale-webhook",
                "configured": bale_is_configured(),
                "secret_required": bool(secret),
                # اثرِ انگشتِ کلید: نه خودش، نه هشش — فقط ۶ کاراکترِ اولِ SHA-256.
                # با این کار می‌شود بی‌آنکه راز لو برود فهمید دو طرف یک کلید
                # دارند یا نه (کلیدِ کوتاه/بلند یا جابه‌جا، همان ۴۰۳ می‌سازد).
                "secret_fingerprint": _fingerprint(secret),
                "webhook_url": str(getattr(settings, "BALE_WEBHOOK_URL", "") or ""),
                "time": timezone.now().isoformat(timespec="seconds"),
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
        return any(value and hmac.compare_digest(value, expected) for value in provided)

    @staticmethod
    def _payload(request: Request) -> dict:
        """بدنهٔ JSON را از هر راهی که شد می‌خواند، بی‌آنکه ۴۰۰ بسازد.

        دو سناریوی واقعی: (۱) واسطِ میزبان هدرِ Content-Type را عوض می‌کند و
        DRF بدنه را پارس نمی‌کند؛ (۲) بدنهٔ ناقص/غیرِJSON می‌رسد. در هر دو
        حالت `request.data` یا خطا می‌دهد یا `{}` می‌شود و اگر ما ۴۰۰ برگردانیم،
        بله همان آپدیت را بی‌پایان دوباره می‌فرستد. پس اول بدنهٔ خام را
        خودمان می‌خوانیم و فقط در آخرین مرحله به `request.data` تکیه می‌کنیم.
        """
        raw = b""
        for getter in (lambda: request.body, lambda: request._request.body):
            try:
                raw = getter() or b""
            except Exception:  # pragma: no cover - بدنهٔ مصرف‌شده
                raw = b""
            if raw:
                break
        if raw:
            try:
                parsed = json.loads(raw.decode("utf-8", errors="replace"))
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, dict):
                return parsed
        try:
            data = request.data
        except Exception:
            return {}
        return data if isinstance(data, dict) else {}

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

        # ⚠️ دسترسی به بدنه: DRF فقط با Content-Typeِ درست بدنه را پارس می‌کند و
        # اگر بله/پروکسی هدر را عوض کند، `request.data` خالی می‌شود و آپدیت
        # بی‌صدا دور ریخته می‌شود (۲۰۰ می‌دهیم، هیچ کاری نمی‌کنیم — بدترین حالت).
        # پس اگر پارس نشد، خودمان JSON را از بدنهٔ خام می‌خوانیم.
        payload = self._payload(request)
        # آزمونِ حلقه‌ای (`bale_webhook --probe`) یک آپدیتِ ساختگی می‌فرستد تا کلِ
        # مسیر — کلید، ترتیبِ middleware، پردازش و پاسخ — سنجیده شود، ولی بدونِ
        # ارسالِ پیام به هیچ گفتگوی واقعی (تا وقتِ کاربر را نگیرد).
        probe_mode = bool(payload.get("_probe"))
        message = payload.get("message") or {}
        chat = message.get("chat") or {}
        if chat.get("id") is None:
            return Response({"ok": True, "handled": "no_chat"})

        # ⚠️ هر خطای پیش‌بینی‌نشده نباید به ۵۰۰ تبدیل شود: بله ۵۰۰ را «تحویل
        # نشد» می‌بیند و همان آپدیت را بی‌پایان دوباره می‌فرستد. خطا را لاگ
        # می‌کنیم و همان ۲۰۰ را با دلیلش برمی‌گردانیم؛ آن‌گاه عیب‌یابی از راهِ
        # پاسخِ `bale_doctor` ممکن است، نه از دلِ یک حلقهٔ بی‌پایان.
        try:
            result = process_bale_message(
                chat=chat,
                text=str(message.get("text") or ""),
                sender=message.get("from") or {},
                contact=message.get("contact") or {},
            )
        except Exception:
            logger.exception("پردازشِ آپدیتِ بله شکست خورد (chat=%s)", chat.get("id"))
            if not probe_mode:
                record_bale_delivery(
                    chat_id=int(chat.get("id") or 0),
                    handled="error",
                    replied=False,
                    note="خطای پردازش",
                )
            return Response({"ok": True, "handled": "error", "replied": None})
        chat_id = int(chat["id"])

        # اگر کدِ اتصال تازه وصل شد و چالشِ فعالی داشت، همان کد را همین حالا بفرست
        resend_for = str(result.get("resend_otp_for") or "")
        if resend_for:
            _resend_otp_via_bale(phone_number=resend_for, chat_id=chat_id)

        otp_code = str(result.get("otp_code") or "")
        if probe_mode:
            delivered = None
        elif otp_code:
            delivered = _safe_bale_reply(chat_id, prepare_otp_text(phone_number="", code=otp_code))
        else:
            delivered = _safe_bale_reply(chat_id, str(result["reply"]), result.get("keyboard"))
        if not probe_mode:
            record_bale_delivery(
                chat_id=chat_id,
                handled=str(result["handled"]),
                replied=bool(delivered),
                source="webhook",
                note="" if delivered else "ارسالِ پاسخ ناموفق بود",
            )
        return Response({"ok": True, "handled": result["handled"], "replied": delivered})


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


class BaleStartLinkAPIView(APIView):
    """ساختِ «پیوندِ یک‌ضربه» برای وصل‌کردنِ گفتگو به شماره — بدونِ هیچ تایپی.

    فرانت دو نشانی می‌گیرد:

    * `start_link` — `ble.ir/<bot>?start=<intent>`: بله خودش `/start <intent>`
      را به ربات می‌دهد و ما گفتگو را به شماره وصل می‌کنیم و کد را می‌فرستیم.
    * `contact_link` — گفتگوی ربات را باز می‌کند تا کاربر دکمهٔ «ارسالِ شمارهٔ
      من» را ببیند (مسیرِ پشتیبان اگر بله پارامتر را منتقل نکند).

    ── امنیت ───────────────────────────────────────────────────────────────
    فقط برای شماره‌ای که در سامانه ثبت‌نام کرده کار می‌کند (همان محافظِ
    `issue_bale_code`)، پشتِ throttleِ OTP است، و شماره یا کد هیچ‌جا در نشانی
    نمی‌رود. پاسخ هیچ کدِ تأییدی برنمی‌گرداند.
    """

    permission_classes = [AllowAny]
    authentication_classes: list[Any] = []
    throttle_classes = [OTPRequestRateThrottle]

    @extend_schema(
        tags=["Notifications & Bale"],
        summary="ساختِ پیوندِ اتصالِ یک‌ضربه (بدونِ تایپ در بله)",
        request=None,
        parameters=[OpenApiParameter(name="phone_number", type=str, required=True)],
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request: Request) -> Response:
        """پیوندهای آماده برای دکمهٔ «اتصال با بله» در صفحهٔ ثبت‌نام."""
        phone = normalize_bale_phone(str(request.query_params.get("phone_number", "")))
        if not phone:
            return Response(
                {
                    "ok": False,
                    "error": {"code": "invalid_phone", "message": "شماره همراه معتبر نیست."},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        link = issue_bale_code(phone_number=phone)
        if not link.get("code"):
            return Response(
                {
                    "ok": True,
                    "data": {
                        "eligible": False,
                        "message": "برای این شماره پروندهٔ شرکت‌کننده‌ای پیدا نشد.",
                    },
                }
            )
        return Response(
            {
                "ok": True,
                "data": {
                    "eligible": True,
                    "start_link": link.get("start_link") or bot_deep_link(),
                    "contact_link": link.get("contact_link") or bot_deep_link(),
                    "bot_username": link.get("bot_username") or "",
                    "expires_in_seconds": link.get("expires_in_seconds") or 0,
                    "already_linked": bool(link.get("already_linked")),
                },
            }
        )

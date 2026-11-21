"""سرویس‌های ارسال پیامک، پردازش صف Outbox و ثبت لاگ تحویل پیامک."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.conf import settings
from django.utils import timezone

from apps.core.exceptions import DomainError
from apps.core.models import OutboxMessage

from .choices import SMSCategory, SMSDeliveryStatus
from .models import BaleSubscriber, SMSDeliveryLog
from .providers import send_via_configured_gateway


def format_thank_you_sms_with_channels(
    *,
    base_message: str,
    channels: list[dict[str, str]] | None = None,
) -> str:
    """ترکیب متن پیامک تشکر پایان آزمون با لینک کانال‌های ارتباطی حوزه ۱۸۵ شهید کاوه."""
    lines = [base_message.strip()]
    if channels:
        lines.append("کانال‌های ارتباطی ما:")
        for ch in channels:
            title = str(ch.get("title") or ch.get("platform") or "").strip()
            url = str(ch.get("url") or "").strip()
            if url:
                lines.append(f"- {title}: {url}" if title else f"- {url}")
    return "\n".join(lines)


def send_sms_message(
    *,
    recipient_phone: str,
    message_text: str,
    category: Any = SMSCategory.THANK_YOU,
    raise_on_failure: bool = False,
) -> SMSDeliveryLog:
    """ارسال پیامک از طریق درگاه و ثبت لاگ تحویل در دیتابیس."""
    res = send_via_configured_gateway(
        recipient_phone=recipient_phone,
        message_text=message_text,
    )
    log_entry = SMSDeliveryLog.objects.create(
        recipient_phone=recipient_phone,
        category=category,
        provider=res.provider,
        message_text=message_text,
        status=SMSDeliveryStatus.SENT if res.success else SMSDeliveryStatus.FAILED,
        provider_message_id=res.provider_message_id,
        error_message=res.error_message,
    )
    if not res.success and raise_on_failure:
        raise DomainError(
            f"خطا در ارسال پیامک به {recipient_phone}: {res.error_message}",
            code="sms_gateway_error",
        )
    return log_entry


def dispatch_outbox_message(msg: OutboxMessage) -> dict[str, Any]:
    """پردازش یک رکورد از صف تراکنشی Outbox و ارسال پیامک متناظر."""
    payload: dict[str, Any] = msg.payload or {}
    recipient = str(msg.recipient or payload.get("phone_number", "")).strip()

    if msg.topic == "sms.otp":
        code = str(payload.get("code", "")).strip()
        text = (
            f"کد تایید سامانه مسابقه کتابخوانی هفته بسیج (حوزه ۱۸۵ شهید کاوه): {code}\n"
            "این کد را در اختیار دیگران قرار ندهید."
        )
        log = send_sms_message(
            recipient_phone=recipient,
            message_text=text,
            category=SMSCategory.OTP,
            raise_on_failure=True,
        )
        return {"sms_log_id": log.id, "status": log.status}

    if msg.topic == "sms.exam_thank_you":
        base_msg = str(payload.get("message_text", "")).strip()
        channels = list(payload.get("channels") or [])
        full_text = format_thank_you_sms_with_channels(
            base_message=base_msg,
            channels=channels,
        )
        log = send_sms_message(
            recipient_phone=recipient,
            message_text=full_text,
            category=SMSCategory.THANK_YOU,
            raise_on_failure=True,
        )
        return {"sms_log_id": log.id, "status": log.status}

    return {"skipped": True, "topic": msg.topic}


deliver_outbox_sms = dispatch_outbox_message


# ════════════════════════════════════════════════════════════════════════════
#  پلِ بله → OTP
#  ────────────────────────────────────────────────────────────────────────────
#  وقتی پنلِ پیامکی در دسترس نیست (نبودِ اینماد)، بله تنها راهِ رساندنِ کد به
#  کاربر است. این توابع سه کار می‌کنند:
#    ۱) نشانیِ بلهٔ یک شماره را نگه می‌دارند (`remember_bale_chat`)،
#    ۲) پیام‌های ورودیِ ربات را می‌خوانند و اگر شماره بود، ثبتش می‌کنند،
#    ۳) پیام‌های معلقِ Outbox را — که به خاطرِ نبودِ پیامک شکست خورده‌اند —
#       از راهِ بله می‌فرستند.
#  هیچ‌کدام به پیامک وابسته نیست؛ اگر پیامک بعداً وصل شود، همان مسیرِ قبلی
#  دست‌نخورده کار می‌کند و بله فقط یک کانالِ دوم می‌ماند.
# ════════════════════════════════════════════════════════════════════════════

_FA_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def normalize_bale_phone(raw: str) -> str:
    """شمارهٔ همراه را از متنِ کاربر بیرون می‌کشد و به شکلِ `09xxxxxxxxx` می‌آورد.

    مردم در بله شماره را به ده شکل می‌فرستند: «۰۹۱۲…» با رقمِ فارسی،
    «+98912…»، «0912 345 6789» با فاصله. همه باید یکسان شوند، وگرنه کاربری
    که شماره‌اش را درست فرستاده، کد نمی‌گیرد و فکر می‌کند سامانه خراب است.
    """
    text = str(raw or "").translate(_FA_DIGITS)
    digits = "".join(ch for ch in text if ch.isdigit())
    if digits.startswith("0098"):
        digits = digits[4:]
    elif digits.startswith("98") and len(digits) == 12:
        digits = digits[2:]
    elif digits.startswith("0") and len(digits) == 11:
        digits = digits[1:]
    if len(digits) != 10 or not digits.startswith("9"):
        return ""
    return f"0{digits}"


def remember_bale_chat(
    *, chat_id: int, phone_number: str, first_name: str = "", username: str = ""
) -> BaleSubscriber:
    """نشانیِ بلهٔ یک شماره را ثبت/به‌روز می‌کند (یک رکورد برای هر شماره)."""
    subscriber, _ = BaleSubscriber.objects.update_or_create(
        phone_number=phone_number,
        defaults={
            "chat_id": int(chat_id),
            "bale_first_name": str(first_name or "")[:80],
            "bale_username": str(username or "")[:80],
            "is_active": True,
        },
    )
    return subscriber


def bale_chat_for_phone(phone_number: str) -> int | None:
    """`chat_id`ِ ثبت‌شده برای یک شماره (یا None)."""
    row = BaleSubscriber.objects.filter(phone_number=phone_number, is_active=True).first()
    return int(row.chat_id) if row else None


def send_otp_via_bale(*, phone_number: str, code: str) -> dict[str, Any]:
    """کدِ تأیید را از رباتِ بله برای شماره می‌فرستد.

    خروجی همیشه یک دیکشنری است و هرگز استثنا نمی‌دهد؛ مسیرِ ثبت‌نام نباید
    به‌خاطرِ خطای یک کانالِ جانبی بشکند. `sent=False` یعنی «کاربر هنوز ربات
    را شروع نکرده» یا «بله در دسترس نیست» و لایهٔ بالاتر تصمیم می‌گیرد.
    """
    from .bale import BaleNotConfigured, send_bale_message

    chat_id = bale_chat_for_phone(phone_number)
    if chat_id is None:
        return {"sent": False, "reason": "not_subscribed"}

    text = (
        "کدِ تأییدِ سامانهٔ مسابقهٔ کتاب‌خوانی هفتهٔ بسیج (حوزهٔ ۱۸۵ شهید کاوه)\n\n"
        f"{code}\n\n"
        "این کد را در اختیار دیگران قرار ندهید. اگر شما درخواست نداده‌اید، همین پیام را نادیده بگیرید."
    )
    try:
        res = send_bale_message(chat_id, text)
    except BaleNotConfigured:
        return {"sent": False, "reason": "not_configured"}
    except Exception:  # pragma: no cover - محافظِ نهایی؛ مسیرِ ثبت‌نام نباید بشکند
        return {"sent": False, "reason": "error"}

    if res.ok:
        SMSDeliveryLog.objects.create(
            recipient_phone=phone_number,
            category=SMSCategory.OTP,
            provider="bale",
            message_text=text,
            status=SMSDeliveryStatus.SENT,
            provider_message_id=f"bale:{res.message_id or 0}",
        )
        return {"sent": True, "reason": "ok"}

    SMSDeliveryLog.objects.create(
        recipient_phone=phone_number,
        category=SMSCategory.OTP,
        provider="bale",
        message_text=text,
        status=SMSDeliveryStatus.FAILED,
        error_message=res.detail,
    )
    return {"sent": False, "reason": "gateway_error", "detail": res.detail}


# ════════════════════════════════════════════════════════════════════════════
#  گرفتنِ شماره از کاربر، بدونِ ماژیک: «کدِ بله» (Bale code)
#  ────────────────────────────────────────────────────────────────────────────
#  مشکل: بله اجازه نمی‌دهد ربات پیامی را که کاربر برای «رباتِ دیگر» فرستاده
#  بخواند، و کاربر معمولاً شمارهٔ خودش را هم به ربات نمی‌فرستد. نتیجه: نمی‌فهمیم
#  این chat_id مالِ کدام شماره است.
#
#  راه‌حل: خودِ سامانه یک کدِ کوتاه و یک‌بارمصرف می‌سازد و به کاربر می‌گوید
#  «این کد را برای ربات بفرست». کاربر فقط «کپی → بله → ارسال» می‌کند و با همان
#  یک حرکت، هم ثابت می‌کند صاحبِ آن شماره است (چون کد را از سامانه گرفته که
#  پشتش همان شماره ثبت شده)، هم نشانیِ گفتگو را به ما می‌دهد.
#
#  کدها فقط هش‌شده نگه داشته می‌شوند و کوتاه‌عمرند؛ ورودیِ اشتباهِ متوالی
#  هم محدود است تا کسی نتواند کد را حدس بزند.
# ════════════════════════════════════════════════════════════════════════════

BALE_CODE_TTL_SECONDS = 20 * 60
BALE_CODE_MAX_ATTEMPTS = 5
BALE_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # بدونِ I/O/0/1 (اشتباهِ خواندن)


def _bale_code_hash(code: str) -> str:
    """هشِ کدِ بله با کلیدِ سرور (کد خام هیچ‌جا ذخیره نمی‌شود)."""
    import hashlib
    import hmac

    key = str(getattr(settings, "SECRET_KEY", "")).encode("utf-8")
    return hmac.new(key, code.strip().upper().encode("utf-8"), hashlib.sha256).hexdigest()


def _normalize_bale_code(raw: str) -> str:
    """کد را از متنِ کاربر بیرون می‌کشد و یکسان می‌سازد (حروفِ کوچک/خط تیره)."""
    text = str(raw or "").translate(_FA_DIGITS).upper()
    return "".join(ch for ch in text if ch in BALE_CODE_ALPHABET)


def _generate_bale_code() -> str:
    """کدِ ۶ کاراکتریِ خوانا (بدونِ حروفِ اشتباه‌پذیر)."""
    import secrets

    return "".join(secrets.choice(BALE_CODE_ALPHABET) for _ in range(6))


def issue_bale_code(*, phone_number: str) -> dict[str, Any]:
    """کدِ اتصالِ بله برای یک شماره می‌سازد و دستورهای ارسال را برمی‌گرداند.

    کد فقط در پاسخِ همین درخواست دیده می‌شود؛ در دیتابیس هشِ آن می‌ماند.
    """
    from apps.authentication.models import User

    from .models import BaleLinkCode

    phone = normalize_bale_phone(phone_number) or str(phone_number or "").strip()
    # ⚠️ محافظِ مهم: کدِ اتصال فقط برای شماره‌ای صادر می‌شود که در سامانه
    # «شرکت‌کننده» دارد. وگرنه هر کسی می‌توانست با ساختنِ کد برای شمارهٔ
    # دیگری، گفتگوی بلهٔ خودش را به آن شماره بچسباند و کدهای بعدی را بگیرد.
    if not User.objects.filter(phone_number=phone, role="participant").exists():
        return {"code": "", "expires_in_seconds": 0, "bot_username": "", "deep_link": ""}
    BaleLinkCode.objects.filter(phone_number=phone, consumed_at__isnull=True).update(
        consumed_at=timezone.now()
    )
    code = _generate_bale_code()
    BaleLinkCode.objects.create(
        phone_number=phone,
        code_hash=_bale_code_hash(code),
        expires_at=timezone.now() + timedelta(seconds=BALE_CODE_TTL_SECONDS),
    )
    username = str(getattr(settings, "BALE_BOT_USERNAME", "") or "").strip().lstrip("@")
    return {
        "code": code,
        "expires_in_seconds": BALE_CODE_TTL_SECONDS,
        "bot_username": username,
        "deep_link": f"https://ble.ir/{username}" if username else "",
        "already_linked": bale_chat_for_phone(phone) is not None,
    }


def active_otp_challenge_for_phone(phone_number: str) -> tuple[str, str]:
    """آخرین چالشِ تأییدِ فعالِ یک شماره (تا کد از راهِ بله دوباره فرستاده شود)."""
    from apps.authentication.models import OTPChallenge

    row = (
        OTPChallenge.objects.filter(phone_number=phone_number, is_verified=False)
        .order_by("-created_at", "-id")
        .first()
    )
    if row is None:
        return "", ""
    return str(row.id), str(row.purpose)


def otp_minutes_left(challenge_id: str) -> int:
    """چند دقیقه از عمرِ چالش مانده (برای متنِ کاربر)."""
    from apps.authentication.models import OTPChallenge

    try:
        row = OTPChallenge.objects.filter(pk=int(challenge_id)).first()
    except (TypeError, ValueError):
        return 0
    if row is None:
        return 0
    left = (row.expires_at - timezone.now()).total_seconds()
    return max(0, int(left // 60))


def prepare_otp_text(*, phone_number: str, code: str, purpose: str = "") -> str:
    """متنِ کدِ تأیید؛ اگر کاربر عجله داشت، کوتاه‌ترین راه را هم می‌گوید."""
    del purpose
    return (
        "کدِ تأییدِ سامانهٔ مسابقهٔ کتاب‌خوانی هفتهٔ بسیج (حوزهٔ ۱۸۵ شهید کاوه)\n\n"
        f"{code}\n\n"
        "این کد را در اختیارِ دیگران نگذارید. اگر شما درخواست نداده‌اید، همین پیام را "
        "نادیده بگیرید.\n\n"
        "اگر دیر شده و کد منقضی شده، در همان صفحهٔ ثبت‌نام «ارسال دوبارهٔ کد» را بزنید."
    )


def consume_bale_code(*, raw_text: str, chat: dict[str, Any]) -> dict[str, Any]:
    """اگر متنِ کاربر کدِ اتصال بود، شماره را به این گفتگو وصل می‌کند.

    خروجی: `{"matched": bool, "phone_number": str}`. کدِ منقضی/سوخته/اشتباه
    فقط `matched=False` می‌دهد — هیچ اطلاعاتی لو نمی‌رود.
    """
    from .models import BaleLinkCode

    code = _normalize_bale_code(raw_text)
    if len(code) != 6:
        return {"matched": False}

    digest = _bale_code_hash(code)
    now = timezone.now()
    row = (
        BaleLinkCode.objects.filter(code_hash=digest, consumed_at__isnull=True)
        .order_by("-created_at")
        .first()
    )
    if row is None:
        return {"matched": False}

    if row.expires_at <= now or row.attempts >= BALE_CODE_MAX_ATTEMPTS:
        return {"matched": False, "expired": True}

    row.attempts += 1
    row.save(update_fields=["attempts", "updated_at"])

    remember_bale_chat(
        chat_id=int(chat.get("id") or 0),
        phone_number=row.phone_number,
        first_name=str(chat.get("first_name") or ""),
        username=str(chat.get("username") or ""),
    )
    row.consumed_at = now
    row.save(update_fields=["consumed_at", "attempts", "updated_at"])
    return {"matched": True, "phone_number": row.phone_number}

"""سرویس‌های ارسال پیامک، پردازش صف Outbox و ثبت لاگ تحویل پیامک."""

from __future__ import annotations

from typing import Any

from apps.core.exceptions import DomainError
from apps.core.models import OutboxMessage

from .choices import SMSCategory, SMSDeliveryStatus
from .models import SMSDeliveryLog
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

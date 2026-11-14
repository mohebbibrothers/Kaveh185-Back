"""آداپتورهای قابل تعویض درگاه پیامکی (`console`, `iranpayamak`, `kavenegar`)."""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from urllib import request as urllib_request

from django.conf import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class SMSGatewayResult:
    """نتیجهٔ استاندارد ارسال پیامک از درگاه."""

    provider: str
    success: bool
    provider_message_id: str
    error_message: str = ""


def send_via_configured_gateway(*, recipient_phone: str, message_text: str) -> SMSGatewayResult:
    """ارسال پیامک از طریق درگاه تنظیم‌شده در `settings.SMS_PROVIDER`."""
    provider = str(getattr(settings, "SMS_PROVIDER", "console")).strip().lower()
    api_url = str(getattr(settings, "SMS_API_URL", "")).strip()
    api_key = str(getattr(settings, "SMS_API_KEY", "")).strip()
    sender_line = str(getattr(settings, "SMS_SENDER_LINE", "3000185")).strip()
    timeout_sec = float(getattr(settings, "SMS_TIMEOUT_SECONDS", 4.0))

    if provider == "console" or not api_url or not api_key:
        msg_id = f"console-{uuid.uuid4().hex[:12]}"
        logger.info("SMS [console] to %s: %s", recipient_phone, message_text)
        return SMSGatewayResult(
            provider="console",
            success=True,
            provider_message_id=msg_id,
        )

    payload_bytes = json.dumps(
        {
            "recipient": recipient_phone,
            "sender": sender_line,
            "message": message_text,
        },
        ensure_ascii=False,
    ).encode("utf-8")

    req = urllib_request.Request(  # noqa: S310
        api_url,
        data=payload_bytes,
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "Authorization": f"Bearer {api_key}",
            "X-API-Key": api_key,
        },
        method="POST",
    )
    try:
        with urllib_request.urlopen(req, timeout=timeout_sec) as resp:  # noqa: S310  # nosec B310
            body_text = resp.read().decode("utf-8", errors="replace")
            return SMSGatewayResult(
                provider=provider,
                success=200 <= resp.status < 300,
                provider_message_id=body_text[:100] or f"{provider}-ok",
            )
    except Exception as exc:  # pragma: no cover - خطای شبکه خارجی
        return SMSGatewayResult(
            provider=provider,
            success=False,
            provider_message_id="",
            error_message=str(exc),
        )

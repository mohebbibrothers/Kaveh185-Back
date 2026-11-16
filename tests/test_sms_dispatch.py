"""تست‌های مسیر پیامک: قالب متن، ثبت لاگ تحویل، و پردازش صف Outbox.

چرا این‌ها؟
──────────
پیامک تنها کانالی است که کاربر *بیرون* سایت با سامانه ارتباط می‌گیرد.
اگر قالب متن بشکند یا لاگ تحویل ثبت نشود، هیچ ردی برای پیگیری نمی‌ماند و
پشتیبانی نمی‌تواند بگوید «کد برای این شماره رفت یا نه». این تست‌ها همان
دو چیز را قفل می‌کنند، بدون آن‌که به درگاه واقعی وصل شوند (درگاه در
حالت `console` تست می‌شود تا هیچ پیامک واقعی ارسال نشود).
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from apps.core.exceptions import DomainError
from apps.core.models import OutboxMessage
from apps.notifications.choices import SMSCategory, SMSDeliveryStatus
from apps.notifications.models import SMSDeliveryLog
from apps.notifications.providers import SMSGatewayResult, send_via_configured_gateway
from apps.notifications.services import (
    dispatch_outbox_message,
    format_thank_you_sms_with_channels,
    send_sms_message,
)

pytestmark = pytest.mark.django_db


# ── قالب متن ──────────────────────────────────────────────────────────────
def test_thank_you_format_appends_channels_without_duplicates() -> None:
    """متن تشکر + فهرست کانال‌ها؛ هر کانال یک خط."""
    text = format_thank_you_sms_with_channels(
        base_message="با تشکر از شرکت شما.",
        channels=[
            {"title": "خبرگزاری میدان نامجو", "url": "https://ble.ir/NamjooNewsAgency"},
            {"platform": "bale", "url": "https://ble.ir/x"},
        ],
    )
    assert text.splitlines()[0] == "با تشکر از شرکت شما."
    assert "کانال‌های ارتباطی ما:" in text
    assert "https://ble.ir/NamjooNewsAgency" in text
    # کانالی که عنوان ندارد، از نام پلتفرم استفاده می‌کند نه خط خالی
    assert "- bale: https://ble.ir/x" in text


def test_thank_you_format_skips_entries_without_url() -> None:
    """کانال بی‌نشانی نباید خط خالی یا «- :» بسازد."""
    text = format_thank_you_sms_with_channels(
        base_message="متن",
        channels=[{"title": "بی‌نشانی", "url": ""}],
    )
    assert "- بی‌نشانی" not in text
    assert text.count("\n") == 1  # فقط سرخط «کانال‌های ارتباطی ما»


def test_thank_you_format_without_channels_is_plain() -> None:
    """بدون کانال، متن دست‌نخورده می‌ماند."""
    assert format_thank_you_sms_with_channels(base_message="  متن  ") == "متن"


# ── ثبت لاگ تحویل ─────────────────────────────────────────────────────────
def test_send_sms_records_successful_delivery(settings) -> None:
    """ارسال موفق، یک رکورد SENT با شناسهٔ درگاه ثبت می‌کند."""
    settings.SMS_PROVIDER = "console"
    log = send_sms_message(
        recipient_phone="09120000001",
        message_text="سلام",
        category=SMSCategory.OTP,
    )
    assert log.status == SMSDeliveryStatus.SENT
    assert log.provider == "console"
    assert log.provider_message_id.startswith("console-")
    assert SMSDeliveryLog.objects.filter(pk=log.pk).exists()


def test_send_sms_failure_is_recorded_and_optional_raise(settings) -> None:
    """ارسال ناموفق: لاگ FAILED ثبت می‌شود و با raise_on_failure خطا می‌دهد."""
    settings.SMS_PROVIDER = "console"
    with patch(
        "apps.notifications.services.send_via_configured_gateway",
        return_value=SMSGatewayResult(
            provider="kavenegar", success=False, provider_message_id="", error_message="quota"
        ),
    ):
        log = send_sms_message(recipient_phone="09120000002", message_text="سلام")
        assert log.status == SMSDeliveryStatus.FAILED
        assert log.error_message == "quota"

        with pytest.raises(DomainError) as exc:
            send_sms_message(
                recipient_phone="09120000003", message_text="سلام", raise_on_failure=True
            )
        assert exc.value.code == "sms_gateway_error"


# ── درگاه ─────────────────────────────────────────────────────────────────
def test_console_gateway_never_touches_network(settings) -> None:
    """حالت `console` بدون تنظیم درگاه، موفق برمی‌گردد و شبکه صدا نمی‌زند."""
    settings.SMS_PROVIDER = "console"
    settings.SMS_API_URL = ""
    settings.SMS_API_KEY = ""
    res = send_via_configured_gateway(recipient_phone="09120000004", message_text="x")
    assert res.success is True
    assert res.provider == "console"


def test_gateway_without_credentials_falls_back_to_console(settings) -> None:
    """درگاه تنظیم‌شده ولی بی‌کلید ⇒ همان مسیر امن console."""
    settings.SMS_PROVIDER = "kavenegar"
    settings.SMS_API_URL = "https://example.invalid/send"
    settings.SMS_API_KEY = ""
    res = send_via_configured_gateway(recipient_phone="09120000005", message_text="x")
    assert res.provider == "console"
    assert res.success is True


# ── صف Outbox ─────────────────────────────────────────────────────────────
def test_dispatch_otp_message_sends_code() -> None:
    """پیام صف با موضوع OTP ⇒ متن شامل کد و ارسال موفق."""
    msg = OutboxMessage.objects.create(
        topic="sms.otp",
        recipient="09120000006",
        payload={"code": "4821"},
    )
    result = dispatch_outbox_message(msg)
    assert result["status"] == SMSDeliveryStatus.SENT
    log = SMSDeliveryLog.objects.get(pk=result["sms_log_id"])
    assert "4821" in log.message_text
    assert log.category == SMSCategory.OTP


def test_dispatch_thank_you_includes_channel_line() -> None:
    """پیام تشکر در صف، نشانی کانال رسمی را هم به متن اضافه می‌کند."""
    msg = OutboxMessage.objects.create(
        topic="sms.exam_thank_you",
        recipient="09120000007",
        payload={
            "message_text": "کارنامهٔ شما صادر شد.",
            "channels": [{"title": "نامجو", "url": "https://ble.ir/NamjooNewsAgency"}],
        },
    )
    result = dispatch_outbox_message(msg)
    log = SMSDeliveryLog.objects.get(pk=result["sms_log_id"])
    assert "ble.ir/NamjooNewsAgency" in log.message_text
    assert log.category == SMSCategory.THANK_YOU


def test_dispatch_unknown_topic_is_skipped() -> None:
    """موضوع ناشناخته ⇒ رد بی‌خطا؛ صف نباید به‌خاطر آن متوقف شود."""
    msg = OutboxMessage.objects.create(topic="sms.unknown", recipient="09120000008", payload={})
    assert dispatch_outbox_message(msg) == {"skipped": True, "topic": "sms.unknown"}

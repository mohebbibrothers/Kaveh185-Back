"""آزمون‌های کانالِ بله: نرمال‌سازیِ شماره، کدِ اتصال، و انتخابِ کانالِ تحویل."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest
from django.test import override_settings

from apps.notifications.bale import BaleResult
from apps.notifications.models import BaleLinkCode, BaleSubscriber
from apps.notifications.services import (
    consume_bale_code,
    issue_bale_code,
    normalize_bale_phone,
    send_otp_via_bale,
)
from conftest import create_test_participant as _make_participant

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("09121234567", "09121234567"),
        ("۰۹۱۲۱۲۳۴۵۶۷", "09121234567"),
        ("+989121234567", "09121234567"),
        ("989121234567", "09121234567"),
        ("0912 123 4567", "09121234567"),
        ("00989121234567", "09121234567"),
        ("12345", ""),
        ("", ""),
        ("0212345678", ""),
    ],
)
def test_normalize_bale_phone_accepts_every_real_world_format(raw: str, expected: str) -> None:
    """شماره به هر شکلی که کاربر بنویسد باید یکسان شود، وگرنه کد به او نمی‌رسد."""
    assert normalize_bale_phone(raw) == expected


@override_settings(BALE_BOT_TOKEN="test-token", BALE_BOT_USERNAME="kaveh185_bot")
def test_issue_bale_code_refuses_unknown_phone() -> None:
    """کدِ اتصال برای شمارهٔ بدونِ ثبت‌نام صادر نمی‌شود (جلوگیری از چسباندنِ گفتگو)."""
    _make_participant(seq=901)
    result = issue_bale_code(phone_number="09120000000")
    assert result["code"] == ""
    assert not BaleLinkCode.objects.exists()


@override_settings(BALE_BOT_TOKEN="test-token", BALE_BOT_USERNAME="kaveh185_bot")
def test_bale_code_links_chat_once() -> None:
    """کدِ درست شماره را به گفتگو وصل می‌کند و کد می‌سوزد (مصرفِ دوباره بی‌اثر است)."""
    user = _make_participant(seq=902)
    issued = issue_bale_code(phone_number=user.phone_number)
    assert len(issued["code"]) == 6

    chat = {"id": 555001, "first_name": "کاربر"}
    assert consume_bale_code(raw_text=issued["code"].lower(), chat=chat)["matched"] is True
    subscriber = BaleSubscriber.objects.get(phone_number=user.phone_number)
    assert subscriber.chat_id == 555001

    again = consume_bale_code(raw_text=issued["code"], chat={"id": 999})
    assert again["matched"] is False
    subscriber.refresh_from_db()
    assert subscriber.chat_id == 555001


@override_settings(BALE_BOT_TOKEN="test-token", BALE_BOT_USERNAME="kaveh185_bot")
def test_issue_bale_code_invalidates_previous_code() -> None:
    """درخواستِ دوباره، کدِ قبلی را باطل می‌کند تا فقط آخرین کد معتبر باشد."""
    user = _make_participant(seq=903)
    first = issue_bale_code(phone_number=user.phone_number)
    second = issue_bale_code(phone_number=user.phone_number)
    assert consume_bale_code(raw_text=first["code"], chat={"id": 1})["matched"] is False
    assert consume_bale_code(raw_text=second["code"], chat={"id": 2})["matched"] is True


def test_send_otp_via_bale_reports_not_subscribed() -> None:
    """اگر شماره به ربات وصل نیست، «نشده» را صادقانه برمی‌گرداند (بدونِ استثنا)."""
    user = _make_participant(seq=904)
    with override_settings(BALE_BOT_TOKEN="test-token"):
        assert send_otp_via_bale(phone_number=user.phone_number, code="123456") == {
            "sent": False,
            "reason": "not_subscribed",
        }


@override_settings(BALE_BOT_TOKEN="test-token")
def test_send_otp_via_bale_uses_stored_chat() -> None:
    """وقتی گفتگو ثبت شده، پیام با همان chat_id به بله می‌رود و لاگ ثبت می‌شود."""
    from apps.notifications.bale import BaleResult
    from apps.notifications.models import SMSDeliveryLog

    user = _make_participant(seq=905)
    BaleSubscriber.objects.create(phone_number=user.phone_number, chat_id=4242)

    with patch(
        "apps.notifications.bale.send_bale_message",
        return_value=BaleResult(ok=True, message_id=77),
    ) as sender:
        result = send_otp_via_bale(phone_number=user.phone_number, code="987654")

    assert result == {"sent": True, "reason": "ok"}
    sender.assert_called_once()
    assert sender.call_args.args[0] == 4242
    log = SMSDeliveryLog.objects.get(recipient_phone=user.phone_number)
    assert log.provider == "bale"
    assert "987654" in log.message_text


@override_settings(
    BALE_BOT_TOKEN="test-token", BALE_BOT_USERNAME="kaveh185_bot", BALE_WEBHOOK_SECRET=""
)
def test_webhook_links_phone_when_user_sends_code(
    client: Any,
) -> None:
    """وب‌هوک: کاربر کدِ اتصال را در بله می‌فرستد ⇒ شماره به گفتگو وصل و پیام تأیید می‌رود."""
    user = _make_participant(seq=906)
    code = issue_bale_code(phone_number=user.phone_number)["code"]

    with patch(
        "apps.notifications.views.send_bale_message",
        return_value=BaleResult(ok=True),
    ) as sender:
        response = client.post(
            "/api/v1/notifications/bale/webhook/",
            data={"message": {"chat": {"id": 778899}, "text": code}},
            content_type="application/json",
        )

    assert response.status_code == 200
    assert response.json()["handled"] == "linked"
    assert BaleSubscriber.objects.get(phone_number=user.phone_number).chat_id == 778899
    assert sender.call_args.args[0] == 778899


@override_settings(BALE_WEBHOOK_SECRET="s3cret")
def test_webhook_rejects_wrong_secret(client: Any) -> None:
    """اگر secret تنظیم شده باشد، درخواستِ بدونِ هدرِ درست پذیرفته نمی‌شود."""
    response = client.post(
        "/api/v1/notifications/bale/webhook/",
        data={"message": {"chat": {"id": 1}, "text": "/start"}},
        content_type="application/json",
    )
    assert response.status_code == 403

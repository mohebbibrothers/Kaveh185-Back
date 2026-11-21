"""آزمون‌های کانالِ بله: نرمال‌سازیِ شماره، کدِ اتصال، و انتخابِ کانالِ تحویل."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest
from django.test import override_settings

from apps.notifications.bale import BaleResult
from apps.notifications.models import BaleLinkCode, BaleSubscriber
from apps.notifications.providers import SMSGatewayResult
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


# ══════════════════════════════════════════════════════════════════════════
#  دستورها و وب‌هوک — مسیرهایی که در زمانِ اجرای واقعی قدم می‌زنند، پس
#  نباید بی‌آزمون بمانند (پوششِ خطیِ CI این را جدی می‌گیرد).
# ══════════════════════════════════════════════════════════════════════════


def test_bale_inbox_reads_updates_and_links_phone(
    tmp_path: Any, monkeypatch: Any, settings: Any
) -> None:
    """پیامِ شاملِ شماره در صندوقِ بله خوانده و ثبت می‌شود؛ offset ذخیره می‌گردد."""
    from django.core.management import call_command

    from apps.notifications.management.commands import bale_inbox as inbox_module

    settings.BALE_BOT_TOKEN = "test-token"
    monkeypatch.setattr(inbox_module, "OFFSET_FILE", tmp_path / "offset.json")

    user = _make_participant(seq=920)
    updates = {
        "ok": True,
        "result": [
            {
                "update_id": 41,
                "message": {
                    "chat": {"id": 31337, "first_name": "زهرا", "username": "z"},
                    "from": {"first_name": "زهرا", "username": "z"},
                    "text": user.phone_number.replace("0", "۰", 1),
                },
            }
        ],
    }
    with (
        patch("apps.notifications.management.commands.bale_inbox._api", return_value=updates),
        patch(
            "apps.notifications.management.commands.bale_inbox.send_bale_message",
            return_value=BaleResult(ok=True),
        ) as sender,
    ):
        call_command("bale_inbox", "--verbose")

    assert BaleSubscriber.objects.get(phone_number=user.phone_number).chat_id == 31337
    sender.assert_called_once()
    assert (tmp_path / "offset.json").exists()


def test_bale_inbox_skips_replies_in_dry_run(
    tmp_path: Any, monkeypatch: Any, settings: Any
) -> None:
    """حالتِ `--dry-run` هیچ پیامی نمی‌فرستد و offset را هم جابه‌جا نمی‌کند."""
    from django.core.management import call_command

    from apps.notifications.management.commands import bale_inbox as inbox_module

    settings.BALE_BOT_TOKEN = "test-token"
    monkeypatch.setattr(inbox_module, "OFFSET_FILE", tmp_path / "offset.json")
    updates = {
        "ok": True,
        "result": [{"update_id": 5, "message": {"chat": {"id": 1}, "text": "/start"}}],
    }

    with (
        patch("apps.notifications.management.commands.bale_inbox._api", return_value=updates),
        patch("apps.notifications.management.commands.bale_inbox.send_bale_message") as sender,
    ):
        call_command("bale_inbox", "--dry-run")

    sender.assert_not_called()
    assert not (tmp_path / "offset.json").exists()


def test_bale_inbox_requires_token(settings: Any) -> None:
    """بدونِ توکن، دستور با پیامِ روشن می‌ایستد (نه با خطای مبهم)."""
    from django.core.management import call_command
    from django.core.management.base import CommandError

    settings.BALE_BOT_TOKEN = ""
    with pytest.raises(CommandError):
        call_command("bale_inbox")


def test_deliver_outbox_sends_pending_otp_via_bale(settings: Any) -> None:
    """پیامِ کدِ تأیید که پیامک نشده، از راهِ بله تحویل و در صف «ارسال‌شده» می‌شود."""
    from django.core.management import call_command

    from apps.core.choices import OutboxStatus
    from apps.core.models import OutboxMessage

    settings.BALE_BOT_TOKEN = "test-token"
    user = _make_participant(seq=921)
    BaleSubscriber.objects.create(phone_number=user.phone_number, chat_id=8888)
    message = OutboxMessage.objects.create(
        topic="sms.otp",
        recipient=user.phone_number,
        payload={"phone_number": user.phone_number, "code": "424242"},
    )

    # پیامک در دسترس نیست (همان وضعیتِ واقعیِ حوزه: بدونِ اینماد) ⇒ صف باید
    # از بله فرار کند. اگر درگاه را سالم بگذاریم، همین تست سبز می‌شود بدونِ
    # اینکه مسیرِ پشتیبان را لمس کند — یعنی تستِ بی‌ارزش.
    with (
        patch(
            "apps.notifications.services.send_via_configured_gateway",
            return_value=SMSGatewayResult(
                provider="kavenegar", success=False, provider_message_id="", error_message="down"
            ),
        ),
        patch(
            "apps.notifications.bale.send_bale_message",
            return_value=BaleResult(ok=True, message_id=9),
        ),
    ):
        call_command("deliver_outbox")

    message.refresh_from_db()
    assert message.status == OutboxStatus.SENT
    assert message.last_error == "delivered: bale"


def test_deliver_outbox_dry_run_lists_without_sending(settings: Any) -> None:
    """`--dry-run` فقط فهرست می‌کند؛ چیزی ارسال و چیزی تغییر نمی‌شود."""
    from django.core.management import call_command

    from apps.core.choices import OutboxStatus
    from apps.core.models import OutboxMessage

    settings.BALE_BOT_TOKEN = "test-token"
    row = OutboxMessage.objects.create(topic="sms.otp", recipient="09121234567", payload={})
    call_command("deliver_outbox", "--dry-run")
    row.refresh_from_db()
    assert row.status == OutboxStatus.PENDING


@override_settings(BALE_BOT_TOKEN="test-token")
def test_webhook_handles_start_phone_and_unknown_paths(client: Any) -> None:
    """سه ورودیِ رایجِ کاربر در بله: `/start`، شماره، و متنِ نامفهوم — همه پاسخ می‌گیرند."""
    user = _make_participant(seq=922)
    with patch(
        "apps.notifications.views.send_bale_message", return_value=BaleResult(ok=True)
    ) as sender:
        for text, expected in (
            ("/start", "start"),
            (user.phone_number, "phone"),
            ("سلام", "unknown"),
        ):
            response = client.post(
                "/api/v1/notifications/bale/webhook/",
                data={"message": {"chat": {"id": 4321}, "text": text}},
                content_type="application/json",
            )
            assert response.status_code == 200
            assert response.json()["handled"] == expected
    assert sender.call_count == 3


@override_settings(BALE_BOT_TOKEN="test-token", BALE_BOT_USERNAME="kaveh185_bot")
def test_bale_status_endpoint_reports_link_state(client: Any) -> None:
    """گامِ دومِ فرم باید بداند شماره وصل است یا نه — بدونِ افشای اطلاعاتِ دیگر."""
    user = _make_participant(seq=923)
    BaleSubscriber.objects.create(phone_number=user.phone_number, chat_id=99)
    res = client.get(f"/api/v1/notifications/bale/status/?phone_number={user.phone_number}")
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["linked"] is True
    assert data["bot_username"] == "kaveh185_bot"


def test_webhook_ignores_payload_without_chat(client: Any) -> None:
    """آپدیتِ بدونِ گفتگو (مثلاً ویرایشِ پیام) نباید خطا بدهد."""
    res = client.post(
        "/api/v1/notifications/bale/webhook/",
        data={"edited_message": {"text": "x"}},
        content_type="application/json",
    )
    assert res.status_code == 200
    assert res.json()["handled"] == "no_chat"


# ══════════════════════════════════════════════════════════════════════════
#  لایهٔ HTTPِ بله — بدونِ شبکه، با جایگزینِ `urlopen`
#  این بخش مهم است چون تنها جایی است که توکن در URL می‌نشیند؛ هر خطایش
#  می‌تواند توکن را در لاگ یا پیامِ خطا بیرون بدهد.
# ══════════════════════════════════════════════════════════════════════════


class _FakeResponse:
    """پاسخِ جعلیِ urlopen با همان رفتارِ زمینه‌ای (`with`)."""

    def __init__(self, body: str, status: int = 200) -> None:
        self._body = body.encode("utf-8")
        self.status = status

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *exc: object) -> None:
        return None


def test_api_raises_when_token_missing(settings: Any) -> None:
    """بدونِ توکن، خطای مشخص می‌دهد (نه تماسِ بی‌فایده به بله)."""
    from apps.notifications.bale import BaleNotConfigured, _api

    settings.BALE_BOT_TOKEN = ""
    with pytest.raises(BaleNotConfigured):
        _api("getMe")


def test_api_returns_json_on_success(settings: Any) -> None:
    """پاسخِ سالم به دیکشنری تبدیل می‌شود و URL همان مسیرِ رسمیِ بله است."""
    from apps.notifications import bale

    settings.BALE_BOT_TOKEN = "test-token"
    settings.BALE_API_BASE = "https://tapi.bale.ai"
    with patch.object(
        bale.urllib_request,
        "urlopen",
        return_value=_FakeResponse('{"ok": true, "result": {"username": "k185"}}'),
    ) as opener:
        payload = bale._api("getMe")
    assert payload["result"]["username"] == "k185"
    assert "bot test-token" not in str(opener.call_args)


def test_api_wraps_http_error_without_leaking_token(settings: Any) -> None:
    """خطای HTTP به `BaleError` کوتاه تبدیل می‌شود و توکن در پیام نیست."""
    from apps.notifications import bale

    settings.BALE_BOT_TOKEN = "super-secret-token"
    with (
        patch.object(bale.urllib_request, "urlopen", return_value=_FakeResponse("{}", 401)),
        pytest.raises(bale.BaleError) as exc,
    ):
        bale._api("sendMessage", {"chat_id": 1, "text": "x"})
    assert "super-secret-token" not in str(exc.value)
    assert "401" in str(exc.value)


def test_api_wraps_network_error(settings: Any) -> None:
    """قطعیِ شبکه ⇒ خطای خوانا با نوعِ خطا، نه استثنای خامِ urllib."""
    from apps.notifications import bale

    settings.BALE_BOT_TOKEN = "test-token"
    with (
        patch.object(bale.urllib_request, "urlopen", side_effect=TimeoutError("boom")),
        pytest.raises(bale.BaleError) as exc,
    ):
        bale._api("getMe")
    assert "TimeoutError" in str(exc.value)


def test_api_rejects_unparsable_body(settings: Any) -> None:
    """پاسخِ غیر-JSON (مثلاً صفحهٔ خطای میزبان) ⇒ خطای مشخص."""
    from apps.notifications import bale

    settings.BALE_BOT_TOKEN = "test-token"
    with (
        patch.object(bale.urllib_request, "urlopen", return_value=_FakeResponse("<html>")),
        pytest.raises(bale.BaleError),
    ):
        bale._api("getMe")


def test_send_bale_message_reports_failure_instead_of_raising(settings: Any) -> None:
    """خطای درگاه به `BaleResult(ok=False)` تبدیل می‌شود؛ مسیرِ ثبت‌نام نمی‌شکند."""
    from apps.notifications import bale

    settings.BALE_BOT_TOKEN = "test-token"
    with patch.object(bale.urllib_request, "urlopen", side_effect=OSError("down")):
        result = bale.send_bale_message(123, "سلام")
    assert result.ok is False
    assert result.chat_id == 123
    assert result.detail


def test_get_me_extracts_username(settings: Any) -> None:
    """`get_me` نامِ کاربریِ ربات را برمی‌گرداند (برای تستِ اتصال در استقرار)."""
    from apps.notifications import bale

    settings.BALE_BOT_TOKEN = "test-token"
    with patch.object(
        bale.urllib_request,
        "urlopen",
        return_value=_FakeResponse(
            '{"ok": true, "result": {"username": "kaveh185_bot", "first_name": "کاوه"}}'
        ),
    ):
        info = bale.get_me()
    assert info == {"ok": True, "username": "kaveh185_bot", "name": "کاوه"}


# ══════════════════════════════════════════════════════════════════════════
#  `bale_check` — بازرسیِ آمادگیِ کانال پیش از اعلامِ عمومی
# ══════════════════════════════════════════════════════════════════════════


def _run_check(settings: Any, *, me: dict | None = None, webhook: str = "") -> str:
    """اجرای `bale_check` با پاسخ‌های جعلیِ بله و برگرداندنِ متنِ گزارش."""
    from io import StringIO

    from django.core.management import call_command

    settings.BALE_BOT_TOKEN = "test-token"
    settings.BALE_BOT_USERNAME = "Kaveh185_bot"

    def fake_api(method: str, payload: object = None, **_: object) -> dict:
        if method == "getMe":
            return {"ok": True, "result": me or {"username": "Kaveh185_bot", "first_name": "کاوه"}}
        if method == "getWebhookInfo":
            return {"ok": True, "result": {"url": webhook}}
        return {"ok": True, "result": {}}

    out = StringIO()
    with (
        patch("apps.notifications.bale._api", side_effect=fake_api),
        patch(
            "apps.notifications.bale.get_me",
            side_effect=lambda: {
                "ok": True,
                "username": (me or {}).get("username", "Kaveh185_bot"),
                "name": (me or {}).get("first_name", "کاوه"),
            },
        ),
    ):
        call_command("bale_check", stdout=out)
    return out.getvalue()


def test_bale_check_flags_missing_webhook_and_secret(settings: Any) -> None:
    """بدونِ وب‌هوک و کلید، گزارش باید صریح بگوید چه چیزی کم است."""
    settings.BALE_WEBHOOK_SECRET = ""
    text = _run_check(settings)
    assert "وب‌هوک تنظیم نشده" in text
    assert "BALE_WEBHOOK_SECRET" in text
    assert "هنوز آماده نیست" in text


def test_bale_check_flags_username_mismatch(settings: Any) -> None:
    """اگر نامِ کاربریِ ربات با تنظیمات یکی نباشد، پیوندِ فرم اشتباه می‌شود."""
    settings.BALE_WEBHOOK_SECRET = "s3cret"
    text = _run_check(
        settings, me={"username": "kaveh_new_bot", "first_name": "کاوه"}, webhook="https://x/y"
    )
    assert "یکی نیست" in text


def test_bale_check_reports_ready_when_all_green(settings: Any) -> None:
    """وقتی توکن، وب‌هوک، کلید و یک کاربرِ وصل‌شده هست، جمع‌بندی مثبت است."""
    settings.BALE_WEBHOOK_SECRET = "s3cret"
    user = _make_participant(seq=930)
    BaleSubscriber.objects.create(phone_number=user.phone_number, chat_id=555)
    text = _run_check(
        settings, webhook="https://api.kaveh185.ir/api/v1/notifications/bale/webhook/"
    )
    assert "همه‌چیز آماده است" in text


def test_bale_check_sends_test_message_only_to_linked_number(settings: Any) -> None:
    """پیامِ آزمایشی برای شمارهٔ وصل‌نشده ارسال نمی‌شود و راهنمایی می‌دهد."""
    from io import StringIO

    from django.core.management import call_command

    settings.BALE_BOT_TOKEN = "test-token"
    settings.BALE_WEBHOOK_SECRET = "s3cret"
    out = StringIO()
    with (
        patch(
            "apps.notifications.bale._api",
            return_value={"ok": True, "result": {"username": "Kaveh185_bot", "url": "https://x"}},
        ),
        patch(
            "apps.notifications.bale.get_me",
            return_value={"ok": True, "username": "Kaveh185_bot", "name": "کاوه"},
        ),
    ):
        call_command("bale_check", "--send-to", "09120000000", stdout=out)
    assert "به ربات وصل نیست" in out.getvalue()


@override_settings(BALE_WEBHOOK_SECRET="s3cret", BALE_BOT_TOKEN="test-token")
def test_webhook_accepts_bale_secret_header(client: Any) -> None:
    """بله کلید را در `X-Telegram-Bot-Api-Secret-Token` می‌فرستد، نه `X-Bale-Secret`.

    اگر فقط هدرِ دومی پذیرفته شود، کلید عملاً بی‌اثر است و وب‌هوک برای همه باز
    می‌ماند — یعنی هر کسی می‌تواند گفتگوی خودش را به شمارهٔ دلخواه بچسباند.
    """
    response = client.post(
        "/api/v1/notifications/bale/webhook/",
        data={"message": {"chat": {"id": 12}, "text": "سلام"}},
        content_type="application/json",
        headers={"X-Telegram-Bot-Api-Secret-Token": "s3cret"},
    )
    assert response.status_code == 200


@override_settings(BALE_BOT_TOKEN="test-token", BALE_WEBHOOK_SECRET="s3cret")
def test_webhook_get_reports_health_without_leaking_secret(client: Any) -> None:
    """`GET` سلامت را می‌گوید (برای setWebhook) و هرگز خودِ کلید را برنمی‌گرداند."""
    response = client.get("/api/v1/notifications/bale/webhook/")
    assert response.status_code == 200
    body = response.json()
    assert body["secret_required"] is True
    assert "s3cret" not in str(body)


@override_settings(BALE_BOT_TOKEN="", BALE_WEBHOOK_SECRET="")
def test_webhook_never_500s_when_bale_is_unconfigured(client: Any) -> None:
    """نبودِ توکن نباید وب‌هوک را ۵۰۰ کند.

    چرا مهم است؟ بله پاسخِ غیرِ۲۰۰ را «تحویل نشد» می‌بیند و **همان آپدیت را
    بی‌پایان دوباره می‌فرستد**؛ یک تنظیمِ جاافتاده نباید به حلقهٔ بی‌پایان
    تبدیل شود. وب‌هوک همیشه ۲۰۰ می‌دهد و فقط `replied=false` را گزارش می‌کند.
    """
    response = client.post(
        "/api/v1/notifications/bale/webhook/",
        data={"message": {"chat": {"id": 77}, "text": "/start"}},
        content_type="application/json",
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["replied"] is False


@override_settings(BALE_BOT_TOKEN="test-token", BALE_BOT_USERNAME="")
def test_status_falls_back_to_live_bot_username(client: Any) -> None:
    """اگر نامِ کاربری در تنظیمات خالی باشد، از خودِ بله خوانده می‌شود.

    چرا؟ نامِ اشتباه یعنی کاربر به رباتِ دیگری می‌رود و کدش هیچ‌وقت نمی‌آید؛
    منبعِ حقیقت باید خودِ بله باشد، نه یک خط در `.env`.
    """
    with patch(
        "apps.notifications.views.get_me", return_value={"ok": True, "username": "Kaveh185_bot"}
    ):
        res = client.get("/api/v1/notifications/bale/status/?phone_number=09121234567")
    assert res.json()["data"]["bot_username"] == "Kaveh185_bot"


@override_settings(BALE_BOT_TOKEN="", BALE_BOT_USERNAME="")
def test_status_survives_unreachable_bale(client: Any) -> None:
    """اگر بله در دسترس نبود، وضعیت باز هم پاسخ می‌دهد (بدونِ نامِ کاربری)."""
    res = client.get("/api/v1/notifications/bale/status/?phone_number=09121234567")
    assert res.status_code == 200
    assert res.json()["data"]["bot_username"] == ""


# ══════════════════════════════════════════════════════════════════════════
#  `bale_webhook` — ثبت/بازرسی/حذفِ وب‌هوک بدونِ دستِ کاربر روی URL
# ══════════════════════════════════════════════════════════════════════════


def _call_webhook(settings: Any, *args: str, api: Any = None) -> str:
    """اجرای `bale_webhook` با پاسخِ جعلیِ بله و برگرداندنِ متنِ خروجی."""
    from io import StringIO

    from django.core.management import call_command

    settings.BALE_BOT_TOKEN = "test-token"
    fake = api or (lambda method, payload=None, **_: {"ok": True, "result": True})
    out = StringIO()
    with patch("apps.notifications.bale._api", side_effect=fake):
        call_command("bale_webhook", *args, stdout=out)
    return out.getvalue()


def test_webhook_command_builds_url_from_allowed_hosts(settings: Any) -> None:
    """نشانی از دامنهٔ `api.` در `ALLOWED_HOSTS` ساخته می‌شود (نه از حدس)."""
    settings.ALLOWED_HOSTS = ["kaveh185.ir", "api.kaveh185.ir"]
    text = _call_webhook(settings, "--print-url")
    assert text.strip() == "https://api.kaveh185.ir/api/v1/notifications/bale/webhook/"


def test_webhook_command_requires_secret_or_warns(settings: Any) -> None:
    """بدونِ کلید، ثبت انجام می‌شود ولی هشدارِ امنیتی صریح داده می‌شود."""
    settings.ALLOWED_HOSTS = ["api.kaveh185.ir"]
    settings.BALE_WEBHOOK_SECRET = ""
    called: list[str] = []
    captured: dict[str, object] = {}

    def fake(method: str, payload: object = None, **_: object) -> dict:
        called.append(method)
        if method == "setWebhook":
            captured.update(payload or {})
        if method == "getWebhookInfo":
            return {
                "ok": True,
                "result": {"url": "https://api.kaveh185.ir/x", "pending_update_count": 0},
            }
        return {"ok": True, "result": True}

    text = _call_webhook(settings, api=fake)
    assert "secret_token" not in captured  # کلیدِ خالی نباید فرستاده شود
    assert "BALE_WEBHOOK_SECRET خالی است" in text
    assert "setWebhook" in called


def test_webhook_new_secret_generates_key_without_calling_bale(settings: Any) -> None:
    """`--new-secret` کلید می‌سازد و آن را برای گذاشتن در `.env` چاپ می‌کند."""
    settings.ALLOWED_HOSTS = ["api.kaveh185.ir"]
    settings.BALE_WEBHOOK_SECRET = ""
    text = _call_webhook(settings, "--new-secret")
    assert "BALE_WEBHOOK_SECRET=" in text
    assert len(text.split("BALE_WEBHOOK_SECRET=")[1].split()[0]) >= 40


def test_webhook_show_explains_delivery_error(settings: Any) -> None:
    """اگر بله نتوانسته به نشانی برسد، گزارش باید دلیل و راهِ حل را بگوید."""
    settings.ALLOWED_HOSTS = ["api.kaveh185.ir"]

    def fake(method: str, payload: object = None, **_: object) -> dict:
        info = {
            "url": "https://api.kaveh185.ir/api/v1/notifications/bale/webhook/",
            "pending_update_count": 4,
            "last_error_message": "Wrong response from the webhook: 404 Not Found",
            "last_error_code": 404,
        }
        return {"ok": True, "result": info if method == "getWebhookInfo" else True}

    text = _call_webhook(settings, "--show", api=fake)
    assert "آپدیتِ در انتظار: 4" in text
    assert "۴۰۳/۴۰۴" in text


def test_webhook_delete_reports_success(settings: Any) -> None:
    """`--delete` وب‌هوک را برمی‌دارد و می‌گوید از این پس کران باید بخواند."""
    settings.ALLOWED_HOSTS = ["api.kaveh185.ir"]
    text = _call_webhook(settings, "--delete")
    assert "برداشته شد" in text


# ══════════════════════════════════════════════════════════════════════════
#  `bale_setup` — راه‌اندازیِ یک‌مرحله‌ای (`نوشتنِ .env` + تستِ تماس + وب‌هوک)
# ══════════════════════════════════════════════════════════════════════════

VALID_TOKEN = "123456789:AAHfakeTokenForTests_abcdefghijklmnop"


def _write_env(tmp_path: Any) -> Any:
    """یک `.env` نمونه با همان کلیدهای رمزِ واقعی می‌سازد."""
    path = tmp_path / ".env"
    path.write_text(
        "DJANGO_SECRET_KEY=keep-me\nDB_PASSWORD=keep-me-too\nBALE_BOT_TOKEN=\n",
        encoding="utf-8",
    )
    return path


def test_bale_setup_writes_env_keeps_other_keys_and_never_prints_token(
    tmp_path: Any, settings: Any
) -> None:
    """توکن در `.env` نوشته می‌شود، بقیهٔ کلیدها دست‌نخورده می‌مانند و چاپ نمی‌شود."""
    from io import StringIO

    from django.core.management import call_command

    env = _write_env(tmp_path)
    settings.BALE_API_BASE = "https://tapi.bale.ai"
    settings.ALLOWED_HOSTS = ["api.kaveh185.ir"]
    out = StringIO()
    with (
        patch(
            "apps.notifications.bale.get_me",
            return_value={"ok": True, "username": "Kaveh185_bot", "name": "کاوه"},
        ),
        patch("apps.notifications.bale._api", return_value={"ok": True, "result": True}),
    ):
        call_command(
            "bale_setup",
            f"--token={VALID_TOKEN}",
            f"--env-file={env}",
            "--secret=testsecret",
            stdout=out,
        )

    text = env.read_text(encoding="utf-8")
    assert f"BALE_BOT_TOKEN={VALID_TOKEN}" in text
    assert "BALE_BOT_USERNAME=Kaveh185_bot" in text  # از getMe، نه از حدس
    assert "BALE_WEBHOOK_SECRET=testsecret" in text
    assert "DJANGO_SECRET_KEY=keep-me" in text  # تنظیماتِ دیگر حفظ می‌شوند
    assert "DB_PASSWORD=keep-me-too" in text
    assert VALID_TOKEN not in out.getvalue()  # توکن هرگز چاپ نمی‌شود
    assert (tmp_path / ".env.bak").exists()  # پشتیبان
    assert "Restart" in out.getvalue()  # یادآوریِ restart پروسه


def test_bale_setup_rejects_malformed_token(tmp_path: Any) -> None:
    """توکنِ بدشکل پیش از هر نوشتنی رد می‌شود (`.env` نباید خراب شود)."""
    import pytest as _pytest
    from django.core.management import call_command
    from django.core.management.base import CommandError

    env = _write_env(tmp_path)
    with _pytest.raises(CommandError):
        call_command("bale_setup", "--token=not-a-token", f"--env-file={env}")
    assert "BALE_BOT_TOKEN=\n" in env.read_text(encoding="utf-8")


def test_bale_setup_status_explains_restart_need(tmp_path: Any, settings: Any) -> None:
    """اگر توکن در فایل هست ولی پروسه نمی‌بیندش، علت و راه‌حل صریح گفته می‌شود."""
    from io import StringIO

    from django.core.management import call_command

    env = tmp_path / ".env"
    env.write_text(f"BALE_BOT_TOKEN={VALID_TOKEN}\n", encoding="utf-8")
    settings.BALE_BOT_TOKEN = ""
    out = StringIO()
    call_command("bale_setup", "--status", f"--env-file={env}", stdout=out)
    text = out.getvalue()
    assert "در فایل: هست" in text or "در `" in text
    assert "restart" in text.lower()

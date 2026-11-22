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


def _run_check2(settings: Any, webhook_info: dict, *args: str) -> str:
    """اجرای `bale_check` با `getWebhookInfo` مشخص و برگرداندنِ گزارش."""
    from io import StringIO

    from django.core.management import call_command

    settings.BALE_BOT_TOKEN = "test-token"
    settings.BALE_BOT_USERNAME = "kaveh185_bot"
    settings.BALE_WEBHOOK_SECRET = "s3cret"

    def fake(method: str, payload: object = None, **_: object) -> dict:
        if method == "getWebhookInfo":
            return {"ok": True, "result": webhook_info}
        return {"ok": True, "result": {"username": "kaveh185_bot", "first_name": "کاوه"}}

    out = StringIO()
    with (
        patch("apps.notifications.bale._api", side_effect=fake),
        patch(
            "apps.notifications.bale.get_me",
            return_value={"ok": True, "username": "kaveh185_bot", "name": "کاوه"},
        ),
    ):
        call_command("bale_check", *args, stdout=out)
    return out.getvalue()


def test_bale_check_flags_webhook_that_bale_cannot_reach(settings: Any) -> None:
    """«وب‌هوک ثبت شد» با «وب‌هوک کار می‌کند» یکی نیست.

    بله اگر به نشانی نرسد، خطا را فقط در `getWebhookInfo` نگه می‌دارد. اگر
    گزارش این را نگوید، کاربر «شروع» می‌زند و هیچ پاسخی نمی‌گیرد — بی‌صدا.
    """
    text = _run_check2(
        settings,
        {
            "url": "https://api.kaveh185.ir/api/v1/notifications/bale/webhook/",
            "last_error_message": "Wrong response from the webhook: 404 Not Found",
            "pending_update_count": 3,
        },
    )
    assert "بله نتوانسته به وب‌هوک برسد" in text
    assert "آپدیت در صفِ بله مانده" in text
    assert "کرانِ `bale_inbox`" in text


def test_bale_check_zero_linked_users_is_normal_not_a_blocker(settings: Any) -> None:
    """کاربرِ وصل‌نشده مانعِ آماده‌بودن نیست؛ هر کاربر در فرم خودش وصل می‌شود."""
    with patch.object(BaleSubscriber.objects, "filter") as _filter:
        pass  # فقط برای خوانایی؛ شمارشِ واقعی صفر است
    text = _run_check2(
        settings,
        {"url": "https://api.kaveh185.ir/x", "pending_update_count": 0},
    )
    assert "طبیعی است" in text
    assert "همه‌چیز آماده است" in text


def test_bale_check_ping_explains_live_webhook_test(settings: Any) -> None:
    """`--ping-webhook` می‌گوید برای آزمونِ زنده دقیقاً چه کاری لازم است."""
    text = _run_check2(
        settings,
        {"url": "https://api.kaveh185.ir/x", "pending_update_count": 0},
        "--ping-webhook",
    )
    assert "آزمونِ زندهٔ وب‌هوک" in text
    assert "سالم به نظر می‌رسد" in text


def test_bale_check_without_webhook_explains_the_silent_trap(settings: Any) -> None:
    """اگر نه وب‌هوک باشد نه کران، کاربر «شروع» می‌زند و هیچ پاسخی نمی‌گیرد.

    این تفکیک مهم است چون در گزارش، «وب‌هوک تنظیم نشده» فقط یک هشدارِ ملایم
    به نظر می‌رسد؛ در واقع یعنی هیچ‌کس پیامِ کاربر را نمی‌خواند.
    """
    text = _run_check2(settings, {"url": "", "pending_update_count": 1})
    assert "هیچ پاسخی نمی‌گیرد" in text
    assert "نه وب‌هوک ثبت است" in text
    assert "هنوز آماده نیست" in text


def test_bale_check_ping_without_webhook_says_where_the_message_is(settings: Any) -> None:
    """با `--ping-webhook` و بدونِ وب‌هوک، پیام در صفِ getUpdates است — همان را می‌گوید."""
    text = _run_check2(settings, {"url": "", "pending_update_count": 1}, "--ping-webhook")
    assert "صفِ `getUpdates`" in text


# ══════════════════════════════════════════════════════════════════════════
#  منطقِ مشترکِ پیامِ ورودی (وب‌هوک و `bale_inbox` یک رفتار دارند)
# ══════════════════════════════════════════════════════════════════════════


@override_settings(BALE_BOT_TOKEN="test-token")
def test_start_command_explains_next_step_instead_of_dead_end() -> None:
    """`/start` باید بگوید «از سامانه کدِ اتصال بگیرید»، نه فقط خوش‌آمد.

    پیامِ مبهم یعنی کاربر همان‌جا می‌ماند و ثبت‌نام را رها می‌کند؛ این متن
    کوتاه‌ترین مسیر تا گامِ دوم را می‌گوید.
    """
    from apps.notifications.views import process_bale_message

    result = process_bale_message(chat={"id": 1}, text="/start")
    assert result["handled"] == "start"
    assert "کدِ اتصال" in result["reply"]
    assert "09121234567" in result["reply"]


@override_settings(BALE_BOT_TOKEN="test-token", BALE_BOT_USERNAME="kaveh185_bot")
def test_start_with_code_links_in_one_message() -> None:
    """`/start A7K2QF` هم مثلِ فرستادنِ کدِ خالی کار می‌کند.

    کاربر چیزی که کپی کرده را کنارِ دستورِ شروع می‌چسباند؛ اگر این را
    «دستورِ نامفهوم» بشماریم، اتصال برقرار نمی‌شود و کد هیچ‌وقت نمی‌آید.
    """
    from apps.notifications.views import process_bale_message
    from conftest import create_test_participant as _mk

    user = _mk(seq=940)
    code = issue_bale_code(phone_number=user.phone_number)["code"]
    result = process_bale_message(chat={"id": 4242}, text=f"/start {code}")
    assert result["handled"] == "linked"
    assert BaleSubscriber.objects.get(phone_number=user.phone_number).chat_id == 4242


@override_settings(BALE_BOT_TOKEN="test-token", BALE_BOT_USERNAME="kaveh185_bot")
def test_linking_with_active_challenge_triggers_fresh_code() -> None:
    """اگر چالشِ فعالی برای شماره باشد، بعد از اتصال یک کدِ تازه هم می‌رود.

    چرا؟ کاربر معمولاً کد ارسال را زودتر زده و ممکن است صفحه را رفرش کرده
    باشد؛ فرستادنِ کدِ تازه در همان لحظه، یک رفت‌وبرگشتِ کامل را حذف می‌کند.
    """
    from apps.authentication.services import create_and_send_otp
    from apps.notifications.views import process_bale_message
    from conftest import create_test_participant as _mk

    user = _mk(seq=941, is_phone_verified=False)
    create_and_send_otp(phone_number=user.phone_number)
    code = issue_bale_code(phone_number=user.phone_number)["code"]

    result = process_bale_message(chat={"id": 5555}, text=code)
    assert result["handled"] == "linked"
    assert result.get("resend_otp_for") == user.phone_number


def test_webhook_self_test_detects_wrong_host(settings: Any) -> None:
    """ثبتِ وب‌هوک با نشانیِ اشتباه باید همان لحظه لو برود، نه فردا.

    `setWebhook` همیشه می‌گوید «ثبت شد»؛ تنها راهِ فهمیدنِ درست بودن، زدنِ
    همان نشانی از بیرون است. این تست همان بررسی را با پاسخِ ۴۰۴ می‌سنجد.
    """
    import urllib.error

    from apps.notifications.management.commands.bale_webhook import Command

    cmd = Command()
    with patch(
        "urllib.request.urlopen",
        side_effect=urllib.error.HTTPError("u", 404, "Not Found", {}, None),  # type: ignore[arg-type]
    ):
        assert cmd._self_test("https://www.kaveh185.ir/api/v1/notifications/bale/webhook/") is False


def test_webhook_self_test_accepts_real_health_payload(settings: Any) -> None:
    """پاسخِ سلامتِ خودِ اپلیکیشن ⇒ سالم (وگرنه هر ۲۰۰ای کافی بود)."""
    from apps.notifications.management.commands.bale_webhook import Command

    class _Resp:
        status = 200

        def read(self, n: int = -1) -> bytes:
            return b'{"ok": true, "service": "kaveh185-bale-webhook"}'

        def __enter__(self) -> _Resp:
            return self

        def __exit__(self, *exc: object) -> None:
            return None

    cmd = Command()
    with patch("urllib.request.urlopen", return_value=_Resp()):
        assert cmd._self_test("https://api.kaveh185.ir/api/v1/notifications/bale/webhook/") is True


def test_webhook_self_test_rejects_foreign_200(settings: Any) -> None:
    """۲۰۰ِ صفحهٔ دیگری (مثلاً HTMLِ سایت) «سالم» حساب نمی‌شود."""
    from apps.notifications.management.commands.bale_webhook import Command

    class _Resp:
        status = 200

        def read(self, n: int = -1) -> bytes:
            return b"<html>not the api</html>"

        def __enter__(self) -> _Resp:
            return self

        def __exit__(self, *exc: object) -> None:
            return None

    cmd = Command()
    with patch("urllib.request.urlopen", return_value=_Resp()):
        assert cmd._self_test("https://kaveh185.ir/x/") is False


def test_bale_inbox_refuses_to_race_with_active_webhook(
    settings: Any, tmp_path: Any, monkeypatch: Any
) -> None:
    """با وب‌هوکِ فعال، `bale_inbox` باید توضیح بدهد، نه اینکه ساکت چیزی نخواند.

    بله آپدیت‌ها را به وب‌هوک تحویل می‌دهد و `getUpdates` خالی می‌ماند؛ کاربر
    از خروجیِ خالی نتیجه می‌گیرد «ربات خراب است».
    """
    from io import StringIO

    from django.core.management import call_command

    from apps.notifications.management.commands import bale_inbox as inbox_module

    settings.BALE_BOT_TOKEN = "test-token"
    monkeypatch.setattr(inbox_module, "OFFSET_FILE", tmp_path / "offset.json")
    out = StringIO()
    with (
        patch(
            "apps.notifications.management.commands.bale_inbox._api",
            return_value={"ok": True, "result": {"url": "https://api.kaveh185.ir/x"}},
        ),
        patch("apps.notifications.management.commands.bale_inbox.send_bale_message") as sender,
    ):
        call_command("bale_inbox", stdout=out)
    assert "وب‌هوک فعال است" in out.getvalue()
    sender.assert_not_called()


def test_bale_check_fix_re_registers_broken_webhook(settings: Any) -> None:
    """`bale_check --fix` وب‌هوکِ شکسته را دوباره ثبت می‌کند (نقشِ نگهبانِ کران)."""
    from io import StringIO

    from django.core.management import call_command

    settings.BALE_BOT_TOKEN = "test-token"
    settings.BALE_WEBHOOK_SECRET = "s3cret"
    settings.ALLOWED_HOSTS = ["api.kaveh185.ir"]
    calls: list[str] = []

    def fake(method: str, payload: object = None, **_: object) -> dict:
        calls.append(method)
        if method == "getWebhookInfo":
            return {"ok": True, "result": {"url": "", "pending_update_count": 2}}
        return {"ok": True, "result": True}

    out = StringIO()
    with (
        patch("apps.notifications.bale._api", side_effect=fake),
        patch(
            "apps.notifications.bale.get_me",
            return_value={"ok": True, "username": "kaveh185_bot", "name": "کاوه"},
        ),
        patch(
            "apps.notifications.management.commands.bale_webhook.Command._self_test",
            return_value=True,
            create=True,
        ),
    ):
        call_command("bale_check", "--fix", stdout=out)

    assert "setWebhook" in calls  # دوباره ثبت شد
    assert "ترمیم" in out.getvalue() or "ثبتِ دوباره" in out.getvalue()


@override_settings(BALE_WEBHOOK_SECRET="s3cret", BALE_BOT_TOKEN="test-token")
def test_probe_webhook_call_does_not_message_anyone(client: Any) -> None:
    """آزمونِ حلقه‌ای همان مسیرِ واقعی را می‌زند ولی به هیچ گفتگویی پیام نمی‌دهد."""
    with patch("apps.notifications.views.send_bale_message") as sender:
        res = client.post(
            "/api/v1/notifications/bale/webhook/",
            data={"_probe": True, "message": {"chat": {"id": 1}, "text": "/start"}},
            content_type="application/json",
            headers={"X-Telegram-Bot-Api-Secret-Token": "s3cret"},
        )
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert body["handled"] == "start"
    assert body["replied"] is None
    sender.assert_not_called()


def test_loopback_test_reports_mismatched_secret(settings: Any) -> None:
    """اگر کلید جابه‌جا باشد، همان‌جا ۴۰۳ تشخیص داده می‌شود."""
    import urllib.error

    from apps.notifications.management.commands.bale_webhook import Command

    settings.BALE_WEBHOOK_SECRET = "new"
    cmd = Command()
    with (
        patch.object(Command, "_self_test", return_value=True, create=True),
        patch(
            "urllib.request.urlopen",
            side_effect=urllib.error.HTTPError("u", 403, "Forbidden", {}, None),  # type: ignore[arg-type]
        ),
    ):
        cmd._loopback_test("https://api.kaveh185.ir/api/v1/notifications/bale/webhook/")


def test_webhook_is_csrf_exempt() -> None:
    """بله کوکی و توکنِ مرورگر ندارد؛ اگر CSRF فعال بماند، هر POST با ۴۰۳ رد می‌شود.

    این خطا در آزمونِ دستی پیدا نمی‌شود (چون `Client` خودش توکن می‌سازد) و
    فقط در دنیای واقعی به شکلِ «ربات ساکت است» ظاهر می‌شود.
    """
    from apps.notifications.views import BaleWebhookAPIView

    assert BaleWebhookAPIView.csrf_exempt is True


def test_send_start_reregisters_webhook_without_dropping_updates(settings: Any) -> None:
    """`bale_check --send-start` وب‌هوک را بازثبت می‌کند و صف را دور نمی‌ریزد."""
    from io import StringIO

    from django.core.management import call_command

    settings.BALE_BOT_TOKEN = "test-token"
    settings.BALE_WEBHOOK_SECRET = "s3cret"
    settings.BALE_WEBHOOK_URL = "https://api.kaveh185.ir/api/v1/notifications/bale/webhook/"
    calls: list[tuple[str, dict]] = []

    def fake(method: str, payload: object = None, **_: object) -> dict:
        calls.append((method, dict(payload or {})))
        if method == "getWebhookInfo":
            return {"ok": True, "result": {"url": settings.BALE_WEBHOOK_URL}}
        return {"ok": True, "result": True}

    out = StringIO()
    with (
        patch("apps.notifications.bale._api", side_effect=fake),
        patch(
            "apps.notifications.bale.get_me",
            return_value={"ok": True, "username": "kaveh185_bot", "name": "کاوه"},
        ),
    ):
        call_command("bale_check", "--send-start", stdout=out)

    methods = [m for m, _ in calls]
    assert "deleteWebhook" in methods and "setWebhook" in methods
    drop = dict(calls[methods.index("deleteWebhook")][1])
    assert drop.get("drop_pending_updates") is False  # پیام‌های معطل حفظ می‌شوند


@override_settings(BALE_WEBHOOK_SECRET="s3cret", BALE_WEBHOOK_URL="https://api.kaveh185.ir/x/")
def test_health_endpoint_exposes_fingerprint_but_not_the_secret(client: Any) -> None:
    """مرورگر باید بتواند بفهمد دو طرف یک کلید دارند، بدونِ دیدنِ خودِ کلید."""
    res = client.get("/api/v1/notifications/bale/webhook/")
    body = res.json()
    assert res.status_code == 200
    assert body["secret_fingerprint"] and body["secret_fingerprint"] != "s3cret"
    assert "s3cret" not in str(body)
    assert len(body["secret_fingerprint"]) == 6


@override_settings(BALE_WEBHOOK_SECRET="")
def test_webhook_survives_broken_json_body(client: Any) -> None:
    """بدنهٔ خراب ⇒ ۲۰۰ با `no_chat`، نه ۵۰۰ (۵۰۰ = تحویلِ بی‌پایانِ همان آپدیت)."""
    res = client.post(
        "/api/v1/notifications/bale/webhook/",
        data=b"not-json",
        content_type="application/json",
    )
    assert res.status_code == 200


@override_settings(BALE_WEBHOOK_SECRET="s3cret")
def test_webhook_returns_ok_even_if_processing_explodes(client: Any) -> None:
    """اگر پردازشِ پیام بترکد، ۲۰۰ با `handled=error` برمی‌گردد، نه ۵۰۰."""
    with patch("apps.notifications.views.process_bale_message", side_effect=RuntimeError("boom")):
        res = client.post(
            "/api/v1/notifications/bale/webhook/",
            data={"message": {"chat": {"id": 5}, "text": "/start"}},
            content_type="application/json",
            headers={"X-Telegram-Bot-Api-Secret-Token": "s3cret"},
        )
    assert res.status_code == 200
    assert res.json()["handled"] == "error"


def test_doctor_reports_every_layer_and_a_verdict(settings: Any) -> None:
    """`bale_doctor` هفت لایه را می‌سنجد و در پایان یک حکمِ صریح می‌دهد."""
    import json as jsonlib
    from io import StringIO

    from django.core.management import call_command

    settings.BALE_BOT_TOKEN = "test-token"
    settings.BALE_WEBHOOK_SECRET = "s3cret"
    settings.BALE_WEBHOOK_URL = "https://api.kaveh185.ir/api/v1/notifications/bale/webhook/"

    def fake_api(method: str, payload: object = None, **_: object) -> dict:
        if method == "getWebhookInfo":
            return {
                "ok": True,
                "result": {"url": settings.BALE_WEBHOOK_URL, "pending_update_count": 0},
            }
        return {"ok": True, "result": True}

    def fake_http(url: str, **_: object) -> tuple[int, str]:
        if "webhook" in url:
            return 200, jsonlib.dumps(
                {"ok": True, "service": "kaveh185-bale-webhook", "handled": "start"}
            )
        return 200, "{}"

    out = StringIO()
    with (
        patch("apps.notifications.bale._api", side_effect=fake_api),
        patch(
            "apps.notifications.bale.get_me",
            return_value={"ok": True, "username": "kaveh185_bot", "name": "کاوه"},
        ),
        patch(
            "apps.notifications.probe.http_call",
            side_effect=fake_http,
        ),
    ):
        call_command("bale_doctor", stdout=out)
    text = out.getvalue()
    for layer in ("۱)", "۲)", "۳)", "۴)", "۵)", "۶)", "۷)"):
        assert layer in text
    assert "حکم:" in text


def test_doctor_translates_bale_delivery_errors() -> None:
    """از متنِ خطای بله، کارِ درست استخراج می‌شود (نه پیامِ مبهم)."""
    from apps.notifications.management.commands.bale_doctor import Command

    assert "کلید" in Command._error_hint("Wrong response from the webhook: 403 Forbidden")
    assert "نمی‌رسد" in Command._error_hint("Wrong response from the webhook: 404 Not Found")
    assert "لاگ" in Command._error_hint(
        "Wrong response from the webhook: 500 Internal Server Error"
    )


def test_doctor_fix_reregisters_and_reports_without_leaking_secret(settings: Any) -> None:
    """`bale_doctor --fix --report` بازثبت می‌کند و گزارشِ بی‌راز می‌دهد."""
    import json as jsonlib
    from io import StringIO

    from django.core.management import call_command

    settings.BALE_BOT_TOKEN = "test-token"
    settings.BALE_WEBHOOK_SECRET = "s3cret"
    settings.BALE_WEBHOOK_URL = "https://api.kaveh185.ir/api/v1/notifications/bale/webhook/"
    methods: list[str] = []

    def fake_api(method: str, payload: object = None, **_: object) -> dict:
        methods.append(method)
        if method == "getWebhookInfo":
            return {
                "ok": True,
                "result": {"url": settings.BALE_WEBHOOK_URL, "pending_update_count": 0},
            }
        return {"ok": True, "result": True}

    def fake_http(url: str, **_: object) -> tuple[int, str]:
        return 200, jsonlib.dumps(
            {"ok": True, "service": "kaveh185-bale-webhook", "handled": "start"}
        )

    out = StringIO()
    with (
        patch("apps.notifications.bale._api", side_effect=fake_api),
        patch(
            "apps.notifications.bale.get_me",
            return_value={"ok": True, "username": "kaveh185_bot", "name": "کاوه"},
        ),
        patch("apps.notifications.probe.http_call", side_effect=fake_http),
    ):
        call_command("bale_doctor", "--fix", "--report", stdout=out)
    text = out.getvalue()
    assert "setWebhook" in methods
    assert "secret_fingerprint" in text
    assert "s3cret" not in text  # راز هرگز چاپ نمی‌شود
    assert "حکم:" in text


def _doctor(**settings_overrides: Any):
    """یک نمونهٔ Command با استایلِ واقعی، برای صدا زدنِ لایه‌ها یکی‌یکی."""
    from io import StringIO

    from apps.notifications.management.commands.bale_doctor import Command

    return Command(stdout=StringIO(), stderr=StringIO())


@override_settings(BALE_WEBHOOK_SECRET="", BALE_WEBHOOK_URL="http://insecure/x/")
def test_doctor_secret_and_url_layers(settings: Any) -> None:
    """کلیدِ خالی و نشانیِ غیرِhttps هر دو باید در حکم بیایند."""
    command = _doctor()
    verdicts: list[str] = []
    assert command._secret(verdicts) is True
    command._url_report("http://insecure/x/", verdicts)
    text = command.stdout.getvalue()  # type: ignore[attr-defined]
    assert "کلید تنظیم نشده" in text
    assert "https" in text
    assert len(verdicts) == 2


@override_settings(BALE_WEBHOOK_SECRET="  spaced  ")
def test_doctor_detects_whitespace_in_secret(settings: Any) -> None:
    """فاصله/CR در کلید ⇒ ۴۰۳ِ بی‌توضیح؛ دستور باید صریح بگوید."""
    command = _doctor()
    verdicts: list[str] = []
    command._secret(verdicts)
    assert any("پاک‌سازی" in v for v in verdicts)


def test_doctor_token_layer_reports_bad_token(settings: Any) -> None:
    """توکنِ نامعتبر ⇒ لایهٔ ۱ قرمز، نه استثنای خام."""
    settings.BALE_BOT_TOKEN = ""
    command = _doctor()
    assert command._token() is False

    settings.BALE_BOT_TOKEN = "x"
    with patch("apps.notifications.bale.get_me", side_effect=BaleErrorLike("401")):
        assert command._token() is False


def BaleErrorLike(message: str):
    from apps.notifications.bale import BaleError

    return BaleError(message)


def test_doctor_reachable_and_loopback_variants(settings: Any) -> None:
    """هر پاسخِ ناخواسته باید توضیحِ خودش را داشته باشد (۴۰۳/۴۰۴/بدونِ‌پاسخ)."""
    settings.BALE_WEBHOOK_SECRET = "s3cret"
    url = "https://api.kaveh185.ir/x/"
    verdicts: list[str] = []

    command = _doctor()
    with patch(
        "apps.notifications.probe.http_call",
        return_value=(404, "<html>not found</html>"),
    ):
        assert command._reachable(url, verdicts) is False
        assert command._loopback(url, verdicts) is False
    with patch("apps.notifications.probe.http_call", return_value=(403, "{}")):
        assert command._loopback(url, verdicts) is False
    with patch("apps.notifications.probe.http_call", return_value=(0, "URLError")):
        assert command._loopback(url, verdicts) is False
        assert command._reachable(url, verdicts) is False
    assert len(verdicts) >= 3


def test_doctor_delivery_layer_variants() -> None:
    """لایهٔ ۷: نبودِ وب‌هوک، صفِ پر، و وضعیتِ سالم سه پیامِ متفاوت دارند."""
    command = _doctor()
    verdicts: list[str] = []
    command._delivery({}, verdicts)
    command._delivery({"url": "u", "pending_update_count": 3}, verdicts)
    command._delivery({"url": "u", "pending_update_count": 0}, verdicts)
    text = command.stdout.getvalue()  # type: ignore[attr-defined]
    assert "ثبت نشود" in text
    assert "سالم نیست" in text
    assert "هیچ تحویلی در دفتر ثبت نیست" in text  # صفِ خالی به‌تنهایی شاهد نیست


def test_doctor_registration_handles_api_errors(settings: Any) -> None:
    """اگر getWebhookInfo خودش خطا بدهد، باید گزارش شود نه استثنا."""
    settings.BALE_WEBHOOK_SECRET = "s3cret"
    command = _doctor()
    verdicts: list[str] = []
    with patch("apps.notifications.bale._api", side_effect=BaleErrorLike("boom")):
        assert command._registration("https://a/", verdicts) == {}
    with patch("apps.notifications.bale._api", return_value={"ok": True, "result": "weird"}):
        assert command._registration("https://a/", verdicts) == {}
    with patch("apps.notifications.bale._api", return_value={"ok": True, "result": {"url": ""}}):
        command._registration("https://a/", verdicts)
    assert any("ثبت نیست" in v for v in verdicts)


def test_doctor_reregister_failure_is_reported(settings: Any) -> None:
    settings.BALE_WEBHOOK_SECRET = "s3cret"
    command = _doctor()
    with patch("apps.notifications.bale._api", side_effect=BaleErrorLike("nope")):
        command._reregister("https://a/")
    assert "ناموفق" in command.stdout.getvalue()  # type: ignore[attr-defined]


@override_settings(BALE_WEBHOOK_SECRET="s3cret", BALE_WEBHOOK_URL="https://api.x/y/")
def test_doctor_verdict_branches() -> None:
    """سه حکمِ ممکن: آماده / نیمه‌باز / آماده‌نبودن."""
    command = _doctor()
    command._verdict([], token_ok=True, secret_ok=True, get_ok=True, post_ok=True)
    command._verdict([], token_ok=True, secret_ok=True, get_ok=True, post_ok=False)
    command._verdict(["x"], token_ok=False, secret_ok=True, get_ok=False, post_ok=False)
    text = command.stdout.getvalue()  # type: ignore[attr-defined]
    assert "آماده است" in text
    assert "زنجیره کامل نیست" in text
    assert "آماده نیست" in text
    assert "  → x" in text


def test_http_call_returns_status_codes(monkeypatch: Any) -> None:
    """`probe.http_call` کدِ وضعیت را حتی روی ۴xx برمی‌گرداند و روی خطای شبکه صفر."""
    import io as iomod
    import urllib.error

    from apps.notifications import probe

    class Resp(iomod.BytesIO):
        status = 200

    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: Resp(b'{"ok": true}'))
    assert probe.http_call("https://a/") == (200, '{"ok": true}')

    def boom(*a: Any, **k: Any) -> Any:
        raise urllib.error.HTTPError("u", 403, "no", {}, None)  # type: ignore[arg-type]

    monkeypatch.setattr("urllib.request.urlopen", boom)
    assert probe.http_call("https://a/")[0] == 403

    def netfail(*a: Any, **k: Any) -> Any:
        raise OSError("down")

    monkeypatch.setattr("urllib.request.urlopen", netfail)
    status, name = probe.http_call("https://a/")
    assert status == 0 and name == "OSError"


def test_doctor_watch_prints_state_changes(settings: Any, monkeypatch: Any) -> None:
    """پایشِ زنده تغییرِ صف/خطا را چاپ می‌کند و در پایان می‌گوید تمام شد."""
    settings.BALE_BOT_TOKEN = "t"
    command = _doctor()
    sequence = iter(
        [
            {"ok": True, "result": {"pending_update_count": 2}},
            {"ok": True, "result": {"pending_update_count": 0, "last_error_message": "boom"}},
        ]
    )

    def fake_api(method: str, payload: object = None, **_: object) -> dict:
        return next(sequence, {"ok": True, "result": {"pending_update_count": 0}})

    ticks = iter([0.0, 1.0, 2.0, 3.0, 99.0])
    monkeypatch.setattr("time.monotonic", lambda: next(ticks))
    monkeypatch.setattr("time.sleep", lambda *_: None)
    with patch("apps.notifications.bale._api", side_effect=fake_api):
        command._watch(30)
    text = command.stdout.getvalue()  # type: ignore[attr-defined]
    assert "صف=" in text and "پایانِ پایش" in text


def test_probe_health_distinguishes_real_app_from_any_200() -> None:
    """۲۰۰ِ هر صفحه‌ای کافی نیست؛ فقط پاسخِ خودِ سرویس سالم است."""
    from apps.notifications import probe

    with patch.object(probe, "http_call", return_value=(200, "<html>splash</html>")):
        ok, message = probe.health("https://a/")
    assert ok is False and "این اپلیکیشن نبود" in message

    with patch.object(probe, "http_call", return_value=(0, "URLError")):
        ok, message = probe.health("https://a/")
    assert ok is False and "پاسخ نیامد" in message


def test_probe_loopback_reports_network_failure() -> None:
    from apps.notifications import probe

    with patch.object(probe, "http_call", return_value=(0, "URLError")):
        ok, message = probe.loopback("https://a/", "s")
    assert ok is False and "برقرار نشد" in message


def test_webhook_command_probe_and_delete_paths(settings: Any) -> None:
    """`--probe` و `--delete` و `--new-secret` و نبودِ توکن — همه با پیامِ روشن."""
    from io import StringIO

    from django.core.management import call_command
    from django.core.management.base import CommandError

    settings.BALE_BOT_TOKEN = "test-token"
    settings.BALE_WEBHOOK_SECRET = ""
    settings.BALE_WEBHOOK_URL = "https://api.kaveh185.ir/x/"

    out = StringIO()
    with patch("apps.notifications.probe.loopback", return_value=(True, "پاسخِ اپلیکیشن: 200")):
        call_command("bale_webhook", "--probe", stdout=out)
    assert "آزمونِ حلقه‌ای" in out.getvalue()

    out = StringIO()
    with patch("apps.notifications.bale._api", return_value={"ok": True, "result": True}):
        call_command("bale_webhook", "--delete", stdout=out)
    assert "حذف" in out.getvalue() or "برداشته" in out.getvalue()

    out = StringIO()
    call_command("bale_webhook", "--new-secret", stdout=out)
    assert "BALE_WEBHOOK_SECRET=" in out.getvalue()

    settings.BALE_BOT_TOKEN = ""
    with pytest.raises(CommandError):
        call_command("bale_webhook", stdout=StringIO())


def test_webhook_command_reports_rejected_registration(settings: Any) -> None:
    """اگر بله ثبت را نپذیرد یا شبکه بلرزد، CommandError با متنِ روشن."""
    from io import StringIO

    from django.core.management import call_command
    from django.core.management.base import CommandError

    from apps.notifications.bale import BaleError

    settings.BALE_BOT_TOKEN = "test-token"
    settings.BALE_WEBHOOK_SECRET = "s3cret"
    settings.BALE_WEBHOOK_URL = "https://api.kaveh185.ir/x/"

    with (
        patch("apps.notifications.bale._api", return_value={"ok": False, "description": "nope"}),
        pytest.raises(CommandError),
    ):
        call_command("bale_webhook", stdout=StringIO())

    with (
        patch("apps.notifications.bale._api", side_effect=BaleError("down")),
        pytest.raises(CommandError),
    ):
        call_command("bale_webhook", stdout=StringIO())


def test_webhook_command_warns_and_suggests_cron_when_unreachable(settings: Any) -> None:
    """اگر نشانی از بیرون پاسخ نداد، صریح می‌گوید به کران برگردد."""
    from io import StringIO

    from django.core.management import call_command

    settings.BALE_BOT_TOKEN = "test-token"
    settings.BALE_WEBHOOK_SECRET = "s3cret"
    settings.BALE_WEBHOOK_URL = "https://api.kaveh185.ir/x/"
    out = StringIO()
    with (
        patch("apps.notifications.bale._api", return_value={"ok": True, "result": {}}),
        patch("apps.notifications.probe.health", return_value=(False, "۴۰۴")),
    ):
        call_command("bale_webhook", stdout=out)
    text = out.getvalue()
    assert "bale_webhook --delete" in text
    assert "--skip-self-test" in text


def test_webhook_command_show_and_print_url(settings: Any) -> None:
    """`--print-url` فقط نشانی می‌دهد و `--show` وضعیت را."""
    from io import StringIO

    from django.core.management import call_command

    settings.BALE_BOT_TOKEN = "t"
    settings.BALE_WEBHOOK_SECRET = "s"
    settings.BALE_WEBHOOK_URL = "https://api.kaveh185.ir/x/"
    out = StringIO()
    call_command("bale_webhook", "--print-url", stdout=out)
    assert out.getvalue().strip() == "https://api.kaveh185.ir/x/"

    out = StringIO()
    with patch(
        "apps.notifications.bale._api",
        return_value={
            "ok": True,
            "result": {"url": "https://api.kaveh185.ir/x/", "pending_update_count": 1},
        },
    ):
        call_command("bale_webhook", "--show", stdout=out)
    assert "آپدیتِ در انتظار: 1" in out.getvalue()


def test_webhook_url_falls_back_to_allowed_hosts(settings: Any) -> None:
    """بدونِ `BALE_WEBHOOK_URL`، دامنهٔ `api.` ترجیح دارد به اولین دامنه."""
    from apps.notifications.management.commands.bale_webhook import Command

    settings.BALE_WEBHOOK_URL = ""
    settings.ALLOWED_HOSTS = ["www.kaveh185.ir", "api.kaveh185.ir"]
    assert "api.kaveh185.ir" in Command()._resolve_url("")

    settings.ALLOWED_HOSTS = ["www.kaveh185.ir"]
    assert "www.kaveh185.ir" in Command()._resolve_url("")

    settings.ALLOWED_HOSTS = ["localhost"]
    assert Command()._resolve_url("").startswith("http://localhost")

    settings.ALLOWED_HOSTS = []
    from django.core.management.base import CommandError

    with pytest.raises(CommandError):
        Command()._resolve_url("")


def test_bale_inbox_reports_webhook_race(monkeypatch: Any, tmp_path: Any) -> None:
    """سنجشِ امنِ `_active_webhook` وقتی بله خطا می‌دهد."""
    from apps.notifications.bale import BaleError
    from apps.notifications.management.commands.bale_inbox import Command

    with patch(
        "apps.notifications.management.commands.bale_inbox._api", side_effect=BaleError("x")
    ):
        assert Command._active_webhook() == ""
    with patch(
        "apps.notifications.management.commands.bale_inbox._api",
        return_value={"ok": True, "result": "s"},
    ):
        assert Command._active_webhook() == ""


@pytest.mark.django_db
def test_webhook_delivery_is_recorded_with_reply_status(client: Any) -> None:
    """هر تحویل در دفتر ثبت می‌شود تا «آیا بله چیزی فرستاد؟» قطعی جواب بگیرد."""
    from apps.notifications.models import BaleDeliveryLog

    with patch("apps.notifications.views.send_bale_message") as sender:
        sender.return_value.ok = False
        res = client.post(
            "/api/v1/notifications/bale/webhook/",
            data={"message": {"chat": {"id": 777}, "text": "/start"}},
            content_type="application/json",
        )
    assert res.status_code == 200
    row = BaleDeliveryLog.objects.get()
    assert row.chat_id == 777
    assert row.handled == "start"
    assert row.replied is False
    assert row.source == "webhook"


@pytest.mark.django_db
def test_doctor_deliveries_lists_ledger(settings: Any) -> None:
    """`bale_doctor --deliveries` دفترِ تحویل را با وضعیتِ پاسخ نشان می‌دهد."""
    from io import StringIO

    from django.core.management import call_command

    from apps.notifications.models import BaleDeliveryLog

    settings.BALE_BOT_TOKEN = "t"
    settings.BALE_WEBHOOK_SECRET = "s"
    BaleDeliveryLog.objects.create(chat_id=42, handled="linked", replied=True)

    out = StringIO()
    call_command("bale_doctor", "--deliveries", "5", stdout=out)
    text = out.getvalue()
    assert "chat=42" in text and "linked" in text

    BaleDeliveryLog.objects.all().delete()
    out = StringIO()
    call_command("bale_doctor", "--deliveries", "5", stdout=out)
    assert "دفتر خالی است" in out.getvalue()


@pytest.mark.django_db
def test_doctor_delivery_layer_uses_ledger(settings: Any) -> None:
    """لایهٔ ۷ با دفترِ پر، گواهِ موفق/ناموفق می‌دهد."""
    from apps.notifications.models import BaleDeliveryLog

    command = _doctor()
    verdicts: list[str] = []
    BaleDeliveryLog.objects.create(chat_id=9, handled="start", replied=True)
    command._delivery({"url": "u", "pending_update_count": 0}, verdicts)
    text = command.stdout.getvalue()  # type: ignore[attr-defined]
    assert "شاهدِ قطعی" in text

    BaleDeliveryLog.objects.create(chat_id=9, handled="start", replied=False, note="x")
    command = _doctor()
    verdicts = []
    command._delivery({"url": "u", "pending_update_count": 0}, verdicts)
    assert any("ناموفق" in v for v in verdicts)


@pytest.mark.django_db
def test_record_bale_delivery_never_raises(monkeypatch: Any) -> None:
    """حسابرسی نباید تحویل را بشکند؛ خطای دیتابیس فقط لاگ می‌شود."""
    from apps.notifications.services import record_bale_delivery

    with patch(
        "apps.notifications.models.BaleDeliveryLog.objects.create",
        side_effect=RuntimeError("db down"),
    ):
        record_bale_delivery(chat_id=1, handled="start", replied=True)


@pytest.mark.django_db
def test_doctor_nudge_detects_delivery(settings: Any) -> None:
    """`--nudge` بازثبت می‌کند و اگر آپدیتی رسید، همان را شاهد می‌گیرد."""
    from apps.notifications.models import BaleDeliveryLog

    settings.BALE_BOT_TOKEN = "t"
    settings.BALE_WEBHOOK_SECRET = "s"
    settings.BALE_WEBHOOK_URL = "https://api.kaveh185.ir/x/"

    def fake_api(method: str, payload: object = None, **_: object) -> dict:
        if method == "setWebhook":
            # بله پس از بازثبت، اولین آپدیتِ معلق را تحویل می‌دهد.
            BaleDeliveryLog.objects.create(chat_id=3, handled="start", replied=True)
        return {"ok": True, "result": True}

    command = _doctor()
    ticks = iter([0.0, 1.0, 200.0])
    with (
        patch("apps.notifications.bale._api", side_effect=fake_api),
        patch("time.monotonic", lambda: next(ticks)),
        patch("time.sleep", lambda *_: None),
    ):
        command._nudge("https://api.kaveh185.ir/x/")
    assert "بله تحویل داد" in command.stdout.getvalue()  # type: ignore[attr-defined]


@pytest.mark.django_db
def test_doctor_nudge_reports_timeout(settings: Any) -> None:
    """اگر چیزی نرسید، می‌گوید پیامِ تازه بفرستید (نه اینکه همه‌چیز را سالم بداند)."""
    settings.BALE_BOT_TOKEN = "t"
    settings.BALE_WEBHOOK_SECRET = "s"
    command = _doctor()
    ticks = iter([0.0, 1.0, 200.0])
    with (
        patch("apps.notifications.bale._api", return_value={"ok": True, "result": True}),
        patch("time.monotonic", lambda: next(ticks)),
        patch("time.sleep", lambda *_: None),
    ):
        command._nudge("https://api.kaveh185.ir/x/")
    assert "هیچ آپدیتی نفرستاد" in command.stdout.getvalue()  # type: ignore[attr-defined]


def _worker_module(tmp_path: Any, monkeypatch: Any):
    from apps.notifications.management.commands import bale_worker as module

    monkeypatch.setattr(module, "OFFSET_FILE", tmp_path / "offset.json")
    monkeypatch.setattr(module, "HEARTBEAT_FILE", tmp_path / "hb.json")
    monkeypatch.setattr(module, "LOCK_FILE", tmp_path / "lock")
    return module


@pytest.mark.django_db
def test_worker_once_consumes_updates_and_records_delivery(
    settings: Any, tmp_path: Any, monkeypatch: Any
) -> None:
    """یک دور: آپدیت خوانده، پاسخ ارسال، offset جلو، تحویل ثبت."""
    from io import StringIO

    from django.core.management import call_command

    from apps.notifications.models import BaleDeliveryLog

    module = _worker_module(tmp_path, monkeypatch)
    settings.BALE_BOT_TOKEN = "t"

    def fake_api(method: str, payload: object = None, **_: object) -> dict:
        if method == "getUpdates":
            return {
                "ok": True,
                "result": [{"update_id": 41, "message": {"chat": {"id": 31337}, "text": "/start"}}],
            }
        return {"ok": True, "result": True}

    out = StringIO()
    with (
        patch("apps.notifications.management.commands.bale_worker._api", side_effect=fake_api),
        patch(
            "apps.notifications.bale.send_bale_message",
            return_value=type("R", (), {"ok": True})(),
        ),
    ):
        call_command("bale_worker", "--once", "--verbose", "--force", stdout=out)
    assert "update=41" in out.getvalue()
    assert module._read_offset() == 42
    row = BaleDeliveryLog.objects.get()
    assert row.source == "polling" and row.replied is True


@pytest.mark.django_db
def test_worker_survives_processing_crash(settings: Any, tmp_path: Any, monkeypatch: Any) -> None:
    """اگر پردازش بترکد، offset جلو می‌رود و حلقه قفل نمی‌شود."""
    from io import StringIO

    from django.core.management import call_command

    from apps.notifications.models import BaleDeliveryLog

    module = _worker_module(tmp_path, monkeypatch)
    settings.BALE_BOT_TOKEN = "t"

    def fake_api(method: str, payload: object = None, **_: object) -> dict:
        return {
            "ok": True,
            "result": [{"update_id": 7, "message": {"chat": {"id": 1}, "text": "x"}}],
        }

    with (
        patch("apps.notifications.management.commands.bale_worker._api", side_effect=fake_api),
        patch(
            "apps.notifications.management.commands.bale_worker.process_bale_message",
            side_effect=RuntimeError("boom"),
        ),
    ):
        call_command("bale_worker", "--once", "--force", stdout=StringIO())
    assert module._read_offset() == 8
    assert BaleDeliveryLog.objects.get().handled == "error"


def test_worker_status_reports_alive_and_dead(
    settings: Any, tmp_path: Any, monkeypatch: Any
) -> None:
    """`--status` سنِ قلب را ترجمه می‌کند و هشدارِ وب‌هوکِ ثبت‌شده می‌دهد."""
    from io import StringIO

    from django.core.management import call_command

    module = _worker_module(tmp_path, monkeypatch)
    settings.BALE_BOT_TOKEN = "t"

    def fake_api(method: str, payload: object = None, **_: object) -> dict:
        return {"ok": True, "result": {"url": "https://api.kaveh185.ir/x"}}

    out = StringIO()
    with patch("apps.notifications.management.commands.bale_worker._api", side_effect=fake_api):
        call_command("bale_worker", "--status", stdout=out)
    text = out.getvalue()
    assert "هرگز اجرا نشده" in text
    assert "وب‌هوک هنوز ثبت است" in text

    module._heartbeat(0)
    out = StringIO()
    with patch("apps.notifications.management.commands.bale_worker._api", side_effect=fake_api):
        call_command("bale_worker", "--status", stdout=out)
    assert "زنده است" in out.getvalue()


def test_worker_refuses_second_instance(settings: Any, tmp_path: Any, monkeypatch: Any) -> None:
    """دو نمونهٔ هم‌زمان = پاسخِ تکراری؛ نمونهٔ دوم باید بلافاصله خارج شود."""
    from io import StringIO

    from django.core.management import call_command

    module = _worker_module(tmp_path, monkeypatch)
    settings.BALE_BOT_TOKEN = "t"
    module._heartbeat(0)  # قلبِ تازه ⇒ سرویسِ اصلی زنده است
    out = StringIO()
    call_command("bale_worker", stdout=out)
    assert "یک نمونهٔ دیگر" in out.getvalue()

    module.HEARTBEAT_FILE.unlink()
    lock = module._Lock(module.LOCK_FILE)
    assert lock.acquire() is True
    out = StringIO()
    call_command("bale_worker", "--once", stdout=out)
    assert "قفل را در دست دارد" in out.getvalue()
    lock.release()


def test_worker_retries_on_api_error_then_exits(
    settings: Any, tmp_path: Any, monkeypatch: Any
) -> None:
    """خطای بله ⇒ بازگشتِ نمایی، نه خروج؛ با `--max-seconds` بیرون می‌آید."""
    from io import StringIO

    from django.core.management import call_command

    from apps.notifications.bale import BaleError

    _worker_module(tmp_path, monkeypatch)
    settings.BALE_BOT_TOKEN = "t"
    sleeps: list[float] = []
    monkeypatch.setattr("time.sleep", lambda value: sleeps.append(value))
    import itertools

    ticks = itertools.count(0, 1)

    def clock() -> float:
        return float(next(ticks, 1000))

    monkeypatch.setattr("time.monotonic", clock)
    out = StringIO()
    with patch(
        "apps.notifications.management.commands.bale_worker._api", side_effect=BaleError("down")
    ):
        call_command("bale_worker", "--max-seconds", "3", "--force", stdout=out)
    assert "خطای تماس با بله" in out.getvalue()
    assert "به سقفِ زمان رسیدم" in out.getvalue()  # خروجِ تمیز، نه حلقهٔ بی‌پایان
    assert sleeps == [1.0]  # بازگشتِ نمایی پیش از رسیدن به سقفِ زمانی

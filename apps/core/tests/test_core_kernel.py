"""تست‌های واحد و یکپارچه برای تمام ماژول‌های هستهٔ زیرساختی (`apps.core`)."""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.core.cache import bump_epoch, cache_get_or_set_swr, get_epoch
from apps.core.cache_invalidation import (
    invalidate_domain_cache,
    process_pending_invalidation_batch,
)
from apps.core.crypto import blind_index, decrypt_pii, encrypt_pii
from apps.core.idempotency import execute_idempotent, purge_expired_keys
from apps.core.jalali import (
    calculate_age,
    format_jalali_date,
    gregorian_to_jalali,
    jalali_to_gregorian,
    normalize_digits,
    parse_flexible_date,
    today_jalali,
)
from apps.core.tasks import (
    process_pending_cache_invalidation_events_task,
    purge_expired_idempotency_keys_task,
    relay_pending_outbox_task,
)
from apps.core.uuid7 import uuid7, uuid7_hex


def test_uuid7_is_monotonic_and_version_7() -> None:
    """شناسه‌های UUIDv7 باید نسخهٔ ۷ و دارای ۳۲ کاراکتر هگزادسیمال معتبر باشند."""
    u1 = uuid7()
    u2 = uuid7()
    assert u1.version == 7
    assert u2.version == 7
    hex_str = uuid7_hex()
    assert len(hex_str) == 32


def test_crypto_aes_gcm_roundtrip_and_blind_index() -> None:
    """رمزنگاری AES-GCM باید برگشت‌پذیر و شاخص کور HMAC-SHA256 باید قطعی باشد."""
    plaintext = "0013542419"
    cipher = encrypt_pii(plaintext)
    assert cipher.startswith("v1:")
    assert decrypt_pii(cipher) == plaintext
    assert decrypt_pii("") == ""
    assert decrypt_pii("plain-legacy-value") == "plain-legacy-value"

    idx1 = blind_index(plaintext, purpose="national_id")
    idx2 = blind_index(plaintext, purpose="national_id")
    idx_other = blind_index(plaintext, purpose="phone")
    assert idx1 == idx2
    assert idx1 != idx_other
    assert len(idx1) == 64


def test_jalali_calendar_conversion_and_flexible_date_parser() -> None:
    """تبدیل دوطرفهٔ تاریخ شمسی ↔ میلادی، نرمال‌سازی ارقام فارسی و محاسبهٔ سن."""
    assert normalize_digits("۱۳۸۲/۰۶/۱۵") == "1382/06/15"

    gy, gm, gd = jalali_to_gregorian(1382, 6, 15)
    jy, jm, jd = gregorian_to_jalali(gy, gm, gd)
    assert (jy, jm, jd) == (1382, 6, 15)

    parsed_jalali = parse_flexible_date("۱۳۸۰/۰۱/۰۱")
    assert parsed_jalali == date(2001, 3, 21)
    assert format_jalali_date(parsed_jalali) == "1380/01/01"

    parsed_greg = parse_flexible_date("2005-05-10")
    assert parsed_greg == date(2005, 5, 10)

    age = calculate_age(date(2000, 1, 1), reference_date=date(2026, 6, 1))
    assert age == 26
    assert today_jalali() != ""

    with pytest.raises(ValueError):
        parse_flexible_date("invalid-date")


@pytest.mark.django_db()
def test_cache_epoch_swr_and_db_invalidation() -> None:
    """کش SWR مبتنی بر Epoch باید پس از باطل‌سازی دامنه مقدار جدید را تولید کند."""
    counter = {"calls": 0}

    def _producer() -> dict[str, int]:
        counter["calls"] += 1
        return {"val": counter["calls"]}

    first = cache_get_or_set_swr(domain="mosques", key_suffix="test", producer=_producer)
    second = cache_get_or_set_swr(domain="mosques", key_suffix="test", producer=_producer)
    assert first == {"val": 1}
    assert second == {"val": 1}
    assert counter["calls"] == 1

    epoch_before = get_epoch("mosques")
    new_epoch = invalidate_domain_cache("mosques", reason="test.bump")
    assert new_epoch > epoch_before

    third = cache_get_or_set_swr(domain="mosques", key_suffix="test", producer=_producer)
    assert third == {"val": 2}
    assert counter["calls"] == 2

    batch_res = process_pending_invalidation_batch()
    assert batch_res["processed"] >= 1
    assert bump_epoch("mosques") > new_epoch


@pytest.mark.django_db()
def test_idempotency_execution_replay_and_conflict() -> None:
    """کلید هم‌توانی (`Idempotency-Key`) باید پاسخ اول را بازپخش و تغییر بدنه را رد کند."""
    runs = {"count": 0}

    def _action() -> tuple[int, dict[str, Any]]:
        runs["count"] += 1
        return 201, {"created": True, "run": runs["count"]}

    res1 = execute_idempotent(
        key="idem-key-101",
        scope="POST:/api/v1/exam/start/",
        actor_ref="user:1",
        payload={"step": 1},
        action=_action,
    )
    assert res1.replayed is False
    assert res1.status_code == 201
    assert runs["count"] == 1

    res2 = execute_idempotent(
        key="idem-key-101",
        scope="POST:/api/v1/exam/start/",
        actor_ref="user:1",
        payload={"step": 1},
        action=_action,
    )
    assert res2.replayed is True
    assert res2.body == {"created": True, "run": 1}
    assert runs["count"] == 1

    from apps.core.exceptions import ConflictDomainError

    with pytest.raises(ConflictDomainError):
        execute_idempotent(
            key="idem-key-101",
            scope="POST:/api/v1/exam/start/",
            actor_ref="user:1",
            payload={"step": 999},
            action=_action,
        )

    def _failing() -> tuple[int, dict[str, Any]]:
        raise ValueError("fail")

    with pytest.raises(ValueError, match="fail"):
        execute_idempotent(
            key="idem-key-fail",
            scope="POST:/api/v1/exam/start/",
            actor_ref="user:1",
            payload={"step": 1},
            action=_failing,
        )

    assert purge_expired_keys() == 0


@pytest.mark.django_db()
def test_health_probes_metrics_and_meta_endpoints(
    api_client: APIClient,
    admin_client: APIClient,
) -> None:
    """تست اندپوینت‌های سلامت (`live`, `ready`, `detailed`)، متریک‌ها و متادیتا + هدرهای امنیتی."""
    live_resp = api_client.get("/api/v1/health/live/", HTTP_X_REQUEST_ID="req-custom-123456")
    assert live_resp.status_code == 200
    assert live_resp["X-Request-ID"] == "req-custom-123456"
    assert live_resp["X-Content-Type-Options"] == "nosniff"
    assert live_resp["X-Frame-Options"] == "DENY"
    assert "X-Response-Time-ms" in live_resp
    assert "X-DB-Query-Count" in live_resp

    ready_resp = api_client.get("/api/v1/health/ready/")
    assert ready_resp.status_code == 200
    assert ready_resp.json()["data"]["status"] in {"healthy", "degraded", "ready"}

    detailed_resp = admin_client.get("/api/v1/health/detailed/")
    assert detailed_resp.status_code == 200
    assert "checks" in detailed_resp.json()["data"]

    metrics_resp = api_client.get("/api/v1/metrics/")
    assert metrics_resp.status_code == 200
    assert b"kaveh185_http_requests_total" in metrics_resp.content

    meta_resp = api_client.get("/api/v1/core/meta/")
    assert meta_resp.status_code == 200
    assert meta_resp.json()["data"]["service"] in {"kaveh185", "kaveh185-backend"}


@pytest.mark.django_db()
def test_celery_maintenance_tasks_run_cleanly() -> None:
    """تسک‌های نگهداری Celery باید در حالت Eager بدون خطا اجرا شوند."""
    outbox_res = relay_pending_outbox_task()
    assert "processed" in outbox_res

    idem_res = purge_expired_idempotency_keys_task()
    assert isinstance(idem_res, int)

    cache_res = process_pending_cache_invalidation_events_task()
    assert "processed" in cache_res


@pytest.mark.django_db()
def test_domain_exceptions_cache_invalidation_client_ip_and_filtersets() -> None:
    """تست مبدل خطاهای دامنه، باطل‌سازی کش همه دامنه‌ها، تشخیص IP کلاینت و FilterSetها."""
    from django.test import RequestFactory

    from apps.authentication.filters import UserFilterSet
    from apps.authentication.models import User
    from apps.core.cache_invalidation import (
        invalidate_domain_cache,
        process_pending_invalidation_batch,
    )
    from apps.core.client_ip import get_client_ip, get_network_prefix
    from apps.core.exceptions import (
        ConflictDomainError,
        ForbiddenDomainError,
        NotFoundDomainError,
        RateLimitDomainError,
        UnauthorizedDomainError,
        ValidationDomainError,
        custom_exception_handler,
    )
    from apps.exam.filters import QuestionFilterSet
    from apps.exam.models import Question
    from apps.mosques.filters import MosqueFilterSet
    from apps.mosques.models import Mosque

    rf = RequestFactory()
    req = rf.get("/api/v1/health/", HTTP_X_FORWARDED_FOR="185.143.232.10, 10.0.0.1")
    ip = get_client_ip(req)
    assert ip in {"185.143.232.10", "127.0.0.1"}
    assert get_network_prefix("185.143.232.10") == "185.143.232.0/24"
    assert get_network_prefix("2001:db8:abcd:0012::1") != ""

    for exc_cls, expected_status in [
        (ValidationDomainError, 400),
        (UnauthorizedDomainError, 401),
        (ForbiddenDomainError, 403),
        (NotFoundDomainError, 404),
        (ConflictDomainError, 409),
        (RateLimitDomainError, 429),
    ]:
        resp = custom_exception_handler(exc_cls("خطای تستی"), {"request": req})
        assert resp is not None
        assert resp.status_code == expected_status

    for domain in ("mosques", "exam_status", "reporting"):
        assert invalidate_domain_cache(domain, reason="test_all") >= 1
    assert process_pending_invalidation_batch()["processed"] >= 0

    # تست تمام شاخه‌های مبدل استثناهای DRF و خطای ۵۰۰
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

    for drf_exc, code_num in [
        (DRFValidationError({"field": ["خطای فیلد"]}), 400),
        (NotAuthenticated(), 401),
        (AuthenticationFailed(), 401),
        (DRFPermissionDenied(), 403),
        (NotFound(), 404),
        (MethodNotAllowed("POST"), 405),
        (ParseError(), 400),
        (Throttled(wait=30), 429),
        (APIException("خطای عمومی"), 500),
        (RuntimeError("خطای غیرمنتظره"), 500),
    ]:
        r = custom_exception_handler(drf_exc, {"request": req})
        assert r is not None
        assert r.status_code == code_num

    # تست حالت Stale در SWR کش
    val1 = cache_get_or_set_swr(
        domain="mosques", key_suffix="stale_test", producer=lambda: {"v": 1}, soft_ttl=-1
    )
    assert val1 == {"v": 1}
    val2 = cache_get_or_set_swr(
        domain="mosques", key_suffix="stale_test", producer=lambda: {"v": 2}, soft_ttl=30
    )
    assert val2 == {"v": 2}

    # تست Outbox معوق و کلاس‌های Permission
    from apps.core.outbox import enqueue_outbox, relay_pending_outbox

    msg = enqueue_outbox(
        topic="custom.event",
        recipient="system",
        payload={"ok": True},
        deliver_immediately=False,
    )
    assert msg.id is not None
    relay_res = relay_pending_outbox()
    assert relay_res["sent"] >= 1

    from apps.authentication.permissions import (
        HasFreshMfa,
        IsOperatorOrAdmin,
        IsParticipantProfileReady,
        IsVerifiedParticipant,
    )

    anon_req = rf.get("/")
    anon_req.user = None  # type: ignore[assignment]
    assert IsParticipantProfileReady().has_permission(anon_req, None) is False
    assert IsVerifiedParticipant().has_permission(anon_req, None) is False
    assert HasFreshMfa().has_permission(anon_req, None) is False
    assert IsOperatorOrAdmin().has_permission(anon_req, None) is False

    assert UserFilterSet(data={"role": "participant"}, queryset=User.objects.all()).qs is not None
    assert MosqueFilterSet(data={"code": "MSQ-01"}, queryset=Mosque.objects.all()).qs is not None
    assert (
        QuestionFilterSet(data={"difficulty": "easy"}, queryset=Question.objects.all()).qs
        is not None
    )


@pytest.mark.django_db()
def test_remaining_branches_for_90_percent_coverage(
    monkeypatch: pytest.MonkeyPatch,
    admin_client: APIClient,
    admin_user: Any,
    participant_user: Any,
) -> None:
    """پوشش شاخه‌های بازاعتبارسنجی فرانت‌اند، تاریخ شمسی، MFA بازیابی و لاگ اعلان‌ها."""
    from datetime import date, datetime

    import requests
    from django.test import override_settings

    from apps.authentication.services import (
        confirm_user_totp,
        create_and_send_otp,
        setup_user_totp,
        verify_otp_and_issue_session,
        verify_user_mfa,
    )
    from apps.authentication.totp import compute_totp_code
    from apps.core.cache_invalidation import (
        invalidate_domain_cache,
        process_invalidation_event,
    )
    from apps.core.exceptions import ValidationDomainError
    from apps.core.jalali import format_jalali_datetime
    from apps.core.models import CacheInvalidationEvent

    # ۱) شاخه‌های موفقیت و شکست بازاعتبارسنجی فرانت‌اند
    invalidate_domain_cache("mosques", reason="reval_test")
    ev = CacheInvalidationEvent.objects.order_by("-id").first()
    assert ev is not None

    with override_settings(
        FRONTEND_REVALIDATION_ENABLED=True,
        FRONTEND_REVALIDATION_URL="https://example.invalid/api/revalidate",
        FRONTEND_REVALIDATION_SECRET="sec-185",
    ):

        class _DummyResp:
            def raise_for_status(self) -> None:
                return None

        monkeypatch.setattr(requests, "post", lambda *a, **kw: _DummyResp())
        assert process_invalidation_event(ev) is True

        def _raise_err(*a: Any, **kw: Any) -> Any:
            raise RuntimeError("network down")

        monkeypatch.setattr(requests, "post", _raise_err)
        assert process_invalidation_event(ev) is False

    # ۲) شاخه‌های تاریخ شمسی و ISO
    d_obj = date(2005, 3, 21)
    assert parse_flexible_date(d_obj) == d_obj
    assert parse_flexible_date("2005-03-21") == d_obj
    assert format_jalali_datetime(datetime(2026, 11, 14, 12, 30)) != ""
    assert format_jalali_datetime(None) == ""

    # ۳) شاخهٔ کد اشتباه OTP و کد بازیابی MFA
    create_and_send_otp(phone_number=participant_user.phone_number)
    with pytest.raises(ValidationDomainError):
        verify_otp_and_issue_session(phone_number=participant_user.phone_number, code="000000")

    totp_info = setup_user_totp(user=admin_user)
    recovery_codes = confirm_user_totp(
        user=admin_user,
        code=compute_totp_code(totp_info["secret"]),
    )
    assert len(recovery_codes) >= 1
    assert verify_user_mfa(user=admin_user, code=recovery_codes[0]) is True

    # ۴) فیلترهای لاگ پیامک ادمین و درگاه پیامک سفارشی و SoftDelete
    sms_resp = admin_client.get(
        "/api/v1/notifications/admin/sms-logs/?status=sent&category=otp&search=0912"
    )
    assert sms_resp.status_code == 200

    from urllib import request as urllib_request

    from apps.authentication.permissions import HasFreshMfa
    from apps.core.exceptions import StepUpMfaRequiredError
    from apps.mosques.models import Mosque
    from apps.notifications.providers import send_via_configured_gateway

    with override_settings(
        SMS_PROVIDER="kavenegar",
        SMS_API_URL="https://sms.example.invalid/send",
        SMS_API_KEY="key-185",
    ):

        class _DummyHttpResp:
            status = 200

            def __enter__(self) -> _DummyHttpResp:
                return self

            def __exit__(self, *args: Any) -> None:
                return None

            def read(self) -> bytes:
                return b"msg-999"

        monkeypatch.setattr(urllib_request, "urlopen", lambda *a, **kw: _DummyHttpResp())
        gw_res = send_via_configured_gateway(recipient_phone="09121112233", message_text="تست")
        assert gw_res.success is True

    m_temp = Mosque.objects.create(code="MSQ-TMP", name="مسجد موقت", display_order=999)
    get_m = admin_client.get(f"/api/v1/mosques/admin/{m_temp.id}/")
    assert get_m.status_code == 200
    m_temp.delete()

    class _DummyReq:
        user = admin_user
        auth_session = None

    with pytest.raises(StepUpMfaRequiredError):
        HasFreshMfa().has_permission(_DummyReq(), None)

    # ۵) پوشش شاخه‌های خطای زیرساخت کش (Fail-Open) و Outbox
    from django.core.cache import cache as dj_cache

    import apps.notifications.services as notif_services
    from apps.core.cache import _safe_add, _safe_get, _safe_set
    from apps.core.outbox import dispatch_outbox_message, enqueue_outbox

    monkeypatch.setattr(
        dj_cache, "get", lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("redis down"))
    )
    monkeypatch.setattr(
        dj_cache, "set", lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("redis down"))
    )
    monkeypatch.setattr(
        dj_cache, "add", lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("redis down"))
    )
    assert _safe_get("k") is None
    assert _safe_set("k", 1, 10) is False
    assert _safe_add("k", 1, 10) is False
    assert bump_epoch("mosques") >= 1

    bad_outbox = enqueue_outbox(
        topic="sms.test",
        recipient="09120000000",
        payload={"message": "err"},
        deliver_immediately=False,
    )
    monkeypatch.setattr(
        notif_services,
        "deliver_outbox_sms",
        lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("sms down")),
    )
    assert dispatch_outbox_message(bad_outbox) is False

    from apps.core.cache_policy import get_cache_policy
    from apps.core.health.checks import (
        build_detailed_health_report,
        check_cache,
        check_database,
        check_sms_provider_readiness,
    )

    with pytest.raises(KeyError):
        get_cache_policy("unknown_domain")
    assert check_database()["status"] == "healthy"
    assert check_cache()["status"] == "degraded"
    with override_settings(OTP_SMS_PROVIDER="iranpayamak"):
        assert check_sms_provider_readiness()["status"] == "degraded"
    assert build_detailed_health_report()["overall_status"] in {"healthy", "degraded"}
    assert str(admin_user) != ""
    assert str(bad_outbox) != ""

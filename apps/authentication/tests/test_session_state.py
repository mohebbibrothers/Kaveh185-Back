"""تست‌های `/auth/session/state/` — نشستِ خودترمیم.

══ سناریوی واقعی ══════════════════════════════════════════════════════════
کاربر ثبت‌نام می‌کند، به صفحهٔ خانه می‌رود، برمی‌گردد و فرمِ خالی می‌بیند.
ریشهٔ فنی: رابط نمی‌دانست این دستگاه چه کسی است. سه حالت آزمون می‌شود:

  ۱) توکنِ دسترسی زنده ⇒ `state=session`
  ۲) توکنِ دسترسی منقضی ولی refresh زنده ⇒ `state=revived` + توکنِ تازه
  ۳) refresh هم مرده ⇒ `state=no_session` و «برو ثبت‌نام» (صادقانه)
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from apps.authentication.models import AuthSession, User
from tests.factories import create_test_admin  # noqa: F401  (ثبتِ fixtureهای مشترک)

pytestmark = pytest.mark.django_db

URL = "/api/v1/auth/session/state/"


def _participant(**over: object) -> User:
    """شرکت‌کنندهٔ کامل (با مسجد و تاریخ تولد) تا پروفایل «آماده» باشد."""
    from datetime import date

    from apps.authentication.choices import UserRole
    from apps.mosques.models import Mosque

    mosque, _ = Mosque.objects.get_or_create(
        code="MSQ-99", defaults={"name": "مسجد آزمون", "neighborhood": "کاوه"}
    )
    user = User.objects.create_user(
        phone_number=str(over.get("phone_number", "09121110000")),
        national_id=str(over.get("national_id", "0013542419")),
        first_name="سارا",
        last_name="آزمون",
        birth_date=date(2000, 1, 1),
        mosque=mosque,
        password=None,
    )
    user.role = UserRole.PARTICIPANT
    user.save(update_fields=["role"])
    return user


def _session_tokens(user: User) -> tuple[str, str]:
    """ساختِ نشست روی سرور و توکن‌های واقعی — همان چیزی که رابط در دست دارد."""
    from apps.authentication.services import issue_tokens_and_session

    tokens = issue_tokens_and_session(user=user)
    return tokens["access"], tokens["refresh"]


def _post(payload: dict[str, object]) -> dict[str, object]:
    client = APIClient()
    res = client.post(URL, payload, format="json")
    assert res.status_code in {200, 403}, res.content
    return res.json()


def test_live_access_token_reports_session_and_next_step() -> None:
    """توکنِ زنده ⇒ session + قدمِ بعد /exam."""
    user = _participant()
    access, refresh = _session_tokens(user)
    body = _post({"access": access, "refresh": refresh})
    data = body["data"]
    assert data["state"] == "session"
    assert data["user"]["phone_number"] == "09121110000"
    assert data["next"]["path"] == "/exam"
    assert data["session"] is None  # توکنِ تازه لازم نبود


def test_expired_access_is_revived_with_refresh() -> None:
    """توکنِ دسترسیِ مرده + refreshِ زنده ⇒ revived + توکنِ تازه و قابلِ استفاده."""
    user = _participant(phone_number="09121110001", national_id="0083534415")
    _, refresh = _session_tokens(user)
    # توکنِ دسترسی که همین حالا منقضی شده (در تست نمی‌شود ۶ ساعت صبر کرد).
    dead = AccessToken()
    dead["user_id"] = user.pk
    dead.set_exp(lifetime=timedelta(seconds=-5))
    body = _post({"access": str(dead), "refresh": refresh})
    data = body["data"]
    assert data["state"] == "revived"
    assert data["session"] and data["session"]["access"]
    # توکنِ تازه واقعاً کار می‌کند:
    again = _post({"access": data["session"]["access"]})
    assert again["data"]["state"] == "session"


def test_revoked_server_session_is_not_revived() -> None:
    """نشستِ باطل‌شده روی سرور با refresh هم زنده نمی‌شود (امنیت)."""
    user = _participant(phone_number="09121110002", national_id="0083534415")
    _, refresh = _session_tokens(user)
    AuthSession.objects.filter(user=user).update(is_revoked=True)
    body = _post({"refresh": refresh})
    assert body["data"]["state"] == "no_session"


def test_new_device_can_claim_with_phone_and_national_id() -> None:
    """دستگاهِ تازه + شماره + کد ملی ⇒ نشستِ تازه و /exam."""
    _participant(phone_number="09121110003")
    body = _post({"phone_number": "09121110003", "national_id": "0013542419"})
    data = body["data"]
    assert data["state"] == "session"
    assert data["session"]["access"]
    assert data["next"]["path"] == "/exam"


def test_claim_requires_both_phone_and_national_id() -> None:
    """شمارهٔ تنها (یا کد ملیِ تنها) نشست نمی‌دهد."""
    _participant(phone_number="09121110004")
    assert _post({"phone_number": "09121110004"})["data"]["state"] == "no_session"
    assert _post({"national_id": "0013542419"})["data"]["state"] == "no_session"


def test_claim_with_wrong_national_id_gets_nothing() -> None:
    """شمارهٔ درست با کد ملیِ غلط ⇒ هیچ نشستی (نه خطای لو دهنده)."""
    _participant(phone_number="09121110005")
    body = _post({"phone_number": "09121110005", "national_id": "0083534415"})
    assert body["data"]["state"] == "no_session"


def test_completed_participant_is_pointed_to_receipt() -> None:
    """کاربری که آزمونش تمام شده ⇒ قدمِ بعد کارنامه است، نه آزمون."""
    from datetime import timedelta

    from django.utils import timezone

    from apps.exam.choices import ExamAttemptStatus
    from apps.exam.models import ExamAttempt

    user = _participant(phone_number="09121110006", national_id="0064278875")
    now = timezone.now()
    ExamAttempt.objects.create(
        user=user,
        status=ExamAttemptStatus.COMPLETED,
        tracking_code="K185-TEST-1",
        mosque=user.mosque,
        started_at=now,
        expires_at=now + timedelta(minutes=5),
    )
    access, refresh = _session_tokens(user)
    data = _post({"access": access, "refresh": refresh})["data"]
    assert data["state"] == "completed"
    assert data["next"]["path"].startswith("/receipt?code=K185-TEST-1")


def test_admin_cannot_use_participant_claim_path() -> None:
    """ادمین از مسیرِ شرکت‌کننده نشست نمی‌گیرد (مسیرش رمز است)."""
    from apps.authentication.choices import UserRole

    user = _participant(phone_number="09121110007", national_id="0064278875")
    user.role = UserRole.ADMIN
    user.save(update_fields=["role"])
    data = _post({"phone_number": "09121110007", "national_id": "0064278872"})["data"]
    assert data["state"] == "no_session"


def test_url_is_reversible() -> None:
    """نامِ مسیر پایدار بماند تا فرانت به رشتهٔ دستی وابسته نشود."""
    assert reverse("authentication:session-state") == URL


def test_admin_token_points_to_login_not_register() -> None:
    """دکمهٔ مدیر باید «ورود به پنل» باشد، نه فرمِ ثبت‌نامِ شرکت‌کننده."""
    from apps.authentication.choices import UserRole

    user = _participant(phone_number="09121110008", national_id="0013542419")
    user.role = UserRole.ADMIN
    user.save(update_fields=["role"])
    access, refresh = _session_tokens(user)
    data = _post({"access": access, "refresh": refresh})["data"]
    assert data["next"]["path"] == "/login"
    assert data["next"]["label"] == "ورود به پنل"

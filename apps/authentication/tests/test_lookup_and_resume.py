"""تستِ «ورودِ بازگشتی»: کاربری که ثبت‌نام کرده ولی آزمون را شروع نکرده است.

شکایتِ واقعی: «کاربر ثبت‌نام می‌کند، دکمهٔ ورود را نمی‌زند؛ بار بعد دوباره
فرمِ خالی می‌بیند.» این فایل قراردادِ مسیرِ `/auth/lookup/` را قفل می‌کند تا
این رفتار برنگردد، و مهم‌تر: قفل می‌کند که با روشن‌شدنِ سیاستِ کد، دانستنِ
یک شماره **دیگر** نشست ندهد.
"""

from __future__ import annotations

from datetime import timedelta
from io import StringIO

import pytest
from django.core.management import call_command
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.exam.choices import ExamAttemptStatus
from apps.exam.models import ExamAttempt
from tests.factories import create_test_participant

LOOKUP_URL = "/api/v1/auth/lookup/"


@pytest.mark.django_db
def test_lookup_issues_session_for_known_phone(api_client: APIClient) -> None:
    """شمارهٔ آشنا ⇒ نشستِ تازه + `session_ready` (بدونِ اینکه چیزی دوباره پر شود)."""
    user = create_test_participant(seq=321)

    res = api_client.post(LOOKUP_URL, data={"phone_number": user.phone_number}, format="json")

    assert res.status_code == 200
    body = res.json()["data"]
    assert body["found"] is True
    assert body["state"] == "session_ready"
    assert body["access"]
    assert body["user"]["phone_number"] == user.phone_number
    assert body["exam_eligibility"]["can_enter_exam"] is True


@pytest.mark.django_db
def test_lookup_returns_not_found_without_leaking(api_client: APIClient) -> None:
    """شمارهٔ ناشناس ⇒ `not_found` با ۲۰۰، نه ۴۰۴ یا خطای مبهم."""
    res = api_client.post(LOOKUP_URL, data={"phone_number": "09129999999"}, format="json")
    assert res.status_code == 200
    body = res.json()["data"]
    assert body == {**body, "found": False, "state": "not_found"}
    assert "user" not in body


@pytest.mark.django_db
def test_lookup_never_returns_session_for_invalid_phone(api_client: APIClient) -> None:
    """شمارهٔ بی‌معنی نباید ۵۰۰ بدهد؛ فقط `not_found`."""
    res = api_client.post(LOOKUP_URL, data={"phone_number": "123"}, format="json")
    assert res.status_code == 200
    assert res.json()["data"]["state"] == "not_found"


@pytest.mark.django_db
def test_lookup_points_completed_user_to_receipt(api_client: APIClient) -> None:
    """کاربری که آزمونش را داده، نشستِ تازه نمی‌گیرد؛ به کارنامه هدایت می‌شود."""
    user = create_test_participant(seq=322)
    ExamAttempt.objects.create(
        user=user,
        mosque=user.mosque,
        tracking_code="TRK-DONE-1",
        status=ExamAttemptStatus.COMPLETED,
        expires_at=timezone.now() + timedelta(minutes=5),
        completed_at=timezone.now(),
    )

    res = api_client.post(LOOKUP_URL, data={"phone_number": user.phone_number}, format="json")
    body = res.json()["data"]

    assert body["state"] == "exam_completed"
    assert body["tracking_code"] == "TRK-DONE-1"
    # ⚠️ توکن نده: آزمون تمام شده، نشستِ تازه فقط سطحِ حمله است.
    assert "access" not in body


@pytest.mark.django_db
@override_settings(BALE_OTP_MANDATORY=True)
def test_lookup_closes_when_phone_verification_is_mandatory(api_client: APIClient) -> None:
    """با سیاستِ کد روشن، دانستنِ شماره نباید نشست بدهد (۴۰۳ صریح)."""
    user = create_test_participant(seq=323, is_phone_verified=False)

    res = api_client.post(LOOKUP_URL, data={"phone_number": user.phone_number}, format="json")

    assert res.status_code == 403
    assert res.json()["code"] == "verification_required"


@pytest.mark.django_db
def test_lookup_survives_after_admin_purge_of_exam_data(api_client: APIClient) -> None:
    """بعد از پاک‌سازیِ دادهٔ آزمایشی، همان شماره باید پروندهٔ تازه بگیرد."""
    user = create_test_participant(seq=324)
    assert api_client.post(
        LOOKUP_URL, data={"phone_number": user.phone_number}, format="json"
    ).json()["data"]["found"]

    call_command("reset_test_participants", "--yes", stdout=StringIO())

    res = api_client.post(LOOKUP_URL, data={"phone_number": user.phone_number}, format="json")
    assert res.json()["data"]["state"] == "not_found"

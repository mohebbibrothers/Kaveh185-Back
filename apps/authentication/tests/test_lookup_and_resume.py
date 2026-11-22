"""تستِ «ورودِ بازگشتی»: کاربری که ثبت‌نام کرده ولی آزمون را شروع نکرده است.

شکایتِ واقعی: «کاربر ثبت‌نام می‌کند، دکمهٔ ورود را نمی‌زند؛ بار بعد دوباره
فرمِ خالی می‌بیند.» این فایل قراردادِ مسیرِ `/auth/lookup/` را قفل می‌کند.

══ قراردادِ دورِ ۵۰: دو عامل، نه یکی ═══════════════════════════════════════
تا این دور، **شمارهٔ همراه تنها** برای گرفتنِ نشست کافی بود. یعنی هر کسی که
شمارهٔ یک شرکت‌کننده را می‌دانست می‌توانست کارنامه‌اش را ببیند. حالا کد ملی
هم الزامی است و **هر دو باید به همان پرونده تعلق داشته باشند**. این فایل
چهار چیز را قفل می‌کند:

  ۱) جفتِ درست ⇒ نشست.
  ۲) شمارهٔ تنها ⇒ هیچ (حتی اگر شماره واقعاً وجود داشته باشد).
  ۳) شمارهٔ درست + کد ملیِ غلط ⇒ **همان** پاسخِ «پیدا نشد»، بی‌تفکیک.
  ۴) با سیاستِ کد روشن، حتی جفتِ درست هم نشست نمی‌دهد (۴۰۳).
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

    res = api_client.post(
        LOOKUP_URL,
        data={"phone_number": user.phone_number, "national_id": user.national_id},
        format="json",
    )

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
    res = api_client.post(
        LOOKUP_URL, data={"phone_number": "09129999999", "national_id": "0013542419"}, format="json"
    )
    assert res.status_code == 200
    body = res.json()["data"]
    assert body == {**body, "found": False, "state": "not_found"}
    assert "user" not in body


@pytest.mark.django_db
def test_lookup_never_returns_session_for_invalid_phone(api_client: APIClient) -> None:
    """شمارهٔ بی‌معنی نباید ۵۰۰ بدهد؛ فقط `not_found`."""
    res = api_client.post(
        LOOKUP_URL, data={"phone_number": "123", "national_id": "123"}, format="json"
    )
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

    res = api_client.post(
        LOOKUP_URL,
        data={"phone_number": user.phone_number, "national_id": user.national_id},
        format="json",
    )
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

    res = api_client.post(
        LOOKUP_URL,
        data={"phone_number": user.phone_number, "national_id": user.national_id},
        format="json",
    )

    assert res.status_code == 403
    assert res.json()["code"] == "verification_required"


@pytest.mark.django_db
def test_lookup_survives_after_admin_purge_of_exam_data(api_client: APIClient) -> None:
    """بعد از پاک‌سازیِ دادهٔ آزمایشی، همان شماره باید پروندهٔ تازه بگیرد."""
    user = create_test_participant(seq=324)
    pair = {"phone_number": user.phone_number, "national_id": user.national_id}
    assert api_client.post(LOOKUP_URL, data=pair, format="json").json()["data"]["found"]

    call_command("reset_test_participants", "--yes", stdout=StringIO())

    res = api_client.post(LOOKUP_URL, data=pair, format="json")
    assert res.json()["data"]["state"] == "not_found"


# ═══════════════════════════════════════════════════════════════════════════
#  قواعدِ «دو عامل» — همان چیزی که این دور اضافه شد
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
def test_phone_alone_is_not_enough(api_client: APIClient) -> None:
    """شمارهٔ واقعیِ یک پرونده، بدونِ کد ملی ⇒ هیچ نشستی (۰ توکن)."""
    user = create_test_participant(seq=401)
    res = api_client.post(LOOKUP_URL, data={"phone_number": user.phone_number}, format="json")
    body = res.json()["data"]
    assert body["found"] is False
    assert body["state"] == "not_found"
    assert "access" not in body


@pytest.mark.django_db
def test_wrong_national_id_is_indistinguishable_from_unknown_phone(
    api_client: APIClient,
) -> None:
    """شمارهٔ درست + کد ملیِ غلط و شمارهٔ ناموجود باید **عیناً** یک پاسخ بدهند.

    اگر تفاوت داشتند، مهاجم می‌فهمید کدام شماره در سامانه هست و فقط باید
    کد ملی را حدس بزند — یعنی همان باگِ قبلی با یک گام اضافه.
    """
    user = create_test_participant(seq=402)
    wrong_pair = api_client.post(
        LOOKUP_URL,
        data={"phone_number": user.phone_number, "national_id": "0013542419"},
        format="json",
    )
    unknown = api_client.post(
        LOOKUP_URL,
        data={"phone_number": "09129999999", "national_id": "0013542419"},
        format="json",
    )
    assert wrong_pair.status_code == unknown.status_code == 200
    assert wrong_pair.json()["data"] == unknown.json()["data"]
    assert wrong_pair.json()["message"] == unknown.json()["message"]


@pytest.mark.django_db
def test_national_id_of_another_participant_does_not_work(api_client: APIClient) -> None:
    """کد ملیِ یک شرکت‌کنندهٔ دیگر با این شماره نمی‌خواند ⇒ پیدا نشد."""
    first = create_test_participant(seq=403)
    second = create_test_participant(seq=404)
    res = api_client.post(
        LOOKUP_URL,
        data={"phone_number": first.phone_number, "national_id": second.national_id},
        format="json",
    )
    assert res.json()["data"]["state"] == "not_found"


@pytest.mark.django_db
def test_persian_digits_are_accepted_for_both_fields(api_client: APIClient) -> None:
    """ارقامِ فارسی در هر دو فیلد نرمال می‌شوند (کاربر با کیبورد فارسی)."""
    user = create_test_participant(seq=405)
    fa = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
    res = api_client.post(
        LOOKUP_URL,
        data={
            "phone_number": user.phone_number.translate(fa),
            "national_id": user.national_id.translate(fa),
        },
        format="json",
    )
    assert res.json()["data"]["state"] == "session_ready"

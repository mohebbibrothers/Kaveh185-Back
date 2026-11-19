"""تست‌های فهرست ۱۷ مسجد، رتبه‌بندی زنده مشارکت مساجد و مدیریت مساجد توسط ادمین."""

from __future__ import annotations

from io import StringIO

import pytest
from django.core.management import call_command
from rest_framework.test import APIClient

from apps.mosques.models import Mosque
from apps.mosques.services import (
    increment_mosque_completed_exam_count,
    increment_mosque_registered_count,
)


@pytest.mark.django_db()
def test_seed_17_mosques_dropdown_and_live_leaderboard(
    api_client: APIClient,
) -> None:
    """بارگذاری ۱۷ مسجد پیش‌فرض، لیست کشویی ثبت‌نام و رنکینگ مشارکت مساجد بر اساس تعداد آزمون‌داده‌ها."""
    out = StringIO()
    call_command("seed_mosques", stdout=out)
    assert Mosque.objects.filter(is_active=True).count() == 17

    dropdown_resp = api_client.get("/api/v1/mosques/")
    assert dropdown_resp.status_code == 200
    items = dropdown_resp.json()["data"]
    assert len(items) == 17

    # افزایش تعداد مشارکت در آزمون برای مسجد شماره ۵ تا به رتبه ۱ جدول صعود کند
    target_mosque = Mosque.objects.get(code="MSQ-05")
    increment_mosque_registered_count(target_mosque.id)
    for _ in range(4):
        increment_mosque_completed_exam_count(target_mosque.id)

    second_mosque = Mosque.objects.get(code="MSQ-02")
    for _ in range(2):
        increment_mosque_completed_exam_count(second_mosque.id)

    lb_resp = api_client.get("/api/v1/mosques/leaderboard/")
    assert lb_resp.status_code == 200
    lb_data = lb_resp.json()["data"]
    assert lb_data["total_mosques"] == 17
    assert lb_data["total_completed_participants"] == 6

    top_rank = lb_data["leaderboard"][0]
    assert top_rank["rank"] == 1
    assert top_rank["code"] == "MSQ-05"
    assert top_rank["completed_participants_count"] == 4
    assert top_rank["tier"] == "gold"

    second_rank = lb_data["leaderboard"][1]
    assert second_rank["rank"] == 2
    assert second_rank["code"] == "MSQ-02"
    assert second_rank["completed_participants_count"] == 2
    assert second_rank["tier"] == "silver"


@pytest.mark.django_db()
def test_admin_mosque_crud_and_seed_endpoint(admin_client: APIClient) -> None:
    """ادمین باید بتواند مسجد جدید اضافه کند، ویرایش نماید یا غیرفعال سازد."""
    seed_resp = admin_client.post("/api/v1/mosques/admin/seed-defaults/")
    assert seed_resp.status_code == 200
    assert seed_resp.json()["data"]["total"] == 17

    create_resp = admin_client.post(
        "/api/v1/mosques/admin/",
        data={
            "code": "MSJ-185-99",
            "name": "مسجد شهدای گمنام کاوه",
            "neighborhood": "شهرک شهید کاوه",
            "imam_name": "حجت‌الاسلام حسینی",
            "commander_name": "برادر جعفری",
            "target_participants": 300,
            "display_order": 99,
        },
        format="json",
    )
    assert create_resp.status_code == 201
    mosque_id = create_resp.json()["data"]["id"]

    list_resp = admin_client.get("/api/v1/mosques/admin/?search=گمنام")
    assert list_resp.status_code == 200

    patch_resp = admin_client.patch(
        f"/api/v1/mosques/admin/{mosque_id}/",
        data={"target_participants": 450},
        format="json",
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["data"]["target_participants"] == 450

    del_resp = admin_client.delete(f"/api/v1/mosques/admin/{mosque_id}/")
    assert del_resp.status_code == 200
    assert Mosque.all_objects.get(pk=mosque_id).is_active is False


@pytest.mark.django_db()
def test_leaderboard_ties_break_by_persian_alphabet_not_display_order(
    api_client: APIClient,
) -> None:
    """تساویِ امتیاز باید با الفبای **نامِ مسجد** شکسته شود، نه `display_order`."""
    call_command("seed_mosques", stdout=StringIO())

    # دو مسجد با نمایشِ دلخواهِ برعکسِ الفبا، هر دو با ۳ شرکت‌کننده
    zarrah = Mosque.objects.get(code="MSQ-01")  # نام: مسجد جامع صاحب‌الزمان
    amir = Mosque.objects.get(code="MSQ-02")  # نام: مسجد حضرت امیرالمؤمنین
    Mosque.objects.filter(pk=zarrah.pk).update(display_order=99)
    Mosque.objects.filter(pk=amir.pk).update(display_order=1)
    for _ in range(3):
        increment_mosque_completed_exam_count(zarrah.id)
        increment_mosque_completed_exam_count(amir.id)

    data = api_client.get("/api/v1/mosques/leaderboard/").json()["data"]
    board = data["leaderboard"]

    # «امیرالمؤمنین» الفبایی پیش از «صاحب‌الزمان» است ⇒ رتبهٔ ۱
    assert board[0]["code"] == "MSQ-02"
    assert board[0]["rank"] == 1
    assert board[1]["code"] == "MSQ-01"
    # هم‌امتیاز ⇒ رتبهٔ مشترک (۱۲۲۴)، نه ۱ و ۲
    assert board[1]["rank"] == 1
    # سطحِ رقابتی هم یکسان است
    assert board[0]["tier"] == board[1]["tier"] == "gold"


@pytest.mark.django_db()
def test_leaderboard_zero_participation_rows_get_no_rank_and_alpha_order(
    api_client: APIClient,
) -> None:
    """مساجدِ بی‌مشارکت رتبهٔ ۰ می‌گیرند و بین خودشان الفبایی مرتب‌اند."""
    call_command("seed_mosques", stdout=StringIO())
    increment_mosque_completed_exam_count(Mosque.objects.get(code="MSQ-09").id)

    data = api_client.get("/api/v1/mosques/leaderboard/").json()["data"]
    board = data["leaderboard"]
    assert board[0]["code"] == "MSQ-09" and board[0]["rank"] == 1
    zeros = [row for row in board if row["completed_participants_count"] == 0]
    assert zeros and all(row["rank"] == 0 for row in zeros)
    cores = [row["name_core"] for row in zeros]
    assert cores == sorted(cores, key=lambda n: [_ALPHA.index(c) for c in n if c in _ALPHA])


@pytest.mark.django_db()
def test_leaderboard_exposes_display_initial_from_core_name(api_client: APIClient) -> None:
    """حرفِ نشان از نامِ مسجد می‌آید، نه از کلمهٔ «مسجد»."""
    call_command("seed_mosques", stdout=StringIO())
    data = api_client.get("/api/v1/mosques/leaderboard/").json()["data"]
    by_code = {row["code"]: row for row in data["leaderboard"]}
    assert by_code["MSQ-01"]["initial"] == "ص"
    assert by_code["MSQ-02"]["initial"] == "ا"
    assert by_code["MSQ-05"]["initial"] == "س"
    assert by_code["MSQ-09"]["initial"] == "م"  # مسجد امام موسی کاظم → «م» درست است
    assert all(row["initial"] != "" for row in data["leaderboard"])


_ALPHA = "آاأإءبپتثجچحخدذرزژسشصضطظعغفقکگلمنوهیئؤ"

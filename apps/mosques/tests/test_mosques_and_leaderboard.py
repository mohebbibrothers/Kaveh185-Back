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

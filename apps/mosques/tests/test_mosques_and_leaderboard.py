"""تست‌های فهرست ۱۷ مسجد، رتبه‌بندی زنده مشارکت مساجد و مدیریت مساجد توسط ادمین."""

from __future__ import annotations

from datetime import timedelta
from io import StringIO

import pytest
from django.core.management import call_command
from django.utils import timezone
from rest_framework.test import APIClient

from apps.exam.choices import ExamAttemptStatus
from apps.exam.models import ExamAttempt
from apps.mosques.models import Mosque
from tests.factories import create_test_participant


def _finish_exams(*, mosque: Mosque, count: int, seq_start: int = 700) -> None:
    """ساختِ `count` کارنامهٔ **واقعیِ پایان‌یافته** برای یک مسجد.

    از این به بعد شمارنده‌ها «کشِ کارایی» هستند و جدول از شمارشِ زندهٔ
    `ExamAttempt` می‌خواند؛ پس تستی که فقط عددِ شمارنده را بالا ببرد، چیزی را
    که کاربر می‌بیند نمی‌سنجد. این کمکی، همان دادهٔ واقعی را می‌سازد.
    """
    for i in range(count):
        seq = seq_start + mosque.pk * 100 + i
        user = create_test_participant(seq=seq, mosque=mosque)
        ExamAttempt.objects.create(
            user=user,
            mosque=mosque,
            tracking_code=f"TRK-FIN-{seq}",
            status=ExamAttemptStatus.COMPLETED,
            expires_at=timezone.now() + timedelta(minutes=5),
        )


def _seed_leaderboard_rows(api_client: APIClient, counts: list[int]) -> list[dict]:
    """پرکردنِ جدول با دادهٔ **واقعی** و برگرداندنِ ردیف‌های رهبری.

    چرا نه `UPDATE` روی شمارنده؟ چون شمارنده‌ها حالا کشِ کارایی‌اند و جدول از
    شمارشِ زنده می‌خواند (منبعِ حقیقت). تستی که شمارنده را دستی بالا ببرد،
    رفتارِ واقعی را نمی‌سنجد و خودش می‌شکند. پس برای هر مسجد به تعدادِ لازم
    کارنامهٔ واقعیِ پایان‌یافته می‌سازیم.
    """
    call_command("seed_mosques", stdout=StringIO())
    mosques = list(Mosque.objects.filter(is_active=True).order_by("display_order", "id"))
    seq = 700
    for mosque, count in zip(mosques, counts, strict=False):
        for _ in range(count):
            seq += 1
            user = create_test_participant(seq=seq, mosque=mosque)
            ExamAttempt.objects.create(
                user=user,
                mosque=mosque,
                tracking_code=f"TRK-LB-{seq}",
                status=ExamAttemptStatus.COMPLETED,
                expires_at=timezone.now() + timedelta(minutes=5),
            )
    return api_client.get("/api/v1/mosques/leaderboard/").json()["data"]["leaderboard"]


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
    _finish_exams(mosque=target_mosque, count=4)
    second_mosque = Mosque.objects.get(code="MSQ-02")
    _finish_exams(mosque=second_mosque, count=2)

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
    _finish_exams(mosque=zarrah, count=3)
    _finish_exams(mosque=amir, count=3)

    data = api_client.get("/api/v1/mosques/leaderboard/").json()["data"]
    board = data["leaderboard"]

    # «امیرالمؤمنین» الفبایی پیش از «صاحب‌الزمان» است ⇒ رتبهٔ ۱
    assert board[0]["code"] == "MSQ-02"
    assert board[0]["rank"] == 1
    assert board[1]["code"] == "MSQ-01"
    # هم‌امتیاز ⇒ جایگاهِ مشترکِ ۱، نه ۱ و ۲
    assert board[1]["rank"] == 1
    # سطحِ رقابتی هم یکسان است
    assert board[0]["tier"] == board[1]["tier"] == "gold"


@pytest.mark.django_db()
def test_leaderboard_zero_participation_rows_get_no_rank_and_alpha_order(
    api_client: APIClient,
) -> None:
    """مساجدِ بی‌مشارکت رتبهٔ ۰ می‌گیرند و بین خودشان الفبایی مرتب‌اند."""
    call_command("seed_mosques", stdout=StringIO())
    _finish_exams(mosque=Mosque.objects.get(code="MSQ-09"), count=1)

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


@pytest.mark.django_db()
def test_simulate_leaderboard_command_builds_scenarios(api_client: APIClient) -> None:
    """دستورِ شبیه‌سازی، شمارنده‌ها را می‌سازد و کشِ جدول را باطل می‌کند."""
    call_command("seed_mosques", stdout=StringIO())

    call_command("simulate_leaderboard", "--scenario", "realistic", "--force", stdout=StringIO())
    data = api_client.get("/api/v1/mosques/leaderboard/").json()["data"]
    assert data["total_completed_participants"] == 62
    assert data["leaderboard"][0]["completed_participants_count"] == 14
    assert data["leaderboard"][0]["rank"] == 1
    # دو مسجدِ بعدی هم‌امتیاز (۱۱) ⇒ هر دو جایگاهِ ۲؛ نفرِ بعدی جایگاهِ ۳
    # (قاعدهٔ «جایگاه»: رتبهٔ بعدی بعد از گروهِ مساوی، نه شمارهٔ ردیف)
    assert data["leaderboard"][1]["rank"] == 2
    assert data["leaderboard"][2]["rank"] == 2
    assert data["leaderboard"][3]["rank"] == 3

    # سناریوی تساوی: رتبهٔ مشترک و سطحِ یکسان
    call_command(
        "simulate_leaderboard", "--scenario", "tie", "--reset", "--force", stdout=StringIO()
    )
    tie = api_client.get("/api/v1/mosques/leaderboard/").json()["data"]["leaderboard"]
    assert tie[0]["completed_participants_count"] == 5
    tied = [r for r in tie if r["completed_participants_count"] == 5]
    assert len(tied) == 4
    assert {r["rank"] for r in tied} == {1}
    assert {r["tier"] for r in tied} == {"gold"}


@pytest.mark.django_db()
def test_simulate_leaderboard_reset_returns_to_starting_line(api_client: APIClient) -> None:
    """`--only-reset` همهٔ شمارنده‌ها را صفر می‌کند و جدول به خطِ شروع برمی‌گردد."""
    call_command("seed_mosques", stdout=StringIO())
    call_command("simulate_leaderboard", "--scenario", "realistic", "--force", stdout=StringIO())
    call_command("simulate_leaderboard", "--only-reset", "--force", stdout=StringIO())

    data = api_client.get("/api/v1/mosques/leaderboard/").json()["data"]
    assert data["total_completed_participants"] == 0
    assert all(r["rank"] == 0 for r in data["leaderboard"])


@pytest.mark.django_db()
def test_leaderboard_exposes_tie_flags(api_client: APIClient) -> None:
    """`is_tied`/`tied_count` دقیقاً همان گروهِ هم‌امتیاز را می‌گویند."""
    rows = _seed_leaderboard_rows(api_client, [14, 11, 11, 3, 3, 3])

    first = rows[0]
    assert first["rank"] == 1
    assert first["is_tied"] is False

    tied = [r for r in rows if r["completed_participants_count"] == 11]
    assert len(tied) == 2
    assert all(r["rank"] == 2 and r["is_tied"] is True and r["tied_count"] == 2 for r in tied)

    # هیچ مسجدی با رتبهٔ صفر «مشترک» علامت نمی‌خورد
    zeros = [r for r in rows if r["completed_participants_count"] == 0]
    assert zeros and all(r["is_tied"] is False and r["tied_count"] == 0 for r in zeros)


@pytest.mark.django_db()
def test_rank_uses_shared_place_not_row_number(api_client: APIClient) -> None:
    """قاعدهٔ جایگاه: ۱۴/۱۱/۱۱/۸ ⇒ ۱، ۲، ۲، ۳ — تا «سوم» و برنز وجود داشته باشد.

    با قاعدهٔ ۱۲۲۴ رتبه‌ها ۱، ۲، ۲، ۴ می‌شد و جدول هرگز مدالِ برنز نداشت،
    درحالی‌که سکوی صفحه سه جایگاه دارد. این تست همان تناقض را قفل می‌کند.
    """
    rows = _seed_leaderboard_rows(api_client, [14, 11, 11, 8, 8, 3])
    assert [r["rank"] for r in rows[:6]] == [1, 2, 2, 3, 3, 4]
    # سطح‌ها هم با جایگاه هم‌خوان‌اند: جایگاه‌های ۲ و ۳ نقره‌ای‌اند
    assert {r["tier"] for r in rows[1:5]} == {"silver"}
    # سه ردیفِ اول دقیقاً همان سه جایگاهِ سکو هستند
    assert {r["rank"] for r in rows[:3]} == {1, 2}


@pytest.mark.django_db()
def test_recount_restores_counters_from_real_attempts(api_client: APIClient) -> None:
    """`--purge` + `--recount` آمارِ جدول را از کارنامه‌های واقعی بازمی‌سازد.

    سناریوی واقعی: ادمین با `simulate_leaderboard` جدول را برای تست پر کرده و
    حالا می‌خواهد دادهٔ واقعی برگردد. صفرکردن پاسخ نیست (اگر مسابقه در جریان
    باشد اعدادِ واقعی را می‌سوزاند)؛ بازشماری از `ExamAttempt` پاسخِ درست است.
    """
    call_command("seed_mosques", stdout=StringIO())
    mosque = Mosque.objects.get(code="MSQ-01")
    other = Mosque.objects.get(code="MSQ-02")

    # دو کارنامهٔ واقعیِ پایان‌یافته برای یک مسجد
    for i in range(2):
        user = create_test_participant(seq=900 + i, mosque=mosque)
        ExamAttempt.objects.create(
            user=user,
            mosque=mosque,
            tracking_code=f"TRK-RECOUNT-{i}",
            status=ExamAttemptStatus.COMPLETED,
            expires_at=timezone.now() + timedelta(minutes=5),
        )
    # یک کارنامهٔ نیمه‌کاره (نباید «کامل» شمرده شود)
    user = create_test_participant(seq=909, mosque=other)
    ExamAttempt.objects.create(
        user=user,
        mosque=other,
        tracking_code="TRK-RECOUNT-9",
        status=ExamAttemptStatus.IN_PROGRESS,
        expires_at=timezone.now() + timedelta(minutes=5),
    )

    # حالا شمارنده‌ها را با شبیه‌سازی خراب می‌کنیم
    call_command("simulate_leaderboard", "--scenario", "realistic", "--force", stdout=StringIO())
    # دادهٔ شبیه‌سازی حالا **واقعی** است، پس شمارنده هم از همان کارنامه‌ها
    # بازشماری می‌شود: ۱۴ کارنامهٔ ساختگی + ۲ کارنامهٔ واقعیِ همین تست.
    simulated = ExamAttempt.objects.filter(tracking_code__startswith="SIM-", mosque=mosque).count()
    expected = simulated + 2
    assert Mosque.objects.get(pk=mosque.pk).completed_exam_count == expected

    # بیشترین واقع‌گرایی: اول دادهٔ ساختگی را پاک می‌کنیم (همان کاری که ادمین
    # باید بکند)، بعد بازشماری. `--recount` خودش دادهٔ ساختگی را حذف نمی‌کند.
    call_command("simulate_leaderboard", "--purge", "--force", stdout=StringIO())
    call_command("simulate_leaderboard", "--recount", "--force", stdout=StringIO())

    mosque.refresh_from_db()
    other.refresh_from_db()
    assert mosque.completed_exam_count == 2
    assert mosque.registered_count == 2
    assert other.completed_exam_count == 0
    assert other.registered_count == 1  # ثبت‌نام شده ولی کارنامه‌اش کامل نیست

    board = api_client.get("/api/v1/mosques/leaderboard/").json()["data"]
    assert board["total_completed_participants"] == 2
    assert board["leaderboard"][0]["completed_participants_count"] == 2

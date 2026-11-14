"""تست‌های جامع آمار زنده، کاوشگر چندفیلتره قرعه‌کشی حضوری، پاسخنامه ادمین و خروجی اکسل ۷ برگی."""

from __future__ import annotations

from datetime import date
from io import BytesIO

import pytest
from openpyxl import load_workbook
from rest_framework.test import APIClient

from apps.authentication.services import issue_tokens_and_session
from apps.exam.models import Question
from apps.mosques.models import Mosque
from tests.factories import create_test_participant


def _complete_exam_for_user(user: object) -> None:
    """کمک‌کنندهٔ اجرای کامل یک آزمون ۵ سواله برای کاربر تستی."""
    tokens = issue_tokens_and_session(user=user)  # type: ignore[arg-type]
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
    client.post("/api/v1/exam/start/")
    for q_num in range(1, 6):
        client.post(
            "/api/v1/exam/answer/",
            data={"question_number": q_num, "selected_position": 1},
            format="json",
        )
    client.post("/api/v1/exam/finish/")


@pytest.mark.django_db()
def test_multi_filter_lottery_explorer_admin_detail_and_7_sheet_excel(
    admin_client: APIClient,
    seeded_mosques: list[Mosque],
    seeded_questions: list[Question],
) -> None:
    """تست فیلتر هم‌زمان بر اساس مسجد، سن، تعداد درست و مرتب‌سازی پویا + خروجی اکسل ۷ برگی RTL."""
    del seeded_questions
    mosque_a = seeded_mosques[0]
    mosque_b = seeded_mosques[1]

    # ساخت دو شرکت‌کننده در دو مسجد و دو رده سنی متفاوت
    teen_user = create_test_participant(
        seq=301,
        mosque=mosque_a,
        first_name="امیرعلی",
        last_name="نوجوان",
        birth_date=date(2011, 4, 10),  # نوجوان
    )
    adult_user = create_test_participant(
        seq=302,
        mosque=mosque_b,
        first_name="حمیدرضا",
        last_name="بزرگسال",
        birth_date=date(1992, 8, 20),  # بزرگسال
    )

    _complete_exam_for_user(teen_user)
    _complete_exam_for_user(adult_user)

    # ۱) داشبورد آماری زنده
    dash_resp = admin_client.get("/api/v1/reporting/admin/dashboard/")
    assert dash_resp.status_code == 200
    dash = dash_resp.json()["data"]
    assert dash["overview"]["total_finished_exams"] >= 2
    assert len(dash["mosques_ranking_and_analytics"]) == 17
    assert len(dash["question_bank_analytics"]) >= 8

    # ۲) کاوشگر چندفیلتره قرعه‌کشی: فیلتر بر اساس مسجد اول و حداکثر سن ۲۰ سال
    exp_resp = admin_client.get(
        f"/api/v1/reporting/admin/participants/?mosque_ids={mosque_a.id}&max_age=20&ordering=-total_score,duration_seconds"
    )
    assert exp_resp.status_code == 200
    results = exp_resp.json()["data"]["results"]
    assert len(results) == 1
    row = results[0]
    assert row["user"]["first_name"] == "امیرعلی"
    assert row["mosque"]["id"] == mosque_a.id
    # ادمین باید ریز هر ۵ سوال و گزینه انتخابی کاربر را ببیند
    assert len(row["answers"]) == 5
    for ans in row["answers"]:
        assert "question_text" in ans
        assert "selected_option_text" in ans
        assert "correct_option_text" in ans
        assert ans["result_status"] in {"correct", "wrong", "unanswered"}

    # ۳) مشاهده پروندهٔ کامل تک‌شرکت‌کننده توسط ادمین (با شناسه، کد رهگیری، و بدون آزمون)
    detail_resp = admin_client.get(f"/api/v1/reporting/admin/participants/{teen_user.id}/")
    assert detail_resp.status_code == 200
    assert detail_resp.json()["data"]["has_exam_attempt"] is True
    assert len(detail_resp.json()["data"]["participant_report"]["answers"]) == 5

    teen_tracking = row["tracking_code"]
    by_tracking_resp = admin_client.get(
        f"/api/v1/reporting/admin/participants/by-tracking/{teen_tracking}/"
    )
    assert by_tracking_resp.status_code == 200
    assert by_tracking_resp.json()["data"]["participant_report"]["tracking_code"] == teen_tracking

    # ۳.۲) اجرای قرعه‌کشی زنده مراسم با گواهی اثبات رمزنگاری‌شده
    draw_resp = admin_client.post(
        "/api/v1/reporting/admin/lottery/draw/",
        data={
            "winners_count": 1,
            "reserves_count": 1,
            "ceremony_title": "قرعه‌کشی هفته بسیج حوزه ۱۸۵ شهید کاوه",
            "client_seed": "STAGE-1405",
            "min_correct": 0,
        },
        format="json",
    )
    assert draw_resp.status_code == 200
    draw_data = draw_resp.json()["data"]
    assert draw_data["eligible_pool_count"] >= 2
    assert draw_data["drawn_winners_count"] == 1
    assert draw_data["drawn_reserves_count"] == 1
    assert len(draw_data["cryptographic_proof"]["draw_proof_sha256"]) == 64

    # ۳.۳) بررسی اندپوینت‌های یکپارچهٔ صفحه اول (Bootstrap) و کاتالوگ کشف API
    bootstrap_resp = admin_client.get("/api/v1/core/bootstrap/")
    assert bootstrap_resp.status_code == 200
    assert len(bootstrap_resp.json()["data"]["mosques"]) == 17
    root_resp = admin_client.get("/api/v1/")
    assert root_resp.status_code == 200
    assert "public_endpoints" in root_resp.json()["data"]

    no_exam_user = create_test_participant(
        seq=303,
        mosque=mosque_a,
        first_name="مهدی",
        last_name="بی‌آزمون",
        birth_date=date(2016, 1, 15),
    )
    no_exam_detail = admin_client.get(f"/api/v1/reporting/admin/participants/{no_exam_user.id}/")
    assert no_exam_detail.status_code == 200
    assert no_exam_detail.json()["data"]["has_exam_attempt"] is False

    # ۳.۵) بررسی ترکیبات متنوع فیلترهای قرعه‌کشی و مرتب‌سازی چندگانه
    combo_resp = admin_client.get(
        "/api/v1/reporting/admin/participants/"
        f"?mosque_id={mosque_b.id}&mosque_code={mosque_b.code}"
        "&min_age=18&max_age=60&min_score=0&max_score=100"
        "&min_correct=0&max_correct=5&min_wrong=0&max_wrong=5"
        "&min_unanswered=0&max_unanswered=5&min_duration=0&max_duration=600"
        "&status=completed&search=حمیدرضا&birth_from=1350/01/01&birth_to=1400/12/29"
        "&include_answers=false&ordering=-correct_count,wrong_count,-age,mosque"
    )
    assert combo_resp.status_code == 200
    assert len(combo_resp.json()["data"]["results"]) == 1

    # ۴) خروجی اکسل ۷ برگی راست‌به‌چپ (`.xlsx`)
    excel_resp = admin_client.get("/api/v1/reporting/admin/export.xlsx")
    assert excel_resp.status_code == 200
    assert "X-Report-SHA256" in excel_resp
    assert int(excel_resp["X-Report-Rows"]) >= 2

    wb = load_workbook(BytesIO(excel_resp.content))
    expected_sheets = [
        "رتبه‌بندی قرعه‌کشی (برترین‌ها)",
        "مشخصات کامل و ریز پاسخ‌ها",
        "رتبه‌بندی مشارکت مساجد",
        "تفکیک بر اساس مساجد",
        "تفکیک رده‌های سنی",
        "تحلیل بانک سوالات",
        "خلاصه مدیریتی و متادیتا",
    ]
    assert wb.sheetnames == expected_sheets
    for sheet_name in expected_sheets:
        ws = wb[sheet_name]
        assert ws.views.sheetView[0].rightToLeft is True
        assert ws.max_row >= 2

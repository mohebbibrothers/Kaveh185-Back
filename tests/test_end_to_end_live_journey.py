"""تست جامع و واقعی سرتاسری (End-to-End Live Journey) از تمام بخش‌های سامانه کاوه ۱۸۵."""

from __future__ import annotations

from io import BytesIO

import pytest
from django.core.management import call_command
from openpyxl import load_workbook
from rest_framework.test import APIClient

from apps.audit_logs.chain import verify_audit_chain


@pytest.mark.django_db()
def test_complete_real_world_kaveh185_e2e_journey() -> None:
    """شبیه‌سازی کامل و واقعی تمام سناریوهای شرکت‌کننده، آزمون، کارنامه، ادمین، قرعه‌کشی و اکسل."""
    # ۱. اجرای سیدر واقعی همراه با داده‌های دمو (۱۷ مسجد + سوالات + ادمین + ۱۷ شرکت‌کننده دمو)
    call_command("seed_kaveh185", "--with-demo-data")

    public_client = APIClient()

    # ۲. تست کاتالوگ کشف API در ریشهٔ سایت (`/`, `/api/v1/`) و پروب‌های سلامت
    welcome_resp = public_client.get("/")
    assert welcome_resp.status_code == 200
    assert welcome_resp.json()["success"] is True

    discovery_resp = public_client.get("/api/v1/")
    assert discovery_resp.status_code == 200
    assert "public_endpoints" in discovery_resp.json()["data"]

    for health_url in ("/api/v1/health/live/", "/api/v1/health/ready/", "/api/v1/health/deep/"):
        h_resp = public_client.get(health_url)
        assert h_resp.status_code == 200
        assert h_resp.json()["success"] is True

    # ۳. تست اندپوینت تک‌درخواستی صفحهٔ اول (Single-Request Landing Bootstrap)
    bootstrap_resp = public_client.get("/api/v1/core/bootstrap/")
    assert bootstrap_resp.status_code == 200
    b_data = bootstrap_resp.json()["data"]
    assert b_data["exam_status"]["window_state"] == "open"
    assert b_data["exam_status"]["can_participate"] is True
    assert len(b_data["mosques"]) == 17
    assert b_data["leaderboard"]["total_active_mosques"] == 17
    assert b_data["leaderboard"]["total_exam_participants"] >= 17

    selected_mosque_id = b_data["mosques"][0]["id"]

    # ۴. ثبت‌نام واقعی یک شرکت‌کننده جدید با تاریخ تولد شمسی و ارقام فارسی
    reg_resp = public_client.post(
        "/api/v1/auth/register/",
        data={
            "first_name": "محمدجواد",
            "last_name": "محبی",
            "national_id": "۰۰۱۳۵۴۲۴۱۹",
            "phone_number": "۰۹۱۲۹۹۹۸۸۷۷",
            "birth_date": "۱۳۸۳/۰۶/۱۵",
            "mosque_id": selected_mosque_id,
        },
        format="json",
    )
    assert reg_resp.status_code == 201
    reg_data = reg_resp.json()["data"]
    assert reg_data["is_new_user"] is True
    assert reg_data["otp_required"] is False
    assert reg_data["exam_eligibility"]["can_enter_exam"] is True
    participant_token = reg_data["access"]

    participant_client = APIClient()
    participant_client.credentials(HTTP_AUTHORIZATION=f"Bearer {participant_token}")

    # ۵. ورود به آزمون ۵ سواله (`POST /api/v1/exam/start/`) و بررسی عدم افشای کلید سوالات
    start_resp = participant_client.post("/api/v1/exam/start/", data={}, format="json")
    assert start_resp.status_code == 201
    attempt_data = start_resp.json()["data"]
    assert attempt_data["total_questions"] == 5
    assert attempt_data["remaining_seconds"] > 0
    assert len(attempt_data["questions"]) == 5
    for q in attempt_data["questions"]:
        assert "correct" not in str(q).lower()
        assert len(q["options"]) == 4

    # ۶. تست قانون عدم امکان رد کردن سوال (تلاش برای پاسخ به سوال ۲ قبل از سوال ۱)
    skip_resp = participant_client.post(
        "/api/v1/exam/answer/",
        data={"question_number": 2, "selected_position": 1},
        format="json",
    )
    assert skip_resp.status_code == 400
    assert skip_resp.json()["code"] == "cannot_skip_question"

    # ۷. تست عدم امکان پایان دادن زودهنگام به آزمون قبل از پاسخ به هر ۵ سوال
    early_finish_resp = participant_client.post("/api/v1/exam/finish/", data={}, format="json")
    assert early_finish_resp.status_code == 400
    assert early_finish_resp.json()["code"] == "incomplete_exam_answers"

    # ۸. پاسخگویی به هر ۵ سوال به ترتیب ۱ تا ۵ و بررسی بازیابی جلسه در رفرش صفحه
    for q_num in range(1, 6):
        ans_resp = participant_client.post(
            "/api/v1/exam/answer/",
            data={"question_number": q_num, "selected_position": ((q_num % 4) + 1)},
            format="json",
        )
        assert ans_resp.status_code == 200
        assert ans_resp.json()["data"]["answered_count"] == q_num

    current_resp = participant_client.get("/api/v1/exam/current/")
    assert current_resp.status_code == 200
    assert current_resp.json()["data"]["can_finish_now"] is True

    # ۹. پایان آزمون و دریافت کارنامه نهایی (بدون افشای اینکه کدام سوال درست یا غلط بوده)
    finish_resp = participant_client.post("/api/v1/exam/finish/", data={}, format="json")
    assert finish_resp.status_code == 200
    report_card = finish_resp.json()["data"]
    tracking_code = report_card["tracking_code"]
    assert report_card["summary"]["total_questions"] == 5
    assert report_card["summary"]["correct_count"] + report_card["summary"]["wrong_count"] == 5
    assert len(report_card["communication_channels"]) >= 1
    assert "questions" not in report_card

    # ۱۰. تست قفل تک‌بارمصرف بودن آزمون (تلاش مجدد برای ورود به آزمون باید با 409 رد شود)
    retry_resp = participant_client.post("/api/v1/exam/start/", data={}, format="json")
    assert retry_resp.status_code == 409
    assert retry_resp.json()["code"] == "exam_already_completed"

    # ۱۱. استعلام عمومی اصالت رسید با کد رهگیری
    receipt_resp = public_client.get(f"/api/v1/exam/receipt/{tracking_code}/")
    assert receipt_resp.status_code == 200
    assert receipt_resp.json()["data"]["tracking_code"] == tracking_code

    # ۱۲. ورود واقعی ادمین با اکانت پیش‌فرض (`09120000000` / `Kaveh185@Admin1405`)
    admin_login_resp = public_client.post(
        "/api/v1/auth/login/password/",
        data={"identifier": "09120000000", "password": "Kaveh185@Admin1405"},
        format="json",
    )
    assert admin_login_resp.status_code == 200
    admin_token = admin_login_resp.json()["data"]["access"]

    admin_client = APIClient()
    admin_client.credentials(HTTP_AUTHORIZATION=f"Bearer {admin_token}")

    # ۱۳. مرکز فرماندهی ۳۶۰ درجه ادمین و داشبورد آماری زنده
    cc_resp = admin_client.get("/api/v1/admin/command-center/")
    assert cc_resp.status_code == 200
    cc_alias_resp = admin_client.get("/api/v1/command-center/overview/")
    assert cc_alias_resp.status_code == 200

    dash_resp = admin_client.get("/api/v1/reporting/admin/dashboard/")
    assert dash_resp.status_code == 200
    assert dash_resp.json()["data"]["overview"]["total_finished_exams"] >= 18

    # ۱۴. کاوشگر چندفیلتره قرعه‌کشی حضوری و مشاهدهٔ ریز ۵ سوال شرکت‌کننده با کد رهگیری
    explorer_resp = admin_client.get(
        f"/api/v1/reporting/admin/participants/?mosque_ids={selected_mosque_id}&min_age=10&max_age=45&ordering=-total_score,duration_seconds"
    )
    assert explorer_resp.status_code == 200
    assert explorer_resp.json()["data"]["count"] >= 1

    forensic_resp = admin_client.get(
        f"/api/v1/reporting/admin/participants/by-tracking/{tracking_code}/"
    )
    assert forensic_resp.status_code == 200
    forensic_answers = forensic_resp.json()["data"]["participant_report"]["answers"]
    assert len(forensic_answers) == 5

    # ۱۵. اجرای قرعه‌کشی زنده مراسم با گواهی اثبات رمزنگاری‌شده SHA-256
    lottery_resp = admin_client.post(
        "/api/v1/reporting/admin/lottery/draw/",
        data={
            "winners_count": 3,
            "reserves_count": 2,
            "ceremony_title": "مراسم قرعه‌کشی نهایی هفته بسیج حوزه ۱۸۵ شهید کاوه",
            "client_seed": "KAVEH185-FINAL-STAGE",
        },
        format="json",
    )
    assert lottery_resp.status_code == 200
    lottery_data = lottery_resp.json()["data"]
    assert lottery_data["drawn_winners_count"] == 3
    assert lottery_data["drawn_reserves_count"] == 2
    assert len(lottery_data["cryptographic_proof"]["draw_proof_sha256"]) == 64

    # ۱۶. دانلود و اعتبارسنجی فایل اکسل ۷ برگی راست‌به‌چپ (`.xlsx`)
    excel_resp = admin_client.get("/api/v1/reporting/admin/export.xlsx")
    assert excel_resp.status_code == 200
    wb = load_workbook(BytesIO(excel_resp.content))
    assert len(wb.sheetnames) == 7

    # ۱۷. صحت‌سنجی زنجیرهٔ هش ضدتحریف لاگ ممیزی (`AuditLog SHA-256 Chain`)
    chain_verification = verify_audit_chain()
    assert chain_verification["valid"] is True
    assert chain_verification["checked_count"] >= 20

"""تست‌های جامع موتور آزمون ۵ سواله، پنجره زمانی، عدم امکان رد کردن سوال، عدم افشای کلید و بازتصحیح."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.authentication.models import User
from apps.authentication.services import issue_tokens_and_session
from apps.exam.models import ExamAttempt, Question
from apps.exam.selectors import get_or_create_exam_configuration
from apps.mosques.models import Mosque
from apps.notifications.models import SMSDeliveryLog
from tests.factories import create_test_participant


@pytest.mark.django_db()
def test_exam_window_states_upcoming_open_and_ended(
    api_client: APIClient,
    participant_client: APIClient,
    seeded_questions: list[Question],
    admin_client: APIClient,
) -> None:
    """تست پنجرهٔ زمانی آزمون: قبل از شروع (`به زودی`)، حین مهلت (`فعال`) و پس از پایان (`مهلت تمام شد`)."""
    del seeded_questions
    now = timezone.now()

    # ۱) تنظیم زمان شروع در آینده -> وضعیت upcoming («شرکت در آزمون به زودی آغاز می‌شود.»)
    patch_upcoming = admin_client.patch(
        "/api/v1/exam/admin/config/",
        data={
            "starts_at": (now + timedelta(hours=2)).isoformat(),
            "ends_at": (now + timedelta(days=5)).isoformat(),
            "is_manually_open": True,
        },
        format="json",
    )
    assert patch_upcoming.status_code == 200

    st_upcoming = api_client.get("/api/v1/exam/status/").json()["data"]
    assert st_upcoming["window_state"] == "upcoming"
    assert st_upcoming["can_participate"] is False
    assert "به زودی" in st_upcoming["status_message"]

    start_early = participant_client.post("/api/v1/exam/start/")
    assert start_early.status_code == 403
    assert start_early.json()["code"] == "exam_not_started_yet"

    # ۲) تنظیم زمان پایان در گذشته -> وضعیت ended («مهلت شرکت در آزمون به پایان رسید.»)
    admin_client.patch(
        "/api/v1/exam/admin/config/",
        data={
            "starts_at": (now - timedelta(days=5)).isoformat(),
            "ends_at": (now - timedelta(hours=1)).isoformat(),
        },
        format="json",
    )
    st_ended = api_client.get("/api/v1/exam/status/").json()["data"]
    assert st_ended["window_state"] == "ended"
    assert st_ended["can_participate"] is False
    assert "پایان" in st_ended["status_message"]

    start_late = participant_client.post("/api/v1/exam/start/")
    assert start_late.status_code == 403
    assert start_late.json()["code"] == "exam_window_ended"


@pytest.mark.django_db()
def test_full_5_question_exam_flow_no_skip_zero_leak_and_post_exam_effects(
    api_client: APIClient,
    participant_client: APIClient,
    participant_user: User,
    seeded_questions: list[Question],
) -> None:
    """اجرای کامل آزمون ۵ سواله: تصادفی‌سازی دوگانه، منع رد کردن سوال، عدم افشای کلید، کارنامه و پیامک تشکر."""
    del seeded_questions

    # ۱) شروع آزمون ۵ سواله
    start_resp = participant_client.post(
        "/api/v1/exam/start/",
        HTTP_IDEMPOTENCY_KEY="start-exam-user-1",
    )
    assert start_resp.status_code == 201
    attempt_data = start_resp.json()["data"]
    assert attempt_data["total_questions"] == 5
    assert len(attempt_data["questions"]) == 5

    curr_resp = participant_client.get("/api/v1/exam/current/")
    assert curr_resp.status_code == 200
    assert curr_resp.json()["data"]["status"] == "in_progress"

    # بررسی عدم افشای کلید صحیح در سوالات دریافتی
    for q in attempt_data["questions"]:
        assert len(q["options"]) == 4
        assert [o["position"] for o in q["options"]] == [1, 2, 3, 4]
        for opt in q["options"]:
            assert "is_correct" not in opt
            assert "option_id" not in opt

    # ۲) قانون عدم امکان رد کردن سوال (No-Skip Rule): تلاش برای پاسخ به سوال ۲ قبل از سوال ۱ باید خطا بدهد
    skip_resp = participant_client.post(
        "/api/v1/exam/answer/",
        data={"question_number": 2, "selected_position": 1},
        format="json",
    )
    assert skip_resp.status_code == 400
    assert skip_resp.json()["code"] == "cannot_skip_question"

    # ۳) پاسخ به سوالات ۱ تا ۳ و تلاش برای پایان دادن به آزمون قبل از پاسخ به هر ۵ سوال (باید رد شود)
    for q_num in (1, 2, 3):
        ans_resp = participant_client.post(
            "/api/v1/exam/answer/",
            data={"question_number": q_num, "selected_position": 2},
            format="json",
        )
        assert ans_resp.status_code == 200
        # اطمینان از اینکه در حین پاسخگویی هیچ اطلاعاتی از درست یا غلط بودن لو نمی‌رود
        raw_json_str = str(ans_resp.json())
        assert "correct_count" not in raw_json_str
        assert "result_status" not in raw_json_str

    premature_finish = participant_client.post("/api/v1/exam/finish/")
    assert premature_finish.status_code == 400
    assert premature_finish.json()["code"] == "incomplete_exam_answers"

    # ۴) پاسخ به سوالات ۴ و ۵ و پایان دادن به آزمون
    for q_num in (4, 5):
        participant_client.post(
            "/api/v1/exam/answer/",
            data={"question_number": q_num, "selected_position": 1},
            format="json",
        )

    finish_resp = participant_client.post(
        "/api/v1/exam/finish/",
        HTTP_IDEMPOTENCY_KEY="finish-exam-user-1",
    )
    assert finish_resp.status_code == 200
    report_card = finish_resp.json()["data"]

    # ۵) بررسی ساختار کارنامه و عدم افشای اینکه کدام سوال درست یا غلط بوده است
    summary = report_card["summary"]
    assert summary["status"] == "completed"
    assert summary["total_questions"] == 5
    assert summary["unanswered_count"] == 0
    assert summary["correct_count"] + summary["wrong_count"] == 5
    assert summary["duration_seconds"] >= 1
    assert "questions" not in report_card
    assert "answers" not in report_card
    assert len(report_card["communication_channels"]) >= 1

    # ۶) بررسی ارسال پیامک تشکر پایان آزمون همراه با لینک کانال‌ها
    assert SMSDeliveryLog.objects.filter(
        recipient_phone=participant_user.phone_number,
        category="thank_you",
    ).exists()

    # ۷) بررسی افزایش آنی آمار مشارکت مسجد در جدول رنکینگ مساجد
    mosque = Mosque.objects.get(pk=participant_user.mosque_id)
    assert mosque.completed_exam_count >= 1

    # ۸) استعلام عمومی رسید دیجیتال کارنامه با کد رهگیری
    tracking_code = report_card["tracking_code"]
    receipt_resp = api_client.get(f"/api/v1/exam/receipt/{tracking_code}/")
    assert receipt_resp.status_code == 200
    assert receipt_resp.json()["data"]["tracking_code"] == tracking_code

    # ۹) تلاش مجدد همان کاربر برای شرکت دوباره در آزمون باید با ۴۰۹ رد شود (فقط ۱ بار مجاز است)
    second_attempt_resp = participant_client.post("/api/v1/exam/start/")
    assert second_attempt_resp.status_code == 409
    assert second_attempt_resp.json()["code"] == "exam_already_completed"


@pytest.mark.django_db()
def test_exam_timeout_mid_attempt_records_unanswered_questions(
    seeded_mosques: list[Mosque],
    seeded_questions: list[Question],
) -> None:
    """اگر زمان کاربر در اواسط آزمون (مثلاً روی سوال ۲) تمام شود، سوالات باقی‌مانده بی‌پاسخ ثبت می‌شوند."""
    del seeded_questions
    user = create_test_participant(seq=50, mosque=seeded_mosques[2])
    tokens = issue_tokens_and_session(user=user)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")

    # شروع آزمون و پاسخ فقط به سوال ۱
    client.post("/api/v1/exam/start/")
    client.post(
        "/api/v1/exam/answer/", data={"question_number": 1, "selected_position": 1}, format="json"
    )

    # شبیه‌سازی اتمام مهلت زمانی آزمون روی سرور
    attempt = ExamAttempt.objects.get(user=user)
    attempt.expires_at = timezone.now() - timedelta(seconds=10)
    attempt.save(update_fields=["expires_at"])

    # فراخوانی finish پس از اتمام زمان باید آزمون را با وضعیت timed_out و ۴ سوال بی‌پاسخ ببندد
    finish_resp = client.post("/api/v1/exam/finish/")
    assert finish_resp.status_code == 200
    summary = finish_resp.json()["data"]["summary"]
    assert summary["status"] == "timed_out"
    assert summary["unanswered_count"] == 4
    assert summary["correct_count"] + summary["wrong_count"] == 1


@pytest.mark.django_db()
def test_admin_question_key_edit_triggers_automatic_regrading(
    admin_client: APIClient,
    seeded_mosques: list[Mosque],
    seeded_questions: list[Question],
) -> None:
    """وقتی ادمین کلید صحیح یک سوال را تغییر می‌دهد، تمام کارنامه‌ها به‌صورت خودکار بازتصحیح می‌شوند."""
    del seeded_questions
    config = get_or_create_exam_configuration()
    config.questions_per_attempt = 5
    config.save()

    user = create_test_participant(seq=75, mosque=seeded_mosques[0])
    tokens = issue_tokens_and_session(user=user)
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

    attempt = ExamAttempt.objects.get(user=user)
    first_item = attempt.items.order_by("question_number").first()
    assert first_item is not None
    q_obj = first_item.question

    # تغییر کلید صحیح سوال اول توسط ادمین به گزینه‌ای که کاربر انتخاب کرده یا نکرده است
    chosen_opt_id = first_item.selected_option_id
    new_options_payload = []
    for opt in q_obj.options.order_by("option_number"):
        new_options_payload.append(
            {
                "option_number": opt.option_number,
                "text": opt.text,
                "is_correct": (opt.id == chosen_opt_id),
            }
        )

    patch_resp = admin_client.patch(
        f"/api/v1/exam/admin/questions/{q_obj.id}/",
        data={"options": new_options_payload},
        format="json",
    )
    assert patch_resp.status_code == 200

    first_item.refresh_from_db()
    assert first_item.result_status == "correct"

    regrade_resp = admin_client.post("/api/v1/exam/admin/regrade/")
    assert regrade_resp.status_code == 200
    assert regrade_resp.json()["data"]["regraded_attempts_count"] >= 1


@pytest.mark.django_db()
def test_exam_status_admin_question_bank_crud_bulk_and_seed_command(
    api_client: APIClient,
    admin_client: APIClient,
) -> None:
    """تست وضعیت عمومی آزمون، CRUD بانک سوالات، درج دسته‌ای و دستور `seed_kaveh185`."""
    from io import StringIO

    from django.core.management import call_command

    out = StringIO()
    call_command("seed_kaveh185", stdout=out)

    status_resp = api_client.get("/api/v1/exam/status/")
    assert status_resp.status_code == 200

    cfg_get = admin_client.get("/api/v1/exam/admin/config/")
    assert cfg_get.status_code == 200

    cfg_patch = admin_client.patch(
        "/api/v1/exam/admin/config/",
        data={"duration_seconds": 360, "questions_per_attempt": 5},
        format="json",
    )
    assert cfg_patch.status_code == 200
    assert cfg_patch.json()["data"]["duration_seconds"] == 360

    q_list = admin_client.get("/api/v1/exam/admin/questions/?search=کاوه&is_active=true")
    assert q_list.status_code == 200

    q_create = admin_client.post(
        "/api/v1/exam/admin/questions/",
        data={
            "text": "کدام عملیات با فرماندهی شهید محمود کاوه به پیروزی رسید؟",
            "category": "سیره شهدا",
            "source_reference": "کتاب کاوه",
            "difficulty": "medium",
            "points": 20,
            "options": [
                {"option_number": 1, "text": "عملیات کربلای ۲ (حاج عمران)", "is_correct": True},
                {"option_number": 2, "text": "عملیات فتح‌المبین", "is_correct": False},
                {"option_number": 3, "text": "عملیات خیبر", "is_correct": False},
                {"option_number": 4, "text": "عملیات بدر", "is_correct": False},
            ],
        },
        format="json",
    )
    assert q_create.status_code == 201
    qid = q_create.json()["data"]["id"]

    q_detail = admin_client.get(f"/api/v1/exam/admin/questions/{qid}/")
    assert q_detail.status_code == 200

    q_bulk = admin_client.post(
        "/api/v1/exam/admin/questions/bulk/",
        data={
            "questions": [
                {
                    "text": "سوال دسته‌ای نمونه هفته بسیج؟",
                    "category": "بسیج",
                    "difficulty": "easy",
                    "options": [
                        {"option_number": 1, "text": "گزینه ۱", "is_correct": False},
                        {"option_number": 2, "text": "گزینه ۲", "is_correct": True},
                        {"option_number": 3, "text": "گزینه ۳", "is_correct": False},
                        {"option_number": 4, "text": "گزینه ۴", "is_correct": False},
                    ],
                }
            ]
        },
        format="json",
    )
    assert q_bulk.status_code == 201

    q_seed = admin_client.post("/api/v1/exam/admin/questions/seed-defaults/")
    assert q_seed.status_code == 200

    q_del = admin_client.delete(f"/api/v1/exam/admin/questions/{qid}/")
    assert q_del.status_code == 200

    # تست ثبت یک‌جای ۵ پاسخ در لحظهٔ finish
    m_first = Mosque.objects.first()
    assert m_first is not None
    batch_user = create_test_participant(seq=99, mosque=m_first)
    batch_tokens = issue_tokens_and_session(user=batch_user)
    batch_client = APIClient()
    batch_client.credentials(HTTP_AUTHORIZATION=f"Bearer {batch_tokens['access']}")
    batch_client.post("/api/v1/exam/start/")
    batch_finish = batch_client.post(
        "/api/v1/exam/finish/",
        data={
            "answers": [
                {"question_number": i, "selected_position": ((i - 1) % 4) + 1} for i in range(1, 6)
            ]
        },
        format="json",
    )
    assert batch_finish.status_code == 200
    summary_data = batch_finish.json()["data"]["summary"]
    assert summary_data["correct_count"] + summary_data["wrong_count"] == 5

"""سلکتورهای خواندن وضعیت آزمون، سوالات بدون افشای کلید، کارنامه و بانک سوال."""

from __future__ import annotations

from typing import Any

from django.db.models import Count, Q, QuerySet
from django.utils import timezone

from apps.core.cache import cache_get_or_set_swr
from apps.core.exceptions import NotFoundDomainError
from apps.core.jalali import format_jalali_datetime

from .choices import (
    AnswerResultStatus,
    ExamAttemptStatus,
    ExamWindowState,
)
from .models import ExamAttempt, ExamConfiguration, Question


def get_or_create_exam_configuration() -> ExamConfiguration:
    """واکشی یا ایجاد تنظیمات یکتای آزمون سامانهٔ کاوه ۱۸۵."""
    config, _ = ExamConfiguration.all_objects.get_or_create(
        singleton_key="kaveh185_main",
    )
    return config


def get_public_exam_status() -> dict[str, Any]:
    """بررسی وضعیت لحظه‌ای بازهٔ زمانی شرکت در آزمون برای نمایش عمومی."""

    def _produce() -> dict[str, Any]:
        config = get_or_create_exam_configuration()
        now = timezone.now()
        window_state = config.resolve_window_state(now=now)

        if window_state == ExamWindowState.UPCOMING:
            status_message = "شرکت در آزمون به زودی آغاز می‌شود."
            can_participate = False
            sec_until_start = max(0, int((config.starts_at - now).total_seconds()))
            sec_until_end = max(0, int((config.ends_at - now).total_seconds()))
        elif window_state == ExamWindowState.OPEN:
            status_message = "هم‌اکنون امکان شرکت در آزمون فراهم است."
            can_participate = True
            sec_until_start = 0
            sec_until_end = max(0, int((config.ends_at - now).total_seconds()))
        else:
            status_message = "مهلت شرکت در آزمون به پایان رسید."
            can_participate = False
            sec_until_start = 0
            sec_until_end = 0

        active_questions_count = Question.objects.filter(is_active=True).count()

        return {
            "title": config.title,
            "book_title": config.book_title,
            "organizer_name": config.organizer_name,
            "description": config.description,
            "window_state": window_state,
            "window_state_label": ExamWindowState(window_state).label,
            "can_participate": can_participate,
            "status_message": status_message,
            "server_time": now.isoformat(),
            "server_time_jalali": format_jalali_datetime(now),
            "starts_at": config.starts_at.isoformat(),
            "starts_at_jalali": format_jalali_datetime(config.starts_at),
            "ends_at": config.ends_at.isoformat(),
            "ends_at_jalali": format_jalali_datetime(config.ends_at),
            "seconds_until_start": sec_until_start,
            "seconds_until_end": sec_until_end,
            "duration_seconds": config.duration_seconds,
            "questions_per_attempt": config.questions_per_attempt,
            "require_otp_before_exam": config.require_otp_before_exam,
            "active_question_bank_size": active_questions_count,
            "communication_channels": config.communication_channels,
        }

    return cache_get_or_set_swr(
        domain="exam_status",
        key_suffix="public_status",
        producer=_produce,
    )


def get_public_landing_bootstrap() -> dict[str, Any]:
    """بستهٔ یکپارچهٔ صفحهٔ اول (وضعیت آزمون + لیست کشویی ۱۷ مسجد + رنکینگ زندهٔ مساجد)."""
    from apps.mosques.selectors import (
        get_active_mosques_dropdown,
        get_mosque_leaderboard_snapshot,
    )

    now = timezone.now()
    exam_status = get_public_exam_status()
    mosques = get_active_mosques_dropdown()
    leaderboard = get_mosque_leaderboard_snapshot()
    return {
        "server_time": now.isoformat(),
        "server_time_jalali": format_jalali_datetime(now),
        "exam_status": exam_status,
        "mosques": mosques,
        "leaderboard": leaderboard,
    }


def build_active_attempt_payload(attempt: ExamAttempt) -> dict[str, Any]:
    """ساخت خروجی جلسهٔ در حال اجرای آزمون برای کاربر (تضمین ۱۰۰٪ عدم افشای گزینه صحیح)."""
    items = list(attempt.items.order_by("question_number"))
    questions_payload: list[dict[str, Any]] = []
    answered_count = 0
    next_unanswered_number: int | None = None

    for item in items:
        if item.selected_position is not None:
            answered_count += 1
        elif next_unanswered_number is None:
            next_unanswered_number = item.question_number

        safe_options = [
            {
                "position": int(opt["position"]),
                "text": str(opt["text"]),
            }
            for opt in (item.shuffled_options or [])
        ]
        questions_payload.append(
            {
                "question_number": item.question_number,
                "question_text": item.question.text,
                "chapter": item.question.chapter,
                "selected_position": item.selected_position,
                "is_answered": item.selected_position is not None,
                "options": safe_options,
            }
        )

    return {
        "attempt_id": attempt.id,
        "tracking_code": attempt.tracking_code,
        "status": attempt.status,
        "started_at": attempt.started_at.isoformat(),
        "started_at_jalali": attempt.started_at_jalali,
        "expires_at": attempt.expires_at.isoformat(),
        "remaining_seconds": attempt.remaining_seconds(),
        "duration_limit_seconds": attempt.duration_limit_seconds,
        "total_questions": attempt.total_questions,
        "answered_count": answered_count,
        "unanswered_count": max(0, attempt.total_questions - answered_count),
        "all_answered": answered_count == attempt.total_questions,
        "current_question_number": next_unanswered_number or attempt.total_questions,
        "questions": questions_payload,
    }


def build_report_card_payload(attempt: ExamAttempt) -> dict[str, Any]:
    """ساخت کارنامهٔ نهایی کاربر (فقط آمار کلی بدون افشای اینکه کدام سوال درست یا غلط بوده است)."""
    config = get_or_create_exam_configuration()
    user = attempt.user
    mosque = attempt.mosque

    thank_you_text = config.thank_you_sms_template.format(
        full_name=user.full_name,
        mosque_name=mosque.name if mosque else "",
        tracking_code=attempt.tracking_code,
    )

    return {
        "tracking_code": attempt.tracking_code,
        "receipt_signature": attempt.receipt_signature,
        "participant": {
            "id": user.id,
            "full_name": user.full_name,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "national_id_masked": user.national_id_masked,
            "phone_masked": user.phone_masked,
            "mosque_id": mosque.id if mosque else None,
            "mosque_name": mosque.name if mosque else None,
            "mosque_code": mosque.code if mosque else None,
        },
        "summary": {
            "status": attempt.status,
            "status_label": ExamAttemptStatus(attempt.status).label,
            "finished_reason": (
                "time_expired"
                if attempt.status == ExamAttemptStatus.TIMED_OUT
                else "completed_by_user"
            ),
            "total_questions": attempt.total_questions,
            "correct_count": attempt.correct_count,
            "wrong_count": attempt.wrong_count,
            "unanswered_count": attempt.unanswered_count,
            "accuracy_percent": attempt.accuracy_percent,
            "duration_seconds": attempt.duration_seconds,
            "duration_limit_seconds": attempt.duration_limit_seconds,
            "duration_display": attempt.duration_display,
            "base_score": attempt.base_score,
            "time_bonus_score": attempt.time_bonus_score,
            "total_score": attempt.total_score,
            "started_at": attempt.started_at.isoformat(),
            "started_at_jalali": attempt.started_at_jalali,
            "completed_at": attempt.completed_at.isoformat() if attempt.completed_at else None,
            "completed_at_jalali": attempt.completed_at_jalali,
        },
        "thank_you_message": thank_you_text,
        "communication_channels": config.communication_channels,
    }


def get_attempt_by_tracking_code(tracking_code: str) -> ExamAttempt:
    """واکشی کارنامهٔ پایان‌یافته با کد رهگیری برای استعلام رسید دیجیتال."""
    clean = str(tracking_code or "").strip().upper()
    attempt = (
        ExamAttempt.objects.select_related("user", "mosque")
        .filter(
            tracking_code=clean,
            status__in=[ExamAttemptStatus.COMPLETED, ExamAttemptStatus.TIMED_OUT],
        )
        .first()
    )
    if attempt is None:
        raise NotFoundDomainError(
            "کارنامه‌ای با این کد رهگیری یافت نشد.",
            code="report_card_not_found",
        )
    return attempt


def get_admin_questions_queryset(
    *,
    search: str = "",
    difficulty: str = "",
    is_active: str = "",
) -> QuerySet[Question]:
    """واکشی بانک سوالات چهارگزینه‌ای همراه با آمار پاسخگویی برای پنل ادمین."""
    qs = (
        Question.all_objects.prefetch_related("options")
        .annotate(
            times_drawn=Count("attempt_items", distinct=True),
            correct_answers_count=Count(
                "attempt_items",
                filter=Q(attempt_items__result_status=AnswerResultStatus.CORRECT),
                distinct=True,
            ),
            wrong_answers_count=Count(
                "attempt_items",
                filter=Q(attempt_items__result_status=AnswerResultStatus.WRONG),
                distinct=True,
            ),
            unanswered_count_stat=Count(
                "attempt_items",
                filter=Q(attempt_items__result_status=AnswerResultStatus.UNANSWERED),
                distinct=True,
            ),
        )
        .order_by("-created_at", "-id")
    )
    if is_active.lower() in {"true", "1"}:
        qs = qs.filter(is_active=True)
    elif is_active.lower() in {"false", "0"}:
        qs = qs.filter(is_active=False)

    if difficulty.strip():
        qs = qs.filter(difficulty=difficulty.strip())

    if search.strip():
        q = search.strip()
        qs = qs.filter(Q(text__icontains=q) | Q(chapter__icontains=q) | Q(explanation__icontains=q))
    return qs


def get_admin_question_by_id(question_id: int) -> Question:
    """واکشی یک سوال از بانک سوال با شناسه برای ادمین."""
    question = Question.all_objects.prefetch_related("options").filter(pk=question_id).first()
    if question is None:
        raise NotFoundDomainError("سوال مورد نظر در بانک سوال یافت نشد.", code="question_not_found")
    return question

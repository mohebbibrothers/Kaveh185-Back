"""سلکتورهای کاوشگر چندفیلتره شرکت‌کنندگان، آمار زنده و جزئیات پاسخنامه مخصوص ادمین."""

from __future__ import annotations

import contextlib
from datetime import date
from typing import Any

from django.db.models import Avg, Count, Max, Q, QuerySet
from django.utils import timezone

from apps.authentication.choices import UserRole
from apps.authentication.models import User
from apps.core.exceptions import NotFoundDomainError
from apps.core.jalali import parse_Flexible_birth_date
from apps.exam.choices import AnswerResultStatus, ExamAttemptStatus
from apps.exam.models import ExamAttempt, Question
from apps.mosques.models import Mosque
from apps.mosques.selectors import get_mosque_leaderboard

ORDERING_FIELD_MAP: dict[str, str] = {
    "total_score": "total_score",
    "-total_score": "-total_score",
    "correct_count": "correct_count",
    "-correct_count": "-correct_count",
    "wrong_count": "wrong_count",
    "-wrong_count": "-wrong_count",
    "unanswered_count": "unanswered_count",
    "-unanswered_count": "-unanswered_count",
    "duration_seconds": "duration_seconds",
    "-duration_seconds": "-duration_seconds",
    "birth_date": "user__birth_date",
    "-birth_date": "-user__birth_date",
    "age": "-user__birth_date",
    "-age": "user__birth_date",
    "mosque_name": "mosque__name",
    "-mosque_name": "-mosque__name",
    "completed_at": "completed_at",
    "-completed_at": "-completed_at",
    "started_at": "started_at",
    "-started_at": "-started_at",
}


def _shift_years(ref_date: date, years_back: int) -> date:
    """کم کردن تعداد مشخصی سال از تاریخ مرجع برای محاسبهٔ بازهٔ تاریخ تولد از روی سن."""
    target_year = max(1900, ref_date.year - years_back)
    try:
        return ref_date.replace(year=target_year)
    except ValueError:
        # مدیریت ۲۹ فوریه در سال کبیسه
        return ref_date.replace(year=target_year, day=28)


def get_filtered_exam_attempts_queryset(params: dict[str, Any]) -> QuerySet[ExamAttempt]:
    """فیلتر و مرتب‌سازی پویا روی کارنامه‌ها و شرکت‌کنندگان برای قرعه‌کشی حضوری و گزارش‌گیری."""
    qs = ExamAttempt.objects.select_related("user", "mosque").prefetch_related(
        "items__question__options"
    )

    # فیلتر وضعیت آزمون (پیش‌فرض: آزمون‌های پایان‌یافته `completed` + `timed_out`)
    status_filter = str(params.get("status", "finished")).strip().lower()
    if status_filter == "finished":
        qs = qs.filter(status__in=[ExamAttemptStatus.COMPLETED, ExamAttemptStatus.TIMED_OUT])
    elif status_filter in {
        ExamAttemptStatus.COMPLETED,
        ExamAttemptStatus.TIMED_OUT,
        ExamAttemptStatus.IN_PROGRESS,
    }:
        qs = qs.filter(status=status_filter)

    # فیلتر تک‌مسجد یا چندمسجد هم‌زمان (`mosque_id` یا `mosque_ids=1,2,5`)
    mosque_ids_raw = str(params.get("mosque_ids") or params.get("mosque_id") or "").strip()
    if mosque_ids_raw:
        parsed_ids = [
            int(part.strip()) for part in mosque_ids_raw.split(",") if part.strip().isdigit()
        ]
        if parsed_ids:
            qs = qs.filter(mosque_id__in=parsed_ids)

    # فیلتر تعداد پاسخ‌های درست
    if str(params.get("exact_correct", "")).strip().isdigit():
        qs = qs.filter(correct_count=int(str(params["exact_correct"]).strip()))
    if str(params.get("min_correct", "")).strip().isdigit():
        qs = qs.filter(correct_count__gte=int(str(params["min_correct"]).strip()))
    if str(params.get("max_correct", "")).strip().isdigit():
        qs = qs.filter(correct_count__lte=int(str(params["max_correct"]).strip()))

    # فیلتر تعداد پاسخ‌های غلط و بی‌پاسخ
    if str(params.get("min_wrong", "")).strip().isdigit():
        qs = qs.filter(wrong_count__gte=int(str(params["min_wrong"]).strip()))
    if str(params.get("max_wrong", "")).strip().isdigit():
        qs = qs.filter(wrong_count__lte=int(str(params["max_wrong"]).strip()))
    if str(params.get("min_unanswered", "")).strip().isdigit():
        qs = qs.filter(unanswered_count__gte=int(str(params["min_unanswered"]).strip()))
    if str(params.get("max_unanswered", "")).strip().isdigit():
        qs = qs.filter(unanswered_count__lte=int(str(params["max_unanswered"]).strip()))

    # فیلتر بازه امتیاز کل
    for key, lookup in (("min_score", "total_score__gte"), ("max_score", "total_score__lte")):
        raw_val = str(params.get(key, "")).strip()
        if raw_val:
            with contextlib.suppress(ValueError):
                qs = qs.filter(**{lookup: float(raw_val)})

    # فیلتر بازه مدت زمان پاسخگویی (ثانیه)
    if str(params.get("min_duration", "")).strip().isdigit():
        qs = qs.filter(duration_seconds__gte=int(str(params["min_duration"]).strip()))
    if str(params.get("max_duration", "")).strip().isdigit():
        qs = qs.filter(duration_seconds__lte=int(str(params["max_duration"]).strip()))

    # فیلتر بازه سن شرکت‌کننده (سال)
    today = timezone.localdate()
    if str(params.get("min_age", "")).strip().isdigit():
        min_age = int(str(params["min_age"]).strip())
        latest_birth = _shift_years(today, min_age)
        qs = qs.filter(user__birth_date__lte=latest_birth)
    if str(params.get("max_age", "")).strip().isdigit():
        max_age = int(str(params["max_age"]).strip())
        earliest_birth = _shift_years(today, max_age + 1)
        qs = qs.filter(user__birth_date__gt=earliest_birth)

    # فیلتر بازه تاریخ تولد (شمسی یا میلادی)
    birth_from_raw = str(params.get("birth_date_from", "")).strip()
    if birth_from_raw:
        with contextlib.suppress(ValueError):
            qs = qs.filter(user__birth_date__gte=parse_Flexible_birth_date(birth_from_raw))
    birth_to_raw = str(params.get("birth_date_to", "")).strip()
    if birth_to_raw:
        with contextlib.suppress(ValueError):
            qs = qs.filter(user__birth_date__lte=parse_Flexible_birth_date(birth_to_raw))

    # جستجوی متنی روی نام، نام خانوادگی، موبایل، کد ملی یا کد رهگیری
    search = str(params.get("search", "")).strip()
    if search:
        qs = qs.filter(
            Q(tracking_code__icontains=search)
            | Q(user__first_name__icontains=search)
            | Q(user__last_name__icontains=search)
            | Q(user__phone_number__icontains=search)
            | Q(mosque__name__icontains=search)
        )

    # مرتب‌سازی چندستونه پویا
    ordering_raw = str(params.get("ordering", "")).strip()
    order_fields: list[str] = []
    if ordering_raw:
        for token in ordering_raw.split(","):
            clean_token = token.strip()
            if clean_token in ORDERING_FIELD_MAP:
                order_fields.append(ORDERING_FIELD_MAP[clean_token])

    if not order_fields:
        order_fields = ["-total_score", "-correct_count", "duration_seconds", "completed_at", "id"]
    else:
        order_fields.append("id")

    return qs.order_by(*order_fields)


def serialize_attempt_answer_items_for_admin(attempt: ExamAttempt) -> list[dict[str, Any]]:
    """ساخت ریز جزئیات ۵ سوال و گزینه‌های انتخابی شرکت‌کننده مخصوص پنل ادمین و خروجی اکسل."""
    items = sorted(attempt.items.all(), key=lambda x: x.question_number)
    result: list[dict[str, Any]] = []

    for item in items:
        shuffled_opts = list(item.shuffled_options or [])
        selected_text = None
        if item.selected_position is not None:
            matched = next(
                (o for o in shuffled_opts if int(o["position"]) == int(item.selected_position)),
                None,
            )
            if matched:
                selected_text = str(matched["text"])

        correct_opt = next(
            (o for o in item.question.options.all() if o.is_correct),
            None,
        )
        correct_text = correct_opt.text if correct_opt is not None else ""

        result.append(
            {
                "question_number": item.question_number,
                "question_id": item.question_id,
                "question_text": item.question.text,
                "chapter": item.question.chapter,
                "selected_position": item.selected_position,
                "selected_option_id": item.selected_option_id,
                "selected_option_text": selected_text,
                "correct_option_text": correct_text,
                "result_status": item.result_status,
                "result_status_label": AnswerResultStatus(item.result_status).label,
                "shuffled_options": shuffled_opts,
                "answered_at": item.answered_at.isoformat() if item.answered_at else None,
            }
        )
    return result


def serialize_admin_participant_row(
    attempt: ExamAttempt,
    *,
    rank: int | None = None,
    include_answers: bool = True,
) -> dict[str, Any]:
    """سریالایز کامل اطلاعات هویتی، خلاصه کارنامه و ریز پاسخ‌های ۵ سوال برای ادمین."""
    user = attempt.user
    mosque = attempt.mosque

    payload: dict[str, Any] = {
        "rank": rank,
        "attempt_id": attempt.id,
        "tracking_code": attempt.tracking_code,
        "receipt_signature": attempt.receipt_signature,
        "user": {
            "id": user.id,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "full_name": user.full_name,
            "phone_number": user.phone_number,
            "national_id": user.national_id,
            "birth_date": user.birth_date.isoformat() if user.birth_date else None,
            "birth_date_jalali": user.birth_date_jalali,
            "age_years": user.age_years,
            "is_phone_verified": user.is_phone_verified,
        },
        "mosque": {
            "id": mosque.id if mosque else None,
            "code": mosque.code if mosque else None,
            "name": mosque.name if mosque else None,
            "neighborhood": mosque.neighborhood if mosque else None,
        },
        "exam": {
            "status": attempt.status,
            "status_label": ExamAttemptStatus(attempt.status).label,
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
            "started_ip": attempt.started_ip,
            "completed_ip": attempt.completed_ip,
            "thank_you_sms_sent": attempt.thank_you_sms_sent,
        },
    }
    if include_answers:
        payload["answers"] = serialize_attempt_answer_items_for_admin(attempt)
    return payload


def get_admin_participant_detail(*, user_id: int) -> dict[str, Any]:
    """واکشی پروندهٔ کامل یک شرکت‌کننده به همراه ریز سوالات و گزینه‌های انتخابی برای ادمین."""
    user = User.objects.select_related("mosque").filter(pk=user_id).first()
    if user is None:
        raise NotFoundDomainError("شرکت‌کنندهٔ مورد نظر یافت نشد.", code="participant_not_found")

    attempt = (
        ExamAttempt.objects.select_related("user", "mosque")
        .prefetch_related("items__question__options")
        .filter(user=user)
        .first()
    )
    if attempt is None:
        return {
            "has_exam_attempt": False,
            "user": {
                "id": user.id,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "full_name": user.full_name,
                "phone_number": user.phone_number,
                "national_id": user.national_id,
                "birth_date": user.birth_date.isoformat() if user.birth_date else None,
                "birth_date_jalali": user.birth_date_jalali,
                "age_years": user.age_years,
                "mosque_id": user.mosque_id,
                "mosque_name": user.mosque.name if user.mosque else None,
            },
            "exam_attempt": None,
        }

    return {
        "has_exam_attempt": True,
        "participant_report": serialize_admin_participant_row(attempt, include_answers=True),
    }


def get_live_analytics_dashboard() -> dict[str, Any]:
    """تولید داشبورد جامع آماری زنده برای پنل فرماندهی ادمین و گزارش‌گیری."""
    total_registered = User.objects.filter(role=UserRole.PARTICIPANT, is_active=True).count()
    all_attempts = ExamAttempt.objects.all()
    finished_attempts = all_attempts.filter(
        status__in=[ExamAttemptStatus.COMPLETED, ExamAttemptStatus.TIMED_OUT]
    )

    total_started = all_attempts.count()
    total_completed = all_attempts.filter(status=ExamAttemptStatus.COMPLETED).count()
    total_timed_out = all_attempts.filter(status=ExamAttemptStatus.TIMED_OUT).count()
    total_in_progress = all_attempts.filter(status=ExamAttemptStatus.IN_PROGRESS).count()
    total_finished = total_completed + total_timed_out

    agg = finished_attempts.aggregate(
        avg_correct=Avg("correct_count"),
        avg_score=Avg("total_score"),
        avg_duration=Avg("duration_seconds"),
        max_score=Max("total_score"),
    )

    perfect_score_count = finished_attempts.filter(
        correct_count=5,
    ).count()

    # توزیع تعداد پاسخ درست (۰ تا ۵)
    score_dist: dict[str, int] = {str(k): 0 for k in range(6)}
    for row in finished_attempts.values("correct_count").annotate(cnt=Count("id")):
        c_key = str(row["correct_count"])
        score_dist[c_key] = int(row["cnt"])

    # توزیع رده‌های سنی شرکت‌کنندگان آزمون‌داده
    age_buckets: dict[str, dict[str, Any]] = {
        "under_18": {"label": "نوجوانان (زیر ۱۸ سال)", "count": 0},
        "18_to_25": {"label": "جوانان (۱۸ تا ۲۵ سال)", "count": 0},
        "26_to_35": {"label": "بزرگسالان جوان (۲۶ تا ۳۵ سال)", "count": 0},
        "36_to_50": {"label": "میان‌سالان (۳۶ تا ۵۰ سال)", "count": 0},
        "above_50": {"label": "پیشکسوتان (بالای ۵۰ سال)", "count": 0},
    }
    for att in finished_attempts.select_related("user"):
        age = att.user.age_years
        if age is None:
            continue
        if age < 18:
            age_buckets["under_18"]["count"] += 1
        elif age <= 25:
            age_buckets["18_to_25"]["count"] += 1
        elif age <= 35:
            age_buckets["26_to_35"]["count"] += 1
        elif age <= 50:
            age_buckets["36_to_50"]["count"] += 1
        else:
            age_buckets["above_50"]["count"] += 1

    # تحلیل آمار مساجد
    mosque_stats_map: dict[int, dict[str, Any]] = {}
    for m_row in finished_attempts.values("mosque_id").annotate(
        finished_cnt=Count("id"),
        avg_score=Avg("total_score"),
        avg_correct=Avg("correct_count"),
        avg_dur=Avg("duration_seconds"),
        perfect_cnt=Count("id", filter=Q(correct_count=5)),
    ):
        mosque_stats_map[int(m_row["mosque_id"])] = m_row

    leaderboard = get_mosque_leaderboard()
    mosques_analytics: list[dict[str, Any]] = []
    for entry in leaderboard["leaderboard"]:
        mid = int(entry.get("mosque_id") or entry.get("id") or 0)
        st = mosque_stats_map.get(mid, {})
        mosques_analytics.append(
            {
                **entry,
                "id": mid,
                "mosque_id": mid,
                "registered_participants_count": int(entry.get("registered_users_count") or 0),
                "average_total_score": round(float(st.get("avg_score") or 0.0), 2),
                "average_correct_count": round(float(st.get("avg_correct") or 0.0), 2),
                "average_duration_seconds": round(float(st.get("avg_dur") or 0.0), 1),
                "perfect_5_of_5_count": int(st.get("perfect_cnt") or 0),
            }
        )

    # شاخص دشواری بانک سوالات
    question_analytics: list[dict[str, Any]] = []
    questions_qs = Question.all_objects.annotate(
        drawn_cnt=Count("attempt_items"),
        correct_cnt=Count(
            "attempt_items",
            filter=Q(attempt_items__result_status=AnswerResultStatus.CORRECT),
        ),
        wrong_cnt=Count(
            "attempt_items",
            filter=Q(attempt_items__result_status=AnswerResultStatus.WRONG),
        ),
        unanswered_cnt=Count(
            "attempt_items",
            filter=Q(attempt_items__result_status=AnswerResultStatus.UNANSWERED),
        ),
    ).order_by("id")

    for q in questions_qs:
        drawn = int(q.drawn_cnt or 0)
        corr = int(q.correct_cnt or 0)
        acc = round((corr / drawn) * 100.0, 1) if drawn > 0 else 0.0
        question_analytics.append(
            {
                "question_id": q.id,
                "text": q.text,
                "chapter": q.chapter,
                "difficulty": q.difficulty,
                "is_active": q.is_active,
                "times_drawn": drawn,
                "correct_count": corr,
                "wrong_count": int(q.wrong_cnt or 0),
                "unanswered_count": int(q.unanswered_cnt or 0),
                "accuracy_percent": acc,
            }
        )

    return {
        "overview": {
            "total_registered_participants": total_registered,
            "total_started_exams": total_started,
            "total_completed_exams": total_completed,
            "total_timed_out_exams": total_timed_out,
            "total_in_progress_exams": total_in_progress,
            "total_finished_exams": total_finished,
            "completion_rate_percent": (
                round((total_finished / total_registered) * 100.0, 2)
                if total_registered > 0
                else 0.0
            ),
            "perfect_score_5_of_5_count": perfect_score_count,
            "average_correct_answers": round(float(agg["avg_correct"] or 0.0), 2),
            "average_total_score": round(float(agg["avg_score"] or 0.0), 2),
            "average_duration_seconds": round(float(agg["avg_duration"] or 0.0), 1),
            "highest_total_score": round(float(agg["max_score"] or 0.0), 2),
            "active_mosques_count": Mosque.objects.filter(is_active=True).count(),
        },
        "correct_count_distribution": score_dist,
        "age_groups_distribution": age_buckets,
        "mosques_ranking_and_analytics": mosques_analytics,
        "question_bank_analytics": question_analytics,
    }

"""سرویس‌های موتور آزمون، تصادفی‌سازی دوگانه، ثبت پاسخ، صدور کارنامه و بازتصحیح خودکار."""

from __future__ import annotations

import secrets
from datetime import timedelta
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.audit_logs.choices import AuditAction
from apps.audit_logs.services import record_audit_log
from apps.authentication.choices import RiskSeverity, RiskSignalType
from apps.authentication.models import User
from apps.authentication.services import record_risk_signal
from apps.core.cache_invalidation import invalidate_domain_cache
from apps.core.client_ip import get_client_ip
from apps.core.crypto import blind_index
from apps.core.exceptions import (
    ConflictDomainError,
    ExamWindowClosedError,
    NotFoundDomainError,
    ValidationDomainError,
)
from apps.core.metrics import EXAM_ATTEMPTS_FINALIZED_TOTAL, EXAM_ATTEMPTS_STARTED_TOTAL
from apps.core.outbox import enqueue_outbox
from apps.mosques.services import increment_mosque_completed_exam_count

from .choices import (
    DEFAULT_SAMPLE_QUESTIONS,
    AnswerResultStatus,
    ExamAttemptStatus,
    ExamWindowState,
)
from .models import (
    ExamAttempt,
    ExamAttemptItem,
    ExamConfiguration,
    Question,
    QuestionOption,
)
from .scoring import compute_exam_score
from .selectors import get_or_create_exam_configuration
from .validators import validate_question_options_payload

_SYS_RANDOM = secrets.SystemRandom()
NETWORK_GRACE_SECONDS = 2


def _generate_unique_tracking_code() -> str:
    """تولید کد رهگیری یکتای کارنامه با پیشوند `KV185-`."""
    alphabet = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
    for _ in range(20):
        suffix = "".join(_SYS_RANDOM.choice(alphabet) for _ in range(8))
        code = f"KV185-{suffix}"
        if not ExamAttempt.all_objects.filter(tracking_code=code).exists():
            return code
    return f"KV185-{secrets.token_hex(5).upper()}"


def _compute_receipt_signature(attempt: ExamAttempt) -> str:
    """تولید امضای دیجیتال HMAC-SHA256 برای رسید کارنامه."""
    raw = (
        f"{attempt.tracking_code}:{attempt.user_id}:{attempt.mosque_id}:"
        f"{attempt.correct_count}:{attempt.wrong_count}:{attempt.unanswered_count}:"
        f"{attempt.duration_seconds}:{attempt.total_score}"
    )
    return blind_index(raw, purpose="exam_receipt")


def _evaluate_and_finalize_attempt(
    *,
    attempt: ExamAttempt,
    final_status: Any,
    config: ExamConfiguration,
    now: Any = None,
    request: Any = None,
) -> ExamAttempt:
    """محاسبهٔ تعداد درست/غلط/بی‌پاسخ، امتیاز، آمار مسجد و ارسال پیامک تشکر در یک تراکنش."""
    ref_now = now or timezone.now()
    items = list(
        ExamAttemptItem.objects.select_related("question")
        .prefetch_related("question__options")
        .filter(attempt=attempt)
        .order_by("question_number")
    )

    correct_cnt = 0
    wrong_cnt = 0
    unanswered_cnt = 0

    for item in items:
        if item.selected_position is None or item.selected_option_id is None:
            item.result_status = AnswerResultStatus.UNANSWERED
            unanswered_cnt += 1
        else:
            correct_opt = next(
                (o for o in item.question.options.all() if o.is_correct),
                None,
            )
            if correct_opt is not None and int(item.selected_option_id) == int(correct_opt.id):
                item.result_status = AnswerResultStatus.CORRECT
                correct_cnt += 1
            else:
                item.result_status = AnswerResultStatus.WRONG
                wrong_cnt += 1
        item.save(update_fields=["result_status", "updated_at"])

    if final_status == ExamAttemptStatus.TIMED_OUT:
        elapsed = attempt.duration_limit_seconds
    else:
        raw_elapsed = int((ref_now - attempt.started_at).total_seconds())
        elapsed = max(1, min(raw_elapsed, attempt.duration_limit_seconds))

    score_breakdown = compute_exam_score(
        correct_count=correct_cnt,
        wrong_count=wrong_cnt,
        total_questions=attempt.total_questions,
        duration_seconds=elapsed,
        duration_limit_seconds=attempt.duration_limit_seconds,
        points_per_correct=config.points_per_correct,
        points_per_wrong=config.points_per_wrong,
        max_time_bonus=config.max_time_bonus,
    )

    attempt.status = final_status
    attempt.completed_at = ref_now
    attempt.duration_seconds = elapsed
    attempt.correct_count = correct_cnt
    attempt.wrong_count = wrong_cnt
    attempt.unanswered_count = unanswered_cnt
    attempt.base_score = score_breakdown.base_score
    attempt.time_bonus_score = score_breakdown.time_bonus_score
    attempt.total_score = score_breakdown.total_score
    attempt.accuracy_percent = score_breakdown.accuracy_percent
    if request is not None:
        attempt.completed_ip = get_client_ip(request)
    attempt.receipt_signature = _compute_receipt_signature(attempt)

    # تشخیص پاسخ‌گویی غیرطبیعی فوق‌سریع (مثلاً ۵ سوال در کمتر از ۴ ثانیه)
    if (
        final_status == ExamAttemptStatus.COMPLETED
        and attempt.total_questions >= 5
        and elapsed <= 3
    ):
        record_risk_signal(
            user=attempt.user,
            signal_type=RiskSignalType.RAPID_ANSWERING,
            severity=RiskSeverity.MEDIUM,
            request=request,
            details={"duration_seconds": elapsed, "correct_count": correct_cnt},
        )

    # افزایش آمار مشارکت مسجد و ارسال پیامک تشکر
    increment_mosque_completed_exam_count(attempt.mosque_id)

    if config.thank_you_sms_enabled and not attempt.thank_you_sms_sent:
        user = attempt.user
        mosque = attempt.mosque
        thank_you_text = config.thank_you_sms_template.format(
            full_name=user.full_name,
            mosque_name=mosque.name if mosque else "",
            tracking_code=attempt.tracking_code,
        )
        enqueue_outbox(
            topic="sms.exam_thank_you",
            recipient=user.phone_number,
            payload={
                "phone_number": user.phone_number,
                "full_name": user.full_name,
                "mosque_name": mosque.name if mosque else "",
                "tracking_code": attempt.tracking_code,
                "message_text": thank_you_text,
                "channels": config.communication_channels,
            },
        )
        attempt.thank_you_sms_sent = True

    attempt.save()

    EXAM_ATTEMPTS_FINALIZED_TOTAL.labels(status=final_status).inc()
    audit_action = (
        AuditAction.EXAM_TIMED_OUT
        if final_status == ExamAttemptStatus.TIMED_OUT
        else AuditAction.EXAM_COMPLETED
    )
    record_audit_log(
        action=audit_action,
        resource_type="exam_attempt",
        resource_id=attempt.pk,
        user=attempt.user,
        request=request,
        extra_data={
            "tracking_code": attempt.tracking_code,
            "mosque_id": attempt.mosque_id,
            "correct_count": correct_cnt,
            "wrong_count": wrong_cnt,
            "unanswered_count": unanswered_cnt,
            "duration_seconds": elapsed,
            "total_score": attempt.total_score,
        },
    )
    return attempt


def start_or_resume_exam(*, user: User, request: Any = None) -> tuple[ExamAttempt, bool]:
    """شروع آزمون ۵ سواله جدید با تصادفی‌سازی دوگانه (سوالات + گزینه‌ها) یا ادامهٔ آزمون باز."""
    if not user.mosque_id or not user.birth_date or not user.national_id:
        raise ValidationDomainError(
            "برای ورود به آزمون ابتدا اطلاعات هویتی و مسجد خود را تکمیل کنید.",
            code="incomplete_profile",
        )

    now = timezone.now()
    config = get_or_create_exam_configuration()

    with transaction.atomic():
        locked_user = User.objects.select_for_update().get(pk=user.pk)
        existing = (
            ExamAttempt.objects.select_for_update()
            .select_related("user", "mosque")
            .prefetch_related("items__question")
            .filter(user=locked_user)
            .first()
        )

        if existing is not None:
            if existing.status in {ExamAttemptStatus.COMPLETED, ExamAttemptStatus.TIMED_OUT}:
                raise ConflictDomainError(
                    "شما قبلاً در این آزمون شرکت کرده‌اید و هر نفر فقط یک بار مجاز به شرکت در آزمون است.",
                    code="exam_already_completed",
                    errors={"tracking_code": existing.tracking_code},
                )
            # آزمون در حال اجراست: اگر تایمرش تمام شده، خودکار ببند
            if now >= existing.expires_at:
                _evaluate_and_finalize_attempt(
                    attempt=existing,
                    final_status=ExamAttemptStatus.TIMED_OUT,
                    config=config,
                    now=now,
                    request=request,
                )
                raise ConflictDomainError(
                    "مهلت زمانی آزمون شما به پایان رسید و کارنامهٔ شما صادر شد.",
                    code="exam_time_expired",
                    errors={"tracking_code": existing.tracking_code},
                )
            return existing, False

        # کاربر هنوز آزمونی شروع نکرده است؛ بررسی باز بودن پنجرهٔ زمانی آزمون
        window_state = config.resolve_window_state(now=now)
        if window_state == ExamWindowState.UPCOMING:
            raise ExamWindowClosedError(
                "شرکت در آزمون به زودی آغاز می‌شود.",
                code="exam_not_started_yet",
                errors={
                    "window_state": ExamWindowState.UPCOMING,
                    "starts_at": config.starts_at.isoformat(),
                },
            )
        if window_state == ExamWindowState.ENDED:
            raise ExamWindowClosedError(
                "مهلت شرکت در آزمون به پایان رسید.",
                code="exam_window_ended",
                errors={
                    "window_state": ExamWindowState.ENDED,
                    "ends_at": config.ends_at.isoformat(),
                },
            )

        required_q_count = int(config.questions_per_attempt)
        eligible_questions = list(
            Question.objects.filter(is_active=True).prefetch_related("options")
        )
        valid_questions = [q for q in eligible_questions if len(q.options.all()) == 4]

        if len(valid_questions) < required_q_count:
            raise ConflictDomainError(
                f"بانک سوال هنوز تکمیل نشده است (حداقل {required_q_count} سوال چهارگزینه‌ای فعال نیاز است).",
                code="insufficient_question_bank",
            )

        # ۱) انتخاب تصادفی ۵ سوال از بانک سوال با آنتروپی سیستم‌عامل
        selected_questions = _SYS_RANDOM.sample(valid_questions, required_q_count)

        ip_addr = get_client_ip(request) if request is not None else ""
        meta = getattr(request, "META", {}) if request is not None else {}
        user_agent = str(meta.get("HTTP_USER_AGENT", ""))[:300]

        attempt = ExamAttempt.objects.create(
            user=locked_user,
            mosque_id=locked_user.mosque_id,
            tracking_code=_generate_unique_tracking_code(),
            status=ExamAttemptStatus.IN_PROGRESS,
            started_at=now,
            expires_at=now + timedelta(seconds=int(config.duration_seconds)),
            duration_limit_seconds=int(config.duration_seconds),
            total_questions=required_q_count,
            unanswered_count=required_q_count,
            started_ip=ip_addr,
            user_agent=user_agent,
        )

        # ۲) جابه‌جایی تصادفی گزینه‌های ۱ تا ۴ برای هر سوال
        for q_idx, question in enumerate(selected_questions, start=1):
            raw_options = list(question.options.all())
            _SYS_RANDOM.shuffle(raw_options)
            shuffled_mapping = [
                {
                    "position": pos,
                    "option_id": opt.id,
                    "text": opt.text,
                }
                for pos, opt in enumerate(raw_options, start=1)
            ]
            ExamAttemptItem.objects.create(
                attempt=attempt,
                question=question,
                question_number=q_idx,
                shuffled_options=shuffled_mapping,
                result_status=AnswerResultStatus.UNANSWERED,
            )

        EXAM_ATTEMPTS_STARTED_TOTAL.inc()
        record_audit_log(
            action=AuditAction.EXAM_STARTED,
            resource_type="exam_attempt",
            resource_id=attempt.pk,
            user=locked_user,
            request=request,
            extra_data={
                "tracking_code": attempt.tracking_code,
                "mosque_id": locked_user.mosque_id,
                "questions_count": required_q_count,
                "duration_seconds": config.duration_seconds,
            },
        )
        return attempt, True


def get_current_active_attempt_or_finalize(*, user: User, request: Any = None) -> ExamAttempt:
    """واکشی جلسهٔ آزمون کاربر؛ اگر زمانش تمام شده باشد به‌صورت خودکار نهایی و کارنامه صادر می‌شود."""
    now = timezone.now()
    config = get_or_create_exam_configuration()

    with transaction.atomic():
        attempt = (
            ExamAttempt.objects.select_for_update()
            .select_related("user", "mosque")
            .prefetch_related("items__question")
            .filter(user=user)
            .first()
        )
        if attempt is None:
            raise NotFoundDomainError(
                "شما هنوز آزمونی را شروع نکرده‌اید.",
                code="exam_attempt_not_found",
            )
        if attempt.status == ExamAttemptStatus.IN_PROGRESS and now >= attempt.expires_at:
            _evaluate_and_finalize_attempt(
                attempt=attempt,
                final_status=ExamAttemptStatus.TIMED_OUT,
                config=config,
                now=now,
                request=request,
            )
        return attempt


def submit_question_answer(
    *,
    user: User,
    question_number: int,
    selected_position: int,
    request: Any = None,
) -> ExamAttempt:
    """ثبت پاسخ یک سوال در حین آزمون (بدون امکان رد کردن سوال قبلی و بدون افشای درست/غلط بودن)."""
    if selected_position not in {1, 2, 3, 4}:
        raise ValidationDomainError(
            "گزینهٔ انتخابی باید عددی بین ۱ تا ۴ باشد.",
            code="invalid_selected_position",
        )

    now = timezone.now()
    config = get_or_create_exam_configuration()

    with transaction.atomic():
        attempt = (
            ExamAttempt.objects.select_for_update()
            .select_related("user", "mosque")
            .filter(user=user)
            .first()
        )
        if attempt is None:
            raise NotFoundDomainError(
                "ابتدا دکمهٔ ورود به آزمون را بزنید.",
                code="exam_attempt_not_found",
            )
        if attempt.status in {ExamAttemptStatus.COMPLETED, ExamAttemptStatus.TIMED_OUT}:
            raise ConflictDomainError(
                "آزمون شما به پایان رسیده است و امکان تغییر پاسخ وجود ندارد.",
                code="exam_already_finished",
                errors={"tracking_code": attempt.tracking_code},
            )

        # بررسی مهلت زمانی سرور (با ۲ ثانیه تحمل تاخیر شبکه)
        if now > attempt.expires_at + timedelta(seconds=NETWORK_GRACE_SECONDS):
            _evaluate_and_finalize_attempt(
                attempt=attempt,
                final_status=ExamAttemptStatus.TIMED_OUT,
                config=config,
                now=now,
                request=request,
            )
            raise ConflictDomainError(
                "مهلت زمانی آزمون شما به پایان رسید و کارنامه با پاسخ‌های ثبت‌شده صادر گردید.",
                code="exam_time_expired",
                errors={"tracking_code": attempt.tracking_code},
            )

        items = list(
            ExamAttemptItem.objects.select_for_update()
            .select_related("question")
            .filter(attempt=attempt)
            .order_by("question_number")
        )
        target_item = next((i for i in items if i.question_number == question_number), None)
        if target_item is None:
            raise ValidationDomainError(
                f"سوال شمارهٔ {question_number} در این آزمون وجود ندارد.",
                code="invalid_question_number",
            )

        # قانون عدم امکان رد کردن (No-Skip Rule): برای پاسخ به سوال k باید سوالات 1 تا k-1 پاسخ داده شده باشند
        unanswered_prior = [
            i.question_number
            for i in items
            if i.question_number < question_number and i.selected_position is None
        ]
        if unanswered_prior:
            raise ValidationDomainError(
                f"امکان رد کردن سوال وجود ندارد. لطفاً ابتدا به سوال شمارهٔ {unanswered_prior[0]} پاسخ دهید.",
                code="cannot_skip_question",
                errors={"unanswered_prior_questions": unanswered_prior},
            )

        matched_opt = next(
            (
                opt
                for opt in (target_item.shuffled_options or [])
                if int(opt["position"]) == int(selected_position)
            ),
            None,
        )
        if matched_opt is None:
            raise ValidationDomainError(
                "گزینهٔ انتخابی در چیدمان این سوال یافت نشد.",
                code="invalid_selected_position",
            )

        target_item.selected_position = int(selected_position)
        target_item.selected_option_id = int(matched_opt["option_id"])
        target_item.answered_at = now
        target_item.save(
            update_fields=[
                "selected_position",
                "selected_option_id",
                "answered_at",
                "updated_at",
            ]
        )

        if request is not None:
            current_ip = get_client_ip(request)
            if attempt.started_ip and current_ip and attempt.started_ip != current_ip:
                record_risk_signal(
                    user=user,
                    signal_type=RiskSignalType.IP_CHANGE_DURING_EXAM,
                    severity=RiskSeverity.LOW,
                    request=request,
                    details={"started_ip": attempt.started_ip, "current_ip": current_ip},
                )

        return attempt


def finish_exam_attempt(
    *,
    user: User,
    answers: list[dict[str, int]] | None = None,
    request: Any = None,
) -> ExamAttempt:
    """پایان دادن به آزمون و صدور کارنامه.

    قواعد کلیدی:
    ۱) اگر زمان آزمون هنوز تمام نشده باشد (`now < expires_at`)، کاربر موظف است به هر ۵ سوال
       پاسخ داده باشد و نمی‌تواند سوالی را بی‌پاسخ رها کند (`400 incomplete_exam_answers`).
    ۲) اگر زمان آزمون تمام شده باشد (`now >= expires_at`)، آزمون با وضعیت `TIMED_OUT` بسته شده
       و سوالات باقی‌مانده به‌عنوان `بی‌پاسخ (unanswered)` ثبت می‌شوند.
    """
    now = timezone.now()
    config = get_or_create_exam_configuration()

    with transaction.atomic():
        attempt = (
            ExamAttempt.objects.select_for_update()
            .select_related("user", "mosque")
            .filter(user=user)
            .first()
        )
        if attempt is None:
            raise NotFoundDomainError(
                "شما هنوز آزمونی را شروع نکرده‌اید.",
                code="exam_attempt_not_found",
            )
        if attempt.status in {ExamAttemptStatus.COMPLETED, ExamAttemptStatus.TIMED_OUT}:
            return attempt

        items = list(
            ExamAttemptItem.objects.select_for_update()
            .select_related("question")
            .filter(attempt=attempt)
            .order_by("question_number")
        )
        items_by_num = {item.question_number: item for item in items}

        is_expired = now > (attempt.expires_at + timedelta(seconds=NETWORK_GRACE_SECONDS))

        # اگر پاسخ‌هایی همراه با درخواست پایان ارسال شده و هنوز زمان باقی است، آن‌ها را ثبت کن
        if answers and not is_expired:
            sorted_answers = sorted(answers, key=lambda a: int(a.get("question_number", 0)))
            for ans in sorted_answers:
                q_num = int(ans.get("question_number", 0))
                pos = int(ans.get("selected_position", 0))
                if q_num not in items_by_num or pos not in {1, 2, 3, 4}:
                    raise ValidationDomainError(
                        "شماره سوال یا گزینه ارسالی معتبر نیست.",
                        code="invalid_answer_payload",
                    )
                item = items_by_num[q_num]
                matched_opt = next(
                    (opt for opt in (item.shuffled_options or []) if int(opt["position"]) == pos),
                    None,
                )
                if matched_opt is not None:
                    item.selected_position = pos
                    item.selected_option_id = int(matched_opt["option_id"])
                    item.answered_at = item.answered_at or now
                    item.save(
                        update_fields=[
                            "selected_position",
                            "selected_option_id",
                            "answered_at",
                            "updated_at",
                        ]
                    )

        if is_expired:
            return _evaluate_and_finalize_attempt(
                attempt=attempt,
                final_status=ExamAttemptStatus.TIMED_OUT,
                config=config,
                now=now,
                request=request,
            )

        # زمان هنوز باقی است: بررسی اینکه هیچ سوالی بی‌پاسخ نمانده باشد
        unanswered_numbers = [
            item.question_number for item in items if item.selected_position is None
        ]
        if unanswered_numbers:
            raise ValidationDomainError(
                "شما باید به هر ۵ سوال آزمون پاسخ دهید و امکان رد کردن سوال تا پیش از پایان مهلت زمانی وجود ندارد.",
                code="incomplete_exam_answers",
                errors={"unanswered_question_numbers": unanswered_numbers},
            )

        return _evaluate_and_finalize_attempt(
            attempt=attempt,
            final_status=ExamAttemptStatus.COMPLETED,
            config=config,
            now=now,
            request=request,
        )


def update_exam_configuration(
    *,
    data: dict[str, Any],
    request: Any = None,
) -> ExamConfiguration:
    """به‌روزرسانی تنظیمات زندهٔ آزمون (زمان، تعداد سوال، فرمول امتیاز، پیامک و...) توسط ادمین."""
    with transaction.atomic():
        config = get_or_create_exam_configuration()
        changes: dict[str, Any] = {}
        editable_fields = (
            "title",
            "book_title",
            "organizer_name",
            "description",
            "starts_at",
            "ends_at",
            "is_manually_open",
            "duration_seconds",
            "questions_per_attempt",
            "require_otp_before_exam",
            "points_per_correct",
            "points_per_wrong",
            "max_time_bonus",
            "thank_you_sms_enabled",
            "thank_you_sms_template",
            "communication_channels",
        )
        for field in editable_fields:
            if field in data:
                new_val = data[field]
                old_val = getattr(config, field)
                if new_val != old_val:
                    changes[field] = {"old": str(old_val), "new": str(new_val)}
                    setattr(config, field, new_val)

        if config.ends_at <= config.starts_at:
            raise ValidationDomainError(
                "زمان پایان مهلت آزمون باید بعد از زمان شروع آن باشد.",
                code="invalid_exam_window_range",
            )
        if int(config.duration_seconds) < 30:
            raise ValidationDomainError(
                "مدت زمان آزمون نباید کمتر از ۳۰ ثانیه باشد.",
                code="invalid_duration_seconds",
            )
        if int(config.questions_per_attempt) < 1 or int(config.questions_per_attempt) > 50:
            raise ValidationDomainError(
                "تعداد سوالات هر آزمون باید بین ۱ تا ۵۰ باشد.",
                code="invalid_questions_per_attempt",
            )

        config.policy_version += 1
        config.save()

        record_audit_log(
            action=AuditAction.EXAM_CONFIG_UPDATED,
            resource_type="exam_configuration",
            resource_id=config.pk,
            request=request,
            changes=changes,
            extra_data={"policy_version": config.policy_version},
        )
        invalidate_domain_cache("exam_status", reason=f"exam.config.v{config.policy_version}")
        return config


def create_question_with_options(
    *,
    data: dict[str, Any],
    created_by: User | None = None,
    request: Any = None,
) -> Question:
    """ایجاد یک سوال چهارگزینه‌ای جدید در بانک سوال توسط ادمین."""
    validated_options = validate_question_options_payload(list(data.get("options") or []))
    text = str(data.get("text", "")).strip()
    if not text:
        raise ValidationDomainError("متن صورت سوال نمی‌تواند خالی باشد.", code="empty_question_text")

    with transaction.atomic():
        question = Question.all_objects.create(
            text=text,
            chapter=str(data.get("chapter", "")).strip(),
            difficulty=str(data.get("difficulty", "medium")).strip(),
            explanation=str(data.get("explanation", "")).strip(),
            is_active=bool(data.get("is_active", True)),
            created_by=created_by,
        )
        for opt in validated_options:
            QuestionOption.objects.create(
                question=question,
                option_number=int(opt["option_number"]),
                text=str(opt["text"]),
                is_correct=bool(opt["is_correct"]),
            )
        record_audit_log(
            action=AuditAction.QUESTION_CREATED,
            resource_type="question",
            resource_id=question.pk,
            user=created_by,
            request=request,
            changes={"text": question.text[:120]},
        )
        invalidate_domain_cache(
            "exam_status", reason=f"question.created:{question.pk}", record_outbox=False
        )
        return question


def update_question_with_options(
    *,
    question: Question,
    data: dict[str, Any],
    request: Any = None,
    auto_regrade: bool = True,
) -> Question:
    """ویرایش متن، گزینه‌ها یا کلید صحیح سوال توسط ادمین همراه با بازتصحیح خودکار کارنامه‌ها."""
    changes: dict[str, Any] = {}
    key_changed = False

    with transaction.atomic():
        for field in ("text", "chapter", "difficulty", "explanation", "is_active"):
            if field in data:
                new_val = data[field]
                old_val = getattr(question, field)
                if new_val != old_val:
                    changes[field] = {"old": old_val, "new": new_val}
                    setattr(question, field, new_val)
        question.save()

        if "options" in data and data["options"] is not None:
            validated_options = validate_question_options_payload(list(data["options"]))
            existing_opts = {
                o.option_number: o for o in QuestionOption.all_objects.filter(question=question)
            }
            for opt_data in validated_options:
                num = int(opt_data["option_number"])
                if num in existing_opts:
                    opt_obj = existing_opts[num]
                    if opt_obj.is_correct != bool(opt_data["is_correct"]):
                        key_changed = True
                    opt_obj.text = str(opt_data["text"])
                    opt_obj.is_correct = bool(opt_data["is_correct"])
                    opt_obj.is_active = True
                    opt_obj.save(update_fields=["text", "is_correct", "is_active", "updated_at"])
                else:
                    key_changed = True
                    QuestionOption.objects.create(
                        question=question,
                        option_number=num,
                        text=str(opt_data["text"]),
                        is_correct=bool(opt_data["is_correct"]),
                    )
            changes["options_updated"] = True

        record_audit_log(
            action=AuditAction.QUESTION_UPDATED,
            resource_type="question",
            resource_id=question.pk,
            request=request,
            changes=changes,
            extra_data={"key_changed": key_changed},
        )
        if key_changed and auto_regrade:
            regrade_all_attempts(request=request)

        invalidate_domain_cache(
            "exam_status", reason=f"question.updated:{question.pk}", record_outbox=False
        )
        return question


def deactivate_question(*, question: Question, request: Any = None) -> Question:
    """غیرفعال‌سازی نرم یک سوال در بانک سوال."""
    with transaction.atomic():
        question.soft_delete()
        record_audit_log(
            action=AuditAction.QUESTION_DELETED,
            resource_type="question",
            resource_id=question.pk,
            request=request,
        )
        invalidate_domain_cache(
            "exam_status", reason=f"question.deleted:{question.pk}", record_outbox=False
        )
        return question


def regrade_all_attempts(*, request: Any = None) -> dict[str, int]:
    """بازتصحیح خودکار تمامی کارنامه‌های ثبت‌شده بر اساس آخرین کلید سوالات و فرمول امتیازدهی."""
    config = get_or_create_exam_configuration()
    finished_attempts = list(
        ExamAttempt.objects.select_related("user", "mosque").filter(
            status__in=[ExamAttemptStatus.COMPLETED, ExamAttemptStatus.TIMED_OUT]
        )
    )
    updated_count = 0

    with transaction.atomic():
        for attempt in finished_attempts:
            items = list(
                ExamAttemptItem.objects.select_related("question")
                .prefetch_related("question__options")
                .filter(attempt=attempt)
            )
            correct_cnt = 0
            wrong_cnt = 0
            unanswered_cnt = 0

            for item in items:
                if item.selected_position is None or item.selected_option_id is None:
                    new_status = AnswerResultStatus.UNANSWERED
                    unanswered_cnt += 1
                else:
                    correct_opt = next(
                        (o for o in item.question.options.all() if o.is_correct),
                        None,
                    )
                    if correct_opt is not None and int(item.selected_option_id) == int(
                        correct_opt.id
                    ):
                        new_status = AnswerResultStatus.CORRECT
                        correct_cnt += 1
                    else:
                        new_status = AnswerResultStatus.WRONG
                        wrong_cnt += 1

                if item.result_status != new_status:
                    item.result_status = new_status
                    item.save(update_fields=["result_status", "updated_at"])

            breakdown = compute_exam_score(
                correct_count=correct_cnt,
                wrong_count=wrong_cnt,
                total_questions=attempt.total_questions,
                duration_seconds=attempt.duration_seconds,
                duration_limit_seconds=attempt.duration_limit_seconds,
                points_per_correct=config.points_per_correct,
                points_per_wrong=config.points_per_wrong,
                max_time_bonus=config.max_time_bonus,
            )

            attempt.correct_count = correct_cnt
            attempt.wrong_count = wrong_cnt
            attempt.unanswered_count = unanswered_cnt
            attempt.base_score = breakdown.base_score
            attempt.time_bonus_score = breakdown.time_bonus_score
            attempt.total_score = breakdown.total_score
            attempt.accuracy_percent = breakdown.accuracy_percent
            attempt.receipt_signature = _compute_receipt_signature(attempt)
            attempt.save(
                update_fields=[
                    "correct_count",
                    "wrong_count",
                    "unanswered_count",
                    "base_score",
                    "time_bonus_score",
                    "total_score",
                    "accuracy_percent",
                    "receipt_signature",
                    "updated_at",
                ]
            )
            updated_count += 1

        record_audit_log(
            action=AuditAction.EXAM_REGRADED,
            resource_type="exam_attempt",
            resource_id="all",
            request=request,
            extra_data={"regraded_attempts_count": updated_count},
        )
        invalidate_domain_cache("mosques", reason="exam.regraded")
        invalidate_domain_cache("reporting", reason="exam.regraded", record_outbox=False)

    return {"regraded_attempts_count": updated_count}


def seed_default_questions(*, request: Any = None) -> dict[str, int]:
    """بارگذاری بانک سوالات نمونهٔ هفته بسیج و سیره شهید کاوه."""
    created_count = 0
    existing_count = 0

    with transaction.atomic():
        for q_data in DEFAULT_SAMPLE_QUESTIONS:
            q_text = str(q_data["text"])
            if Question.all_objects.filter(text=q_text).exists():
                existing_count += 1
                continue
            create_question_with_options(
                data={
                    "text": q_text,
                    "chapter": q_data["chapter"],
                    "difficulty": q_data["difficulty"],
                    "explanation": q_data["explanation"],
                    "is_active": True,
                    "options": q_data["options"],
                },
                request=request,
            )
            created_count += 1

    return {
        "created": created_count,
        "existing": existing_count,
        "total": created_count + existing_count,
    }

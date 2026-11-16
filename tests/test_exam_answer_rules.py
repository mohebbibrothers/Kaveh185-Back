"""تست‌های قاعده‌های پاسخ در آزمون — همان چیزی که «عدالت مسابقه» یعنی.

سه قاعده‌ای که اگر بشکنند مسابقه بی‌اعتبار می‌شود
──────────────────────────────────────────────────
1. **بدون رد کردن پرسش**: برای پاسخ به پرسش k باید ۱..k-۱ پاسخ داشته باشند.
2. **مهلت سرور تعیین‌کننده است**: پس از پایان زمان، پاسخ تازه ثبت نمی‌شود.
3. **گزینهٔ نامعتبر رد می‌شود**: فقط جایگاه ۱..۴ پذیرفته است.

این تست‌ها با کاربر واقعی و پرسش‌های واقعی کار می‌کنند، نه mock، چون
قاعده‌ها در لایهٔ دیتابیس و قفل ردیف اجرا می‌شوند.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.core.exceptions import ConflictDomainError, NotFoundDomainError, ValidationDomainError
from apps.exam.choices import ExamAttemptStatus
from apps.exam.models import ExamAttempt, ExamConfiguration, Question
from apps.exam.services import (
    finish_exam_attempt,
    start_or_resume_exam,
    submit_question_answer,
)
from apps.mosques.models import Mosque
from tests.factories import create_test_question, make_valid_national_id

pytestmark = pytest.mark.django_db

User = get_user_model()


@pytest.fixture()
def participant() -> User:
    mosque = Mosque.objects.create(name="مسجد قاعده‌ها", code="MSQ-90")
    return User.objects.create_user(
        phone_number="09126660000",
        national_id=make_valid_national_id(101),
        first_name="رها",
        last_name="پاسخ",
        birth_date="1380-01-01",
        mosque=mosque,
        is_phone_verified=True,
    )


@pytest.fixture()
def question_bank() -> list[Question]:
    """بانک ۵ پرسشهٔ استاندارد (کارخانهٔ مشترک تست‌ها)."""
    return [
        create_test_question(seq=i, correct_option_number=((i - 1) % 4) + 1) for i in range(1, 6)
    ]


@pytest.fixture()
def open_config() -> ExamConfiguration:
    ExamConfiguration.objects.create(
        title="مسابقهٔ تست",
        starts_at=timezone.now() - timedelta(hours=1),
        ends_at=timezone.now() + timedelta(hours=1),
        is_manually_open=True,
        questions_per_attempt=5,
        duration_seconds=300,
    )


def test_start_requires_complete_profile() -> None:
    """کاربر بی‌مسجد/بی‌تاریخ تولد اجازهٔ شروع ندارد."""
    user = User.objects.create_user(
        phone_number="09126660001",
        national_id=make_valid_national_id(102),
        first_name="ناقص",
        last_name="پروفایل",
        birth_date="1380-01-01",
    )
    with pytest.raises(ValidationDomainError) as exc:
        start_or_resume_exam(user=user)
    assert exc.value.code == "incomplete_profile"


def test_start_creates_five_questions_and_resumes(participant, question_bank, open_config) -> None:
    """شروع آزمون ۵ پرسش می‌سازد و بار دوم همان آزمون را ادامه می‌دهد."""
    attempt, created = start_or_resume_exam(user=participant)
    assert created is True
    assert attempt.items.count() == 5
    assert attempt.status == ExamAttemptStatus.IN_PROGRESS
    assert attempt.expires_at > timezone.now()

    same, created_again = start_or_resume_exam(user=participant)
    assert created_again is False
    assert same.pk == attempt.pk


def test_cannot_skip_a_question(participant, question_bank, open_config) -> None:
    """پاسخ به پرسش ۲ پیش از پرسش ۱ رد می‌شود (قاعدهٔ عمدی مسابقه)."""
    start_or_resume_exam(user=participant)
    with pytest.raises(ValidationDomainError) as exc:
        submit_question_answer(user=participant, question_number=2, selected_position=1)
    assert exc.value.code == "cannot_skip_question"
    assert exc.value.errors == {"unanswered_prior_questions": [1]}


def test_answer_in_order_is_accepted(participant, question_bank, open_config) -> None:
    """پاسخ به‌ترتیب پذیرفته و ذخیره می‌شود."""
    start_or_resume_exam(user=participant)
    submit_question_answer(user=participant, question_number=1, selected_position=2)
    attempt = ExamAttempt.objects.get(user=participant)
    item = attempt.items.get(question_number=1)
    assert item.selected_position == 2
    assert item.selected_option_id is not None
    assert item.answered_at is not None


@pytest.mark.parametrize("position", [0, 5, -1])
def test_invalid_position_is_rejected(participant, question_bank, open_config, position) -> None:
    """جایگاه گزینه بیرون از ۱..۴ خطای اعتبارسنجی می‌دهد."""
    start_or_resume_exam(user=participant)
    with pytest.raises(ValidationDomainError) as exc:
        submit_question_answer(user=participant, question_number=1, selected_position=position)
    assert exc.value.code == "invalid_selected_position"


def test_unknown_question_number_is_rejected(participant, question_bank, open_config) -> None:
    """پرسش ناموجود در آزمون، خطای روشن می‌دهد."""
    start_or_resume_exam(user=participant)
    with pytest.raises(ValidationDomainError) as exc:
        submit_question_answer(user=participant, question_number=99, selected_position=1)
    assert exc.value.code == "invalid_question_number"


def test_answer_after_deadline_is_blocked(participant, question_bank, open_config) -> None:
    """پس از پایان مهلت، پاسخ تازه ثبت نمی‌شود و کارنامه صادر می‌شود."""
    attempt, _ = start_or_resume_exam(user=participant)
    ExamAttempt.objects.filter(pk=attempt.pk).update(
        expires_at=timezone.now() - timedelta(seconds=30)
    )
    with pytest.raises(ConflictDomainError) as exc:
        submit_question_answer(user=participant, question_number=1, selected_position=1)
    assert exc.value.code == "exam_time_expired"
    attempt.refresh_from_db()
    assert attempt.status == ExamAttemptStatus.TIMED_OUT
    assert attempt.tracking_code.startswith("KV185-")
    assert attempt.completed_at is not None


def test_finish_without_answer_is_rejected(participant, question_bank, open_config) -> None:
    """تا وقتی همهٔ پرسش‌ها بی‌پاسخ‌اند، پایان آزمون ممکن نیست."""
    start_or_resume_exam(user=participant)
    with pytest.raises(ValidationDomainError):
        finish_exam_attempt(user=participant)


def test_finish_after_all_answers_issues_report(participant, question_bank, open_config) -> None:
    """با پاسخ کامل، کارنامه صادر و وضعیت «تکمیل‌شده» می‌شود."""
    start_or_resume_exam(user=participant)
    for number in range(1, 6):
        submit_question_answer(user=participant, question_number=number, selected_position=1)
    attempt = finish_exam_attempt(user=participant)
    assert attempt.status == ExamAttemptStatus.COMPLETED
    assert attempt.completed_at is not None
    assert attempt.total_score is not None


def test_answered_attempt_cannot_be_changed(participant, question_bank, open_config) -> None:
    """پس از پایان آزمون، تغییر پاسخ ممکن نیست."""
    start_or_resume_exam(user=participant)
    for number in range(1, 6):
        submit_question_answer(user=participant, question_number=number, selected_position=1)
    finish_exam_attempt(user=participant)
    with pytest.raises(ConflictDomainError) as exc:
        submit_question_answer(user=participant, question_number=1, selected_position=3)
    assert exc.value.code == "exam_already_finished"


def test_submit_without_start_is_not_found(participant, question_bank, open_config) -> None:
    """پاسخ بدون شروع آزمون ⇒ خطای «آزمونی شروع نشده»."""
    with pytest.raises(NotFoundDomainError) as exc:
        submit_question_answer(user=participant, question_number=1, selected_position=1)
    assert exc.value.code == "exam_attempt_not_found"

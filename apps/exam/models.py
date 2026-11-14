"""مدل‌های تنظیمات آزمون، بانک سوال چهارگزینه‌ای، جلسهٔ آزمون کاربر و پاسخنامه."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.jalali import format_jalali_datetime
from apps.core.models import BaseModel

from .choices import (
    DEFAULT_COMMUNICATION_CHANNELS,
    AnswerResultStatus,
    ExamAttemptStatus,
    ExamWindowState,
    QuestionDifficulty,
)
from .scoring import format_duration_persian


def _default_channels() -> list[dict[str, str]]:
    """مقدار پیش‌فرض کانال‌های ارتباطی حوزه مقاومت بسیج ۱۸۵ شهید کاوه."""
    return [dict(ch) for ch in DEFAULT_COMMUNICATION_CHANNELS]


def _default_starts_at() -> Any:
    """زمان شروع پیش‌فرض آزمون (۱ ساعت قبل برای آماده بودن در محیط توسعه)."""
    return timezone.now() - timedelta(hours=1)


def _default_ends_at() -> Any:
    """زمان پایان پیش‌فرض آزمون (۷ روز بعد — یک هفته مهلت شرکت در آزمون)."""
    return timezone.now() + timedelta(days=7)


class ExamConfiguration(BaseModel):
    """پیکربندی زنده و نسخه‌دار آزمون (تایمر، بازه زمانی، امتیازدهی و پیامک پایان آزمون)."""

    singleton_key = models.CharField(
        max_length=32,
        unique=True,
        default="kaveh185_main",
        verbose_name="کلید یکتای تنظیمات",
    )
    title = models.CharField(
        max_length=200,
        default="مسابقه بزرگ فرهنگی و کتابخوانی هفته بسیج — کاوه ۱۸۵",
        verbose_name="عنوان مسابقه",
    )
    book_title = models.CharField(
        max_length=200,
        default="کتاب منتخب هفته بسیج — سیره شهدای شاخص و فرهنگ بسیجی",
        verbose_name="نام کتاب مسابقه",
    )
    organizer_name = models.CharField(
        max_length=160,
        default="حوزه مقاومت بسیج ۱۸۵ شهید کاوه",
        verbose_name="برگزارکننده",
    )
    description = models.TextField(
        blank=True,
        default="به مناسبت هفته بسیج، پس از ثبت اطلاعات و انتخاب مسجد خود، به ۵ سوال چهارگزینه‌ای پاسخ دهید.",
        verbose_name="توضیحات مسابقه",
    )
    starts_at = models.DateTimeField(
        default=_default_starts_at,
        db_index=True,
        verbose_name="زمان شروع مهلت آزمون",
    )
    ends_at = models.DateTimeField(
        default=_default_ends_at,
        db_index=True,
        verbose_name="زمان پایان مهلت آزمون",
    )
    is_manually_open = models.BooleanField(
        default=True,
        verbose_name="فعال بودن دستی آزمون توسط ادمین",
    )
    duration_seconds = models.PositiveIntegerField(
        default=300,
        verbose_name="مدت زمان آزمون برای هر شرکت‌کننده (ثانیه)",
    )
    questions_per_attempt = models.PositiveSmallIntegerField(
        default=5,
        verbose_name="تعداد سوالات تصادفی در هر آزمون",
    )
    require_otp_before_exam = models.BooleanField(
        default=False,
        verbose_name="الزام تایید OTP پیامکی پیش از شروع آزمون",
    )
    points_per_correct = models.FloatField(
        default=20.0,
        verbose_name="امتیاز هر پاسخ درست",
    )
    points_per_wrong = models.FloatField(
        default=0.0,
        verbose_name="امتیاز/نمره منفی هر پاسخ غلط",
    )
    max_time_bonus = models.FloatField(
        default=20.0,
        verbose_name="حداکثر پاداش سرعت پاسخگویی",
    )
    thank_you_sms_enabled = models.BooleanField(
        default=True,
        verbose_name="ارسال پیامک تشکر و کانال‌ها پس از پایان آزمون",
    )
    thank_you_sms_template = models.TextField(
        default=(
            "{full_name} عزیز، از مشارکت ارزشمند شما از طرف «{mosque_name}» در مسابقه کتابخوانی "
            "هفته بسیج حوزه ۱۸۵ شهید کاوه سپاسگزاریم. کد رهگیری قرعه‌کشی: {tracking_code}"
        ),
        verbose_name="قالب پیامک تشکر پایان آزمون",
    )
    communication_channels: Any = models.JSONField(
        default=_default_channels,
        blank=True,
        verbose_name="کانال‌های ارتباطی و تبلیغاتی حوزه ۱۸۵",
    )
    policy_version = models.PositiveIntegerField(default=1, verbose_name="نسخه سیاست آزمون")

    class Meta:
        verbose_name = "تنظیمات آزمون"
        verbose_name_plural = "تنظیمات آزمون"

    def resolve_window_state(self, *, now: Any = None) -> Any:
        """محاسبهٔ وضعیت فعلی پنجرهٔ زمانی آزمون (`upcoming`, `open`, `ended`)."""
        ref = now or timezone.now()
        if ref < self.starts_at:
            return ExamWindowState.UPCOMING
        if not self.is_manually_open or ref > self.ends_at:
            return ExamWindowState.ENDED
        return ExamWindowState.OPEN

    def __str__(self) -> str:
        """نمایش متنی تنظیمات آزمون."""
        return f"{self.title} (v{self.policy_version})"


class Question(BaseModel):
    """سوال چهارگزینه‌ای در بانک سوال مسابقه کاوه ۱۸۵."""

    text = models.TextField(verbose_name="متن صورت سوال")
    chapter = models.CharField(
        max_length=160,
        blank=True,
        default="",
        db_index=True,
        verbose_name="فصل / بخش کتاب",
    )
    difficulty = models.CharField(
        max_length=16,
        choices=QuestionDifficulty.choices,
        default=QuestionDifficulty.MEDIUM,
        db_index=True,
        verbose_name="سطح دشواری",
    )
    explanation = models.TextField(
        blank=True,
        default="",
        verbose_name="توضیح تشریحی (مخصوص ادمین)",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_questions",
        verbose_name="طراح سوال",
    )

    class Meta:
        verbose_name = "سوال چهارگزینه‌ای"
        verbose_name_plural = "بانک سوالات چهارگزینه‌ای"
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        """نمایش خلاصهٔ صورت سوال."""
        return f"Q#{self.id}: {self.text[:60]}"


class QuestionOption(BaseModel):
    """یکی از ۴ گزینهٔ هر سوال در بانک سوال."""

    question = models.ForeignKey(
        Question,
        on_delete=models.CASCADE,
        related_name="options",
        verbose_name="سوال",
    )
    option_number = models.PositiveSmallIntegerField(verbose_name="شماره گزینه در بانک (۱ تا ۴)")
    text = models.CharField(max_length=500, verbose_name="متن گزینه")
    is_correct = models.BooleanField(default=False, verbose_name="گزینه صحیح است؟")

    class Meta:
        verbose_name = "گزینه سوال"
        verbose_name_plural = "گزینه‌های سوال"
        ordering = ["option_number", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["question", "option_number"],
                name="uniq_question_option_number",
            ),
        ]

    def __str__(self) -> str:
        """نمایش متنی گزینه."""
        mark = "✓" if self.is_correct else " "
        return f"[{mark}] گزینه {self.option_number}: {self.text[:40]}"


class ExamAttempt(BaseModel):
    """جلسهٔ شرکت در آزمون برای هر کاربر (قید سخت‌گیرانهٔ حداکثر ۱ بار شرکت برای هر کاربر)."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="exam_attempt",
        verbose_name="شرکت‌کننده",
    )
    mosque = models.ForeignKey(
        "mosques.Mosque",
        on_delete=models.PROTECT,
        related_name="exam_attempts",
        verbose_name="مسجد ثبت‌شده در لحظه آزمون",
    )
    tracking_code = models.CharField(
        max_length=32,
        unique=True,
        db_index=True,
        verbose_name="کد رهگیری کارنامه و قرعه‌کشی",
    )
    receipt_signature = models.CharField(
        max_length=64,
        blank=True,
        default="",
        verbose_name="امضای دیجیتال رسید (HMAC-SHA256)",
    )
    status = models.CharField(
        max_length=24,
        choices=ExamAttemptStatus.choices,
        default=ExamAttemptStatus.IN_PROGRESS,
        db_index=True,
        verbose_name="وضعیت آزمون",
    )
    started_at = models.DateTimeField(
        default=timezone.now, db_index=True, verbose_name="زمان شروع آزمون"
    )
    expires_at = models.DateTimeField(db_index=True, verbose_name="موعد پایان تایمر سرور")
    completed_at = models.DateTimeField(
        null=True, blank=True, db_index=True, verbose_name="زمان پایان آزمون"
    )

    duration_limit_seconds = models.PositiveIntegerField(
        default=300, verbose_name="مهلت مجاز (ثانیه)"
    )
    duration_seconds = models.PositiveIntegerField(
        default=0, db_index=True, verbose_name="زمان صرف‌شده (ثانیه)"
    )

    total_questions = models.PositiveSmallIntegerField(default=5, verbose_name="تعداد کل سوالات")
    correct_count = models.PositiveSmallIntegerField(
        default=0, db_index=True, verbose_name="تعداد پاسخ درست"
    )
    wrong_count = models.PositiveSmallIntegerField(
        default=0, db_index=True, verbose_name="تعداد پاسخ غلط"
    )
    unanswered_count = models.PositiveSmallIntegerField(
        default=0, db_index=True, verbose_name="تعداد سوالات بی‌پاسخ"
    )

    base_score = models.FloatField(default=0.0, verbose_name="امتیاز پایه")
    time_bonus_score = models.FloatField(default=0.0, verbose_name="پاداش سرعت")
    total_score = models.FloatField(default=0.0, db_index=True, verbose_name="امتیاز کل نهایی")
    accuracy_percent = models.FloatField(default=0.0, verbose_name="درصد پاسخگویی صحیح")

    started_ip = models.CharField(
        max_length=64, blank=True, default="", verbose_name="IP شروع آزمون"
    )
    completed_ip = models.CharField(
        max_length=64, blank=True, default="", verbose_name="IP پایان آزمون"
    )
    user_agent = models.CharField(
        max_length=300, blank=True, default="", verbose_name="مرورگر شرکت‌کننده"
    )
    thank_you_sms_sent = models.BooleanField(default=False, verbose_name="ارسال پیامک تشکر")

    class Meta:
        verbose_name = "کارنامه و جلسه آزمون"
        verbose_name_plural = "کارنامه‌ها و جلسات آزمون"
        ordering = ["-total_score", "duration_seconds", "-completed_at"]
        constraints = [
            models.UniqueConstraint(fields=["user"], name="uniq_exam_attempt_per_user"),
        ]
        indexes = [
            models.Index(
                fields=["status", "-total_score", "duration_seconds"],
                name="attempt_ranking_idx",
            ),
            models.Index(
                fields=["mosque", "status", "-total_score"],
                name="attempt_mosque_score_idx",
            ),
            models.Index(
                fields=["status", "-correct_count", "duration_seconds"],
                name="attempt_correct_dur_idx",
            ),
        ]

    @property
    def duration_display(self) -> str:
        """نمایش خوانای فارسی مدت زمان صرف‌شده در آزمون."""
        return format_duration_persian(self.duration_seconds)

    @property
    def started_at_jalali(self) -> str:
        """زمان شروع آزمون به تاریخ و ساعت شمسی."""
        return format_jalali_datetime(self.started_at)

    @property
    def completed_at_jalali(self) -> str:
        """زمان پایان آزمون به تاریخ و ساعت شمسی."""
        return format_jalali_datetime(self.completed_at)

    def remaining_seconds(self, *, now: Any = None) -> int:
        """محاسبهٔ ثانیه‌های باقی‌مانده از تایمر آزمون روی سرور."""
        if self.status != ExamAttemptStatus.IN_PROGRESS:
            return 0
        ref = now or timezone.now()
        rem = int((self.expires_at - ref).total_seconds())
        return max(0, rem)

    def __str__(self) -> str:
        """نمایش خوانای جلسهٔ آزمون."""
        return f"{self.tracking_code} - user={self.user_id} ({self.status})"


class ExamAttemptItem(BaseModel):
    """سوال تخصیص‌یافته به شرکت‌کننده همراه با چیدمان تصادفی گزینه‌های ۱ تا ۴."""

    attempt = models.ForeignKey(
        ExamAttempt,
        on_delete=models.CASCADE,
        related_name="items",
        verbose_name="جلسه آزمون",
    )
    question = models.ForeignKey(
        Question,
        on_delete=models.PROTECT,
        related_name="attempt_items",
        verbose_name="سوال اصلی",
    )
    question_number = models.PositiveSmallIntegerField(
        verbose_name="شماره ترتیب سوال در آزمون کاربر (۱ تا ۵)",
    )
    shuffled_options: Any = models.JSONField(
        default=list,
        verbose_name="چیدمان تصادفی گزینه‌های ۱ تا ۴ برای این شرکت‌کننده",
    )
    selected_position = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        verbose_name="شماره گزینه انتخابی کاربر (۱ تا ۴ در چیدمان تصادفی)",
    )
    selected_option_id = models.PositiveBigIntegerField(
        null=True,
        blank=True,
        verbose_name="شناسه گزینه اصلی انتخاب‌شده",
    )
    answered_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="زمان ثبت پاسخ",
    )
    result_status = models.CharField(
        max_length=16,
        choices=AnswerResultStatus.choices,
        default=AnswerResultStatus.UNANSWERED,
        db_index=True,
        verbose_name="وضعیت صحت پاسخ (فقط برای ادمین)",
    )

    class Meta:
        verbose_name = "پاسخ تک‌سوال آزمون"
        verbose_name_plural = "پاسخ‌های تک‌سوال آزمون"
        ordering = ["question_number", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["attempt", "question_number"],
                name="uniq_attempt_question_number",
            ),
            models.UniqueConstraint(
                fields=["attempt", "question"],
                name="uniq_attempt_question_pair",
            ),
        ]

    def __str__(self) -> str:
        """نمایش خوانای آیتم آزمون."""
        return f"Attempt #{self.attempt_id} - Q{self.question_number}"

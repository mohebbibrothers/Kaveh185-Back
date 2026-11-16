"""مدل‌های تنظیمات آزمون، بانک سوال چهارگزینه‌ای، جلسهٔ آزمون کاربر و پاسخنامه."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
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
        default="شهادت آیه‌ها (۲)",
        verbose_name="نام کتاب مسابقه",
    )
    organizer_name = models.CharField(
        max_length=160,
        default="حوزه مقاومت بسیج ۱۸۵ شهید کاوه",
        verbose_name="برگزارکننده",
    )
    description = models.TextField(
        blank=True,
        default=(
            "به مناسبت هفتهٔ بسیج، پس از ثبت اطلاعات و انتخاب مسجد خود، "
            "به پنج پرسش چهارگزینه‌ای از کتاب «شهادت آیه‌ها (۲)» پاسخ دهید."
        ),
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
    # ── منبع سؤال در کتاب «شهادت آیه‌ها (۲)» ─────────────────────────────
    # کتاب ۳۰ داستان دارد و فصل‌بندی ندارد؛ پس «فصل/بخش» معنا ندارد.
    # این دو فیلد فقط برای ادمین است و هرگز به شرکت‌کننده نشان داده نمی‌شود
    # (قرارداد عمومی آزمون فقط متن سؤال و گزینه‌ها را می‌فرستد).
    source_story = models.CharField(
        max_length=160,
        blank=True,
        default="",
        db_index=True,
        verbose_name="نام داستان (اختیاری)",
        help_text="مثلاً «داستان ۱۲ — آب را که گل آلود کنی…». فقط ادمین می‌بیند.",
    )
    source_page = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        db_index=True,
        verbose_name="شمارهٔ صفحه (اختیاری)",
        help_text="شمارهٔ صفحه در نسخهٔ فایل کتاب. فقط ادمین می‌بیند.",
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


# ══════════════════════════════════════════════════════════════════════════
# کتاب مسابقه — فایلی که ادمین بارگذاری می‌کند و شرکت‌کننده می‌خواند
# ══════════════════════════════════════════════════════════════════════════
#
# چرا مدل جدا و نه یک FileField روی ExamConfiguration؟
#   ۱) نسخه‌دار است: اگر کتاب ویرایش شود، لینک‌هایی که در پیام‌رسان‌ها
#      فرستاده شده‌اند نباید به محتوای دیگری اشاره کنند.
#   ۲) چند فایل در آینده (نسخهٔ موبایل، جلد) بی‌دردسر جا می‌گیرد.
#   ۳) شمارندهٔ بازدید یک ردیف مستقل است، نه عددی روی تنظیمات.
#
# امنیت: فایل در MEDIA_ROOT می‌نشیند ولی با سرو مستقیم پوشه داده نمی‌شود؛
# نمای کنترل‌شده (`views_book.py`) فقط کتاب منتشرشده را می‌دهد.

# فرمت‌هایی که مرورگرها بدون افزونهٔ اضافه باز می‌کنند. عمداً بسته است.
ALLOWED_BOOK_EXTENSIONS = ["pdf", "epub"]
MAX_BOOK_SIZE_BYTES = 60 * 1024 * 1024


def book_upload_path(instance: BookFile, filename: str) -> str:
    """مسیر ذخیرهٔ فایل: `books/<slug>/<نام-امن>`.

    چرا نام فایل را بازسازی می‌کنیم؟ نام فایل کاربر می‌تواند شامل
    کاراکترهای خطرناک، مسیر نسبی (`../`) یا حروف غیرقابل‌نمایش باشد.
    فقط پسوند را نگه می‌داریم و بقیه را می‌سازیم.
    """
    ext = Path(filename).suffix.lower().lstrip(".")
    safe_slug = (
        "".join(ch for ch in (instance.slug or "book") if ch.isalnum() or ch in "-_") or "book"
    )
    version = instance.updated_at.strftime("%Y%m%d%H%M%S") if instance.updated_at else "v1"
    return f"books/{safe_slug}/{safe_slug}-{version}.{ext or 'pdf'}"


class BookFile(BaseModel):
    """یک فایل کتاب قابل مطالعه برای شرکت‌کنندگان."""

    title = models.CharField(
        max_length=200,
        default="شهادت آیه‌ها (۲)",
        verbose_name="عنوان کتاب",
    )
    slug = models.SlugField(
        max_length=80,
        unique=True,
        default="shahadat-ayeha-2",
        allow_unicode=False,
        verbose_name="شناسهٔ یکتا",
        help_text="در نشانی عمومی کتاب استفاده می‌شود؛ انگلیسی و کوتاه باشد.",
    )
    description = models.TextField(
        blank=True,
        default="",
        verbose_name="توضیح کوتاه",
        help_text="یک یا دو جمله برای معرفی کتاب در صفحهٔ مطالعه.",
    )
    file = models.FileField(
        upload_to=book_upload_path,
        validators=[FileExtensionValidator(allowed_extensions=ALLOWED_BOOK_EXTENSIONS)],
        verbose_name="فایل کتاب",
        help_text="PDF یا EPUB — حداکثر ۶۰ مگابایت.",
    )
    # چرا FileField و نه ImageField؟ `ImageField` وابستگی اجباری به Pillow
    # به کل پروژه اضافه می‌کند (روی هاست cPanel هم باید نصب شود) فقط برای
    # اینکه یک تصویر جلد اعتبارسنجی شود. این‌جا همان کار با
    # `FileExtensionValidator` و بدون وابستگی تازه انجام می‌شود.
    cover = models.FileField(
        upload_to="books/covers/",
        blank=True,
        null=True,
        validators=[FileExtensionValidator(allowed_extensions=["jpg", "jpeg", "png", "webp"])],
        verbose_name="جلد (اختیاری)",
        help_text="تصویر عمودی JPG/PNG/WebP؛ اگر ندهید، جلد پیش‌فرض سایت استفاده می‌شود.",
    )
    is_published = models.BooleanField(
        default=False,
        db_index=True,
        verbose_name="منتشر شده",
        help_text="تا وقتی این تیک نخورد، کتاب در سایت نمایش داده نمی‌شود.",
    )
    page_count = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name="تعداد صفحه (اختیاری)",
        help_text="برای نمایش «۳۰ داستان در ۴۸ صفحه»؛ اختیاری است.",
    )
    story_count = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name="تعداد داستان (اختیاری)",
    )
    view_count = models.PositiveIntegerField(
        default=0,
        editable=False,
        verbose_name="تعداد بازدید",
        help_text="با هر بار باز شدن صفحهٔ مطالعه یک واحد زیاد می‌شود.",
    )

    class Meta:
        verbose_name = "کتاب مسابقه"
        verbose_name_plural = "کتاب‌های مسابقه"
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        """نمایش خوانای کتاب."""
        return f"{self.title} ({self.slug})"

    # ── کمکی‌ها ──────────────────────────────────────────────────────────
    @property
    def extension(self) -> str:
        """پسوند فایل بدون نقطه، با حروف کوچک."""
        return Path(self.file.name or "").suffix.lower().lstrip(".")

    @property
    def is_pdf(self) -> bool:
        """آیا فایل PDF است؟ (برای نمایش درون‌خطی)"""
        return self.extension == "pdf"

    def size_mb(self) -> float:
        """حجم فایل به مگابایت، گردشده به یک رقم."""
        try:
            return round(float(self.file.size) / (1024 * 1024), 1)
        except (OSError, ValueError, AttributeError):
            return 0.0

    def clean(self) -> None:
        """اعتبارسنجی حجم فایل پیش از ذخیره.

        چرا این‌جا و نه در فرم؟ چون هم پنل ادمین و هم API از این مدل
        رد می‌شوند. یک نقطهٔ کنترل، دو مسیر پوشش.
        """
        super().clean()
        if (
            self.file
            and hasattr(self.file, "size")
            and self.file.size
            and int(self.file.size) > MAX_BOOK_SIZE_BYTES
        ):
            raise ValidationError(
                {
                    "file": (
                        f"حجم فایل کتاب {self.size_mb()} مگابایت است؛ "
                        f"سقف مجاز {MAX_BOOK_SIZE_BYTES // (1024 * 1024)} مگابایت است."
                    )
                }
            )

    def save(self, *args: Any, **kwargs: Any) -> None:
        """ذخیره با اطمینان از خالی نبودن slug."""
        if not self.slug:
            self.slug = "book"
        super().save(*args, **kwargs)

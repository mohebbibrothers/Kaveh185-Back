"""پیکربندی پنل ادمین جنگو برای تنظیمات آزمون، بانک سوال و کارنامه‌ها."""

from __future__ import annotations

from typing import Any

from django.contrib import admin
from django.utils.html import format_html

from .models import (
    BookFile,
    ExamAttempt,
    ExamAttemptItem,
    ExamConfiguration,
    Question,
    QuestionOption,
)


class QuestionOptionInline(admin.TabularInline):
    """ویرایش ۴ گزینهٔ هر سوال در همان صفحهٔ سوال در پنل ادمین."""

    model = QuestionOption
    extra = 4
    max_num = 4


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    """مدیریت بانک سوال چهارگزینه‌ای در پنل ادمین جنگو."""

    list_display = (
        "id",
        "short_text",
        "source_cell",
        "difficulty",
        "is_active",
        "times_drawn_cell",
    )
    list_filter = ("difficulty", "is_active")
    search_fields = ("text", "source_story", "explanation")
    inlines = [QuestionOptionInline]
    fieldsets = (
        (
            "سؤال",
            {
                "fields": ("text", "difficulty", "is_active"),
                "description": "متن سؤال باید مستقیماً از کتاب «شهادت آیه‌ها (۲)» باشد.",
            },
        ),
        (
            "منبع در کتاب (اختیاری — فقط ادمین می‌بیند)",
            {
                "fields": ("source_story", "source_page"),
                "description": (
                    "کتاب ۳۰ داستان دارد و فصل‌بندی ندارد. نام یا شمارهٔ داستان و "
                    "شمارهٔ صفحه را این‌جا بنویسید تا بعداً پیدا کردنش آسان باشد. "
                    "شرکت‌کننده هیچ‌وقت این اطلاعات را نمی‌بیند."
                ),
            },
        ),
        (
            "مخصوص ادمین",
            {
                "fields": ("explanation",),
                "classes": ("collapse",),
                "description": "توضیح تشریحی؛ هرگز به شرکت‌کننده نمایش داده نمی‌شود.",
            },
        ),
    )

    @admin.display(description="صورت سؤال")
    def short_text(self, obj: Question) -> str:
        """خلاصهٔ سؤال برای فهرست — متن کامل در فرم دیده می‌شود."""
        return (obj.text[:70] + "…") if len(obj.text) > 70 else obj.text

    @admin.display(description="منبع")
    def source_cell(self, obj: Question) -> str:
        """داستان و صفحه در یک سلول."""
        if not obj.source_story and not obj.source_page:
            return format_html('<span style="opacity:.45">—</span>')
        page = f"ص {obj.source_page}" if obj.source_page else ""
        return format_html("{} <span style='opacity:.5'>{}</span>", obj.source_story or "—", page)

    @admin.display(description="تعداد کشش")
    def times_drawn_cell(self, obj: Question) -> str:
        """چند بار این سؤال در آزمون کسی آمده — معیار عدالت توزیع."""
        total = obj.attempt_items.count()
        return format_html('<span style="font-variant-numeric:tabular-nums">{}</span>', total)


@admin.register(ExamConfiguration)
class ExamConfigurationAdmin(admin.ModelAdmin):
    """مدیریت تنظیمات کلی مسابقه در پنل ادمین جنگو."""

    list_display = (
        "title",
        "starts_at",
        "ends_at",
        "is_manually_open",
        "duration_seconds",
        "questions_per_attempt",
        "require_otp_before_exam",
        "policy_version",
    )


class ExamAttemptItemInline(admin.TabularInline):
    """نمایش ۵ سوال و وضعیت پاسخ هر شرکت‌کننده برای ادمین."""

    model = ExamAttemptItem
    extra = 0
    readonly_fields = (
        "question_number",
        "question",
        "selected_position",
        "selected_option_id",
        "result_status",
        "answered_at",
    )


@admin.register(ExamAttempt)
class ExamAttemptAdmin(admin.ModelAdmin):
    """مدیریت و مشاهدهٔ کارنامه‌های شرکت‌کنندگان در پنل ادمین جنگو."""

    list_display = (
        "tracking_code",
        "user",
        "mosque",
        "status",
        "correct_count",
        "wrong_count",
        "unanswered_count",
        "duration_seconds",
        "total_score",
        "completed_at",
    )
    list_filter = ("status", "mosque")
    search_fields = (
        "tracking_code",
        "user__first_name",
        "user__last_name",
        "user__phone_number",
        "user__national_id",
    )
    inlines = [ExamAttemptItemInline]


@admin.register(BookFile)
class BookFileAdmin(admin.ModelAdmin):
    """بارگذاری و مدیریت فایل کتاب مسابقه.

    جریان کار ادمین — سه گام، بدون اصطلاح فنی:
      ۱) فایل PDF (یا EPUB) کتاب را این‌جا بارگذاری کنید.
      ۲) «منتشر شده» را تیک بزنید.
      ۳) ذخیره. همان لحظه در `kaveh185.ir/book/` برای همه قابل مطالعه است.
    """

    list_display = (
        "title",
        "slug",
        "published_badge",
        "format_cell",
        "size_cell",
        "view_cell",
        "updated_at",
    )
    list_filter = ("is_published", "is_active")
    search_fields = ("title", "slug", "description")
    prepopulated_fields: dict[str, Any] = {}
    readonly_fields = ("public_link", "view_count", "uploaded_at_display")
    fieldsets = (
        (
            "کتاب",
            {
                "fields": ("title", "slug", "description"),
                "description": "عنوان و یک توضیح دو خطی؛ همین‌ها در صفحهٔ مطالعه دیده می‌شوند.",
            },
        ),
        (
            "فایل",
            {
                "fields": ("file", "cover", "page_count", "story_count"),
                "description": "PDF یا EPUB تا ۶۰ مگابایت. جلد و تعداد صفحه اختیاری‌اند.",
            },
        ),
        (
            "انتشار",
            {
                "fields": ("is_published", "is_active", "public_link"),
                "description": (
                    "تا وقتی «منتشر شده» تیک نخورد، هیچ کاربری — حتی با لینک "
                    "مستقیم — به فایل دسترسی ندارد."
                ),
            },
        ),
        ("آمار", {"fields": ("view_count", "uploaded_at_display"), "classes": ("collapse",)}),
    )

    @admin.display(description="وضعیت", boolean=False)
    def published_badge(self, obj: BookFile) -> str:
        """نشان سبز/خاکستری برای وضعیت انتشار."""
        if obj.is_published:
            return format_html(
                '<span style="display:inline-block;padding:2px 9px;border-radius:999px;'
                'background:#e7f3ea;color:#22703c;font-weight:700;font-size:11px">منتشر شده</span>'
            )
        return format_html(
            '<span style="display:inline-block;padding:2px 9px;border-radius:999px;'
            'background:#f2efe8;color:#7a7264;font-weight:700;font-size:11px">پیش‌نویس</span>'
        )

    @admin.display(description="فرمت")
    def format_cell(self, obj: BookFile) -> str:
        """فرمت فایل."""
        return (obj.extension or "—").upper()

    @admin.display(description="حجم")
    def size_cell(self, obj: BookFile) -> str:
        """حجم فایل به مگابایت."""
        size = obj.size_mb()
        return f"{size} MB" if size else "—"

    @admin.display(description="بازدید")
    def view_cell(self, obj: BookFile) -> str:
        """تعداد بازدید مطالعه."""
        return f"{obj.view_count}"

    @admin.display(description="پیوند عمومی")
    def public_link(self, obj: BookFile) -> str:
        """پیوند آمادهٔ ارسال در کانال بله."""
        if not obj.pk or not obj.is_published:
            return "پس از انتشار، نشانی در این‌جا ظاهر می‌شود."
        return format_html(
            '<a href="/book/{0}/" target="_blank" rel="noopener">'
            '<code style="font-size:12.5px">kaveh185.ir/book/{0}/</code></a>',
            obj.slug,
        )

    @admin.display(description="تاریخ بارگذاری")
    def uploaded_at_display(self, obj: BookFile) -> str:
        """تاریخ ایجاد/به‌روزرسانی رکورد."""
        if not obj.pk:
            return "—"
        return obj.updated_at.strftime("%Y-%m-%d %H:%M")

"""پیکربندی پنل ادمین جنگو برای تنظیمات آزمون، بانک سوال و کارنامه‌ها."""

from __future__ import annotations

from django.contrib import admin

from .models import (
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

    list_display = ("id", "text", "chapter", "difficulty", "is_active", "created_at")
    list_filter = ("difficulty", "is_active", "chapter")
    search_fields = ("text", "chapter", "explanation")
    inlines = [QuestionOptionInline]


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

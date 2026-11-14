"""سریالایزرهای ورودی و خروجی برای موتور آزمون، بانک سوال، پاسخگویی و کارنامه."""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

from .models import ExamConfiguration, Question, QuestionOption


class PublicExamStatusSerializer(serializers.Serializer):
    """ساختار خروجی وضعیت عمومی و بازهٔ زمانی شرکت در آزمون."""

    title = serializers.CharField()
    book_title = serializers.CharField()
    organizer_name = serializers.CharField()
    description = serializers.CharField()
    window_state = serializers.CharField()
    window_state_label = serializers.CharField()
    can_participate = serializers.BooleanField()
    status_message = serializers.CharField()
    server_time = serializers.CharField()
    server_time_jalali = serializers.CharField()
    starts_at = serializers.CharField()
    starts_at_jalali = serializers.CharField()
    ends_at = serializers.CharField()
    ends_at_jalali = serializers.CharField()
    seconds_until_start = serializers.IntegerField()
    seconds_until_end = serializers.IntegerField()
    duration_seconds = serializers.IntegerField()
    questions_per_attempt = serializers.IntegerField()
    require_otp_before_exam = serializers.BooleanField()
    active_question_bank_size = serializers.IntegerField()
    communication_channels = serializers.ListField()


class SubmitAnswerInputSerializer(serializers.Serializer):
    """قرارداد ثبت پاسخ یک سوال در حین آزمون (شماره سوال ۱ تا ۵ و شماره گزینه ۱ تا ۴)."""

    question_number = serializers.IntegerField(min_value=1, max_value=50)
    selected_position = serializers.IntegerField(min_value=1, max_value=4)


class FinishExamInputSerializer(serializers.Serializer):
    """قرارداد درخواست پایان آزمون (با امکان ارسال اختیاری آرایه پاسخ‌ها)."""

    answers = SubmitAnswerInputSerializer(many=True, required=False)


class QuestionOptionSafeSerializer(serializers.Serializer):
    """گزینهٔ تصادفی‌شدهٔ سوال برای شرکت‌کننده (بدون افشای شناسهٔ اصلی یا صحیح بودن)."""

    position = serializers.IntegerField()
    text = serializers.CharField()


class ActiveAttemptQuestionSafeSerializer(serializers.Serializer):
    """سوال تخصیص‌یافته به شرکت‌کننده در حین آزمون (بدون افشای کلید)."""

    question_number = serializers.IntegerField()
    question_text = serializers.CharField()
    chapter = serializers.CharField()
    selected_position = serializers.IntegerField(allow_null=True)
    is_answered = serializers.BooleanField()
    options = QuestionOptionSafeSerializer(many=True)


class ActiveAttemptOutputSerializer(serializers.Serializer):
    """ساختار کامل جلسهٔ در حال اجرای آزمون برای شرکت‌کننده."""

    attempt_id = serializers.IntegerField()
    tracking_code = serializers.CharField()
    status = serializers.CharField()
    started_at = serializers.CharField()
    started_at_jalali = serializers.CharField()
    expires_at = serializers.CharField()
    remaining_seconds = serializers.IntegerField()
    duration_limit_seconds = serializers.IntegerField()
    total_questions = serializers.IntegerField()
    answered_count = serializers.IntegerField()
    unanswered_count = serializers.IntegerField()
    all_answered = serializers.BooleanField()
    current_question_number = serializers.IntegerField()
    questions = ActiveAttemptQuestionSafeSerializer(many=True)


class ReportCardOutputSerializer(serializers.Serializer):
    """ساختار کارنامهٔ نهایی شرکت‌کننده (فقط آمار کلی بدون افشای درست/غلط بودن تک‌تک سوالات)."""

    tracking_code = serializers.CharField()
    receipt_signature = serializers.CharField()
    participant = serializers.DictField()
    summary = serializers.DictField()
    thank_you_message = serializers.CharField()
    communication_channels = serializers.ListField()


class AdminQuestionOptionSerializer(serializers.ModelSerializer):
    """سریالایزر گزینهٔ سوال در بانک سوال مخصوص ادمین (شامل کلید صحیح `is_correct`)."""

    class Meta:
        model = QuestionOption
        fields = ["id", "option_number", "text", "is_correct"]
        read_only_fields = ["id"]


class AdminQuestionSerializer(serializers.ModelSerializer):
    """سریالایزر کامل سوال چهارگزینه‌ای در بانک سوال مخصوص ادمین."""

    options = AdminQuestionOptionSerializer(many=True)
    times_drawn = serializers.IntegerField(read_only=True, default=0)
    correct_answers_count = serializers.IntegerField(read_only=True, default=0)
    wrong_answers_count = serializers.IntegerField(read_only=True, default=0)
    unanswered_count_stat = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Question
        fields = [
            "id",
            "text",
            "chapter",
            "difficulty",
            "explanation",
            "is_active",
            "options",
            "times_drawn",
            "correct_answers_count",
            "wrong_answers_count",
            "unanswered_count_stat",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class AdminBulkQuestionInputSerializer(serializers.Serializer):
    """ورودی درج دسته‌ای سوالات چهارگزینه‌ای توسط ادمین."""

    questions = AdminQuestionSerializer(many=True)


class AdminExamConfigurationSerializer(serializers.ModelSerializer):
    """سریالایزر مشاهده و ویرایش کامل تنظیمات زندهٔ آزمون توسط ادمین."""

    window_state = serializers.SerializerMethodField()

    class Meta:
        model = ExamConfiguration
        fields = [
            "id",
            "title",
            "book_title",
            "organizer_name",
            "description",
            "starts_at",
            "ends_at",
            "is_manually_open",
            "window_state",
            "duration_seconds",
            "questions_per_attempt",
            "require_otp_before_exam",
            "points_per_correct",
            "points_per_wrong",
            "max_time_bonus",
            "thank_you_sms_enabled",
            "thank_you_sms_template",
            "communication_channels",
            "policy_version",
            "updated_at",
        ]
        read_only_fields = ["id", "window_state", "policy_version", "updated_at"]

    def get_window_state(self, obj: ExamConfiguration) -> str:
        """محاسبهٔ وضعیت فعلی پنجرهٔ زمانی."""
        return obj.resolve_window_state()

    def to_internal_value(self, data: Any) -> Any:
        """تبدیل ورودی به دیکشنری استاندارد."""
        return super().to_internal_value(data)

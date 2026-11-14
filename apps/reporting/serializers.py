"""سریالایزرهای گزارش‌گیری، آمار زنده و کاوشگر شرکت‌کنندگان برای پنل ادمین."""

from __future__ import annotations

from rest_framework import serializers


class AdminParticipantExplorerItemSerializer(serializers.Serializer):
    """ساختار خروجی هر سطر در کاوشگر چندفیلتره شرکت‌کنندگان برای قرعه‌کشی حضوری."""

    rank = serializers.IntegerField(allow_null=True)
    attempt_id = serializers.IntegerField()
    tracking_code = serializers.CharField()
    receipt_signature = serializers.CharField()
    user = serializers.DictField()
    mosque = serializers.DictField()
    exam = serializers.DictField()
    answers = serializers.ListField(required=False)


class AdminAnalyticsDashboardSerializer(serializers.Serializer):
    """ساختار خروجی داشبورد آماری زنده برای پنل ادمین."""

    overview = serializers.DictField()
    correct_count_distribution = serializers.DictField()
    age_groups_distribution = serializers.DictField()
    mosques_ranking_and_analytics = serializers.ListField()
    question_bank_analytics = serializers.ListField()


class AdminLotteryDrawInputSerializer(serializers.Serializer):
    """ورودی اجرای قرعه‌کشی زنده و قابل‌راستی‌آزمایی رمزنگاری‌شده با پشتیبانی از تمام فیلترها."""

    winners_count = serializers.IntegerField(min_value=1, max_value=100, default=3, required=False)
    reserves_count = serializers.IntegerField(min_value=0, max_value=50, default=2, required=False)
    ceremony_title = serializers.CharField(max_length=240, required=False, allow_blank=True)
    client_seed = serializers.CharField(max_length=120, required=False, allow_blank=True)
    mosque_ids = serializers.CharField(required=False, allow_blank=True)
    mosque_id = serializers.IntegerField(required=False, allow_null=True)
    exact_correct = serializers.IntegerField(required=False, allow_null=True)
    min_correct = serializers.IntegerField(required=False, allow_null=True)
    max_correct = serializers.IntegerField(required=False, allow_null=True)
    min_score = serializers.FloatField(required=False, allow_null=True)
    max_score = serializers.FloatField(required=False, allow_null=True)
    min_duration = serializers.IntegerField(required=False, allow_null=True)
    max_duration = serializers.IntegerField(required=False, allow_null=True)
    min_age = serializers.IntegerField(required=False, allow_null=True)
    max_age = serializers.IntegerField(required=False, allow_null=True)


class AdminLotteryDrawOutputSerializer(serializers.Serializer):
    """خروجی مراسم قرعه‌کشی زنده همراه با گواهی اثبات رمزنگاری‌شده SHA-256."""

    ceremony_title = serializers.CharField()
    drawn_at = serializers.CharField()
    drawn_at_jalali = serializers.CharField()
    eligible_pool_count = serializers.IntegerField()
    requested_winners_count = serializers.IntegerField()
    requested_reserves_count = serializers.IntegerField()
    drawn_winners_count = serializers.IntegerField()
    drawn_reserves_count = serializers.IntegerField()
    applied_filters = serializers.DictField()
    winners = serializers.ListField()
    reserves = serializers.ListField()
    cryptographic_proof = serializers.DictField()

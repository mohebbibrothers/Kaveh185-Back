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

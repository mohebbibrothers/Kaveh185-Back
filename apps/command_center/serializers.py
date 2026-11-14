"""سریالایزر خروجی مرکز فرماندهی یکپارچه ادمین."""

from __future__ import annotations

from rest_framework import serializers


class CommandCenterSnapshotSerializer(serializers.Serializer):
    """ساختار خروجی اسنپ‌شات ۳۶۰ درجه مرکز فرماندهی ادمین."""

    generated_at = serializers.CharField()
    generated_at_jalali = serializers.CharField()
    exam_status = serializers.DictField()
    overview = serializers.DictField()
    top_mosques = serializers.ListField()
    correct_count_distribution = serializers.DictField()
    age_groups_distribution = serializers.DictField()
    security_and_integrity = serializers.DictField()
    infrastructure_and_outbox = serializers.DictField()
    recent_audit_events = serializers.ListField()

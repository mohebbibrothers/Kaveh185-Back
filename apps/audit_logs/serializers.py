"""سریالایزرهای خروجی لاگ‌های حسابرسی و بررسی زنجیرهٔ هش."""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

from apps.core.jalali import format_jalali_datetime

from .models import AuditLog


class AuditLogSerializer(serializers.ModelSerializer):
    """نمایش کامل یک رکورد حسابرسی همراه با زمان شمسی."""

    created_at_jalali = serializers.SerializerMethodField()

    class Meta:
        model = AuditLog
        fields = [
            "id",
            "chain_index",
            "hash_version",
            "previous_hash",
            "event_hash",
            "user",
            "actor_label",
            "action",
            "resource_type",
            "resource_id",
            "reason",
            "ip_address",
            "user_agent",
            "path",
            "method",
            "request_id",
            "changes",
            "extra_data",
            "created_at",
            "created_at_jalali",
        ]

    def get_created_at_jalali(self, obj: AuditLog) -> str:
        """تبدیل زمان ایجاد به فرمت تاریخ و ساعت شمسی."""
        return format_jalali_datetime(obj.created_at)


class AuditChainVerificationSerializer(serializers.Serializer):
    """ساختار خروجی بررسی یکپارچگی زنجیرهٔ حسابرسی."""

    valid = serializers.BooleanField()
    checked_count = serializers.IntegerField()
    broken_at_index = serializers.IntegerField(allow_null=True)
    reason = serializers.CharField(allow_null=True)

    def to_representation(self, instance: dict[str, Any]) -> dict[str, Any]:
        """نمایش دیکشنری خروجی بررسی زنجیره."""
        return instance

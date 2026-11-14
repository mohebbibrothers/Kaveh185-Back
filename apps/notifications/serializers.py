"""سریالایزرهای لاگ ارسال پیامک و ارسال پیامک تستی/اطلاع‌رسانی."""

from __future__ import annotations

from rest_framework import serializers

from apps.authentication.validators import normalize_and_validate_phone

from .models import SMSDeliveryLog


class SMSDeliveryLogSerializer(serializers.ModelSerializer):
    """ساختار خروجی لاگ تحویل پیامک برای پنل ادمین."""

    class Meta:
        model = SMSDeliveryLog
        fields = [
            "id",
            "recipient_phone",
            "category",
            "provider",
            "message_text",
            "status",
            "provider_message_id",
            "error_message",
            "created_at",
        ]


class AdminSendTestSMSInputSerializer(serializers.Serializer):
    """قرارداد ارسال پیامک تستی یا اطلاع‌رسانی توسط ادمین."""

    recipient_phone = serializers.CharField(max_length=15)
    message_text = serializers.CharField(min_length=3, max_length=1000)

    def validate_recipient_phone(self, value: str) -> str:
        """نرمال‌سازی و اعتبارسنجی شماره موبایل گیرنده."""
        return normalize_and_validate_phone(value)

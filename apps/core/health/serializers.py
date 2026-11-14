"""سریالایزرهای مستندسازی OpenAPI برای مسیرهای بررسی سلامت (Health Checks)."""

from __future__ import annotations

from rest_framework import serializers


class BasicHealthSerializer(serializers.Serializer):
    """ساختار پاسخ سلامت پایه و Readiness."""

    status = serializers.CharField(default="healthy")
    service = serializers.CharField(default="kaveh185")


class DetailedHealthSerializer(serializers.Serializer):
    """ساختار پاسخ سلامت جامع زیرسیستم‌ها."""

    overall_status = serializers.CharField()
    service = serializers.CharField()
    checks = serializers.DictField()

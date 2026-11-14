"""پیکربندی پنل ادمین جنگو برای لاگ پیامک‌های ارسالی."""

from __future__ import annotations

from django.contrib import admin

from .models import SMSDeliveryLog


@admin.register(SMSDeliveryLog)
class SMSDeliveryLogAdmin(admin.ModelAdmin):
    """نمایش لاگ پیامک‌های ارسالی در پنل ادمین جنگو."""

    list_display = (
        "id",
        "recipient_phone",
        "category",
        "provider",
        "status",
        "provider_message_id",
        "created_at",
    )
    list_filter = ("category", "provider", "status")
    search_fields = ("recipient_phone", "message_text", "provider_message_id")
    readonly_fields = ("created_at", "updated_at")

"""پیکربندی فقط‌خواندنی پنل ادمین جنگو برای لاگ‌های حسابرسی."""

from __future__ import annotations

from typing import Any

from django.contrib import admin
from django.http import HttpRequest

from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    """نمایش تغییرناپذیر لاگ‌های حسابرسی در پنل ادمین."""

    list_display = (
        "chain_index",
        "action",
        "actor_label",
        "resource_type",
        "resource_id",
        "ip_address",
        "created_at",
    )
    list_filter = ("action", "resource_type")
    search_fields = ("actor_label", "resource_id", "request_id", "reason", "event_hash")
    readonly_fields = (
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
    )

    def has_add_permission(self, request: HttpRequest) -> bool:
        """مسدود کردن افزودن دستی لاگ در ادمین."""
        del request
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        """مسدود کردن ویرایش لاگ در ادمین."""
        del request, obj
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        """مسدود کردن حذف لاگ در ادمین."""
        del request, obj
        return False

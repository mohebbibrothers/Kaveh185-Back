"""پیکربندی پنل ادمین جنگو برای مدیریت مساجد حوزه ۱۸۵ شهید کاوه."""

from __future__ import annotations

from django.contrib import admin

from .models import Mosque


@admin.register(Mosque)
class MosqueAdmin(admin.ModelAdmin):
    """مدیریت مساجد در پنل ادمین جنگو."""

    list_display = (
        "display_order",
        "code",
        "name",
        "neighborhood",
        "completed_exam_count",
        "registered_count",
        "target_participants",
        "is_active",
    )
    list_filter = ("is_active",)
    search_fields = ("code", "name", "neighborhood", "imam_name", "commander_name")
    ordering = ("display_order", "id")

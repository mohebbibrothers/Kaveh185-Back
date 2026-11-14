"""پیکربندی پنل ادمین جنگو برای مدل‌های زیرساختی `apps.core`."""

from __future__ import annotations

from django.contrib import admin

from .models import CacheInvalidationEvent, IdempotencyKey, OutboxMessage


@admin.register(CacheInvalidationEvent)
class CacheInvalidationEventAdmin(admin.ModelAdmin):
    """مدیریت رخدادهای ابطال کش در پنل ادمین جنگو."""

    list_display = ("id", "domain", "status", "attempts", "reason", "created_at", "processed_at")
    list_filter = ("domain", "status")
    search_fields = ("domain", "reason", "last_error")
    readonly_fields = ("created_at", "updated_at", "processed_at")


@admin.register(IdempotencyKey)
class IdempotencyKeyAdmin(admin.ModelAdmin):
    """مدیریت کلیدهای هم‌توانی (`Idempotency-Key`) در پنل ادمین."""

    list_display = (
        "id",
        "scope",
        "key",
        "actor_ref",
        "response_status",
        "expires_at",
        "created_at",
    )
    list_filter = ("scope", "response_status")
    search_fields = ("key", "scope", "actor_ref")
    readonly_fields = ("created_at", "updated_at")


@admin.register(OutboxMessage)
class OutboxMessageAdmin(admin.ModelAdmin):
    """مدیریت پیام‌های Transactional Outbox در پنل ادمین."""

    list_display = (
        "id",
        "topic",
        "recipient",
        "status",
        "attempts",
        "scheduled_at",
        "processed_at",
    )
    list_filter = ("topic", "status")
    search_fields = ("recipient", "topic", "last_error")
    readonly_fields = ("created_at", "updated_at", "processed_at")

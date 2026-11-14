"""پیکربندی اپلیکیشن حسابرسی و فارنزیک (`apps.audit_logs`)."""

from __future__ import annotations

from django.apps import AppConfig


class AuditLogsConfig(AppConfig):
    """پیکربندی اپلیکیشن زنجیرهٔ لاگ‌های حسابرسی."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.audit_logs"
    verbose_name = "لاگ‌های حسابرسی و فارنزیک"

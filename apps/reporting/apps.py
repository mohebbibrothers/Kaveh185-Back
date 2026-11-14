"""پیکربندی اپلیکیشن گزارش‌گیری و قرعه‌کشی (`apps.reporting`)."""

from __future__ import annotations

from django.apps import AppConfig


class ReportingConfig(AppConfig):
    """پیکربندی اپلیکیشن گزارش‌های آماری، کاوشگر شرکت‌کنندگان و خروجی اکسل."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.reporting"
    verbose_name = "گزارش‌گیری، آمار و قرعه‌کشی"

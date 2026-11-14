"""پیکربندی اپلیکیشن مرکز فرماندهی ادمین (`apps.command_center`)."""

from __future__ import annotations

from django.apps import AppConfig


class CommandCenterConfig(AppConfig):
    """پیکربندی اپلیکیشن خلاصهٔ عملیاتی یکپارچهٔ پنل مدیریت."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.command_center"
    verbose_name = "مرکز فرماندهی ادمین"

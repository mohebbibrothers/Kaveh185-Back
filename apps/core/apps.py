"""App configuration for the core infrastructure module."""

from __future__ import annotations

from django.apps import AppConfig


class CoreConfig(AppConfig):
    """پیکربندی اپلیکیشن زیرساخت مشترک (Core)."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.core"
    verbose_name = "زیرساخت مشترک"

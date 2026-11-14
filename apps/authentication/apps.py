"""پیکربندی اپلیکیشن احراز هویت و کاربران (`apps.authentication`)."""

from __future__ import annotations

from django.apps import AppConfig


class AuthenticationConfig(AppConfig):
    """پیکربندی اپلیکیشن احراز هویت و هویت شرکت‌کنندگان."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.authentication"
    verbose_name = "احراز هویت و کاربران"

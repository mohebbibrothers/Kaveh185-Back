"""پیکربندی اپلیکیشن موتور آزمون (`apps.exam`)."""

from __future__ import annotations

from django.apps import AppConfig


class ExamConfig(AppConfig):
    """پیکربندی اپلیکیشن بانک سوال، اجرای آزمون و کارنامه."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.exam"
    verbose_name = "موتور آزمون و بانک سوال"

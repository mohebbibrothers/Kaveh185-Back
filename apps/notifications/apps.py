"""پیکربندی اپلیکیشن اطلاع‌رسانی پیامکی (`apps.notifications`)."""

from __future__ import annotations

from django.apps import AppConfig


class NotificationsConfig(AppConfig):
    """پیکربندی اپلیکیشن درگاه پیامکی و لاگ ارسال پیامک‌ها."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.notifications"
    verbose_name = "اطلاع‌رسانی و درگاه پیامک"

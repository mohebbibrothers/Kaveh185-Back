"""پیکربندی اپلیکیشن مساجد (`apps.mosques`)."""

from __future__ import annotations

from django.apps import AppConfig


class MosquesConfig(AppConfig):
    """پیکربندی اپلیکیشن مدیریت مساجد و رتبه‌بندی مشارکت."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.mosques"
    verbose_name = "مساجد و رتبه‌بندی مشارکت"

    def ready(self) -> None:
        """اتصالِ سیگنال‌های هم‌گام‌سازیِ شمارنده (بندِ `signals.py`)."""
        from . import signals  # noqa: F401  # ثبتِ receiver‌ها

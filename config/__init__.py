"""پکیج پیکربندی مرکزی پروژه جنگو سامانه کاوه ۱۸۵."""

from __future__ import annotations

from .celery import app as celery_app

__all__ = ("celery_app",)

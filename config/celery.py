"""پیکربندی Celery برای پردازش ناهمگام صف Outbox، ارسال پیامک‌ها و وظایف زمان‌بندی‌شده."""

from __future__ import annotations

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

app = Celery("kaveh185")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

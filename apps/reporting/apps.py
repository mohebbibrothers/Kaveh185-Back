"""پیکربندی اپلیکیشن گزارش‌گیری و قرعه‌کشی (`apps.reporting`).

⚠️ تاریخچهٔ کوچک اما مهم: در نسخهٔ اولِ دورِ ۵۱، مسیرِ صفحهٔ «رتبه‌بندی» با
monkeypatch کردنِ `admin.site.get_urls` در `ready()` وصل می‌شد. روی محیطِ
توسعه کار می‌کرد، ولی روی هاست **۴۰۴** داد: ترتیبِ بار‌شدنِ `ready()`
قطعی نیست و اگر `django.contrib.admin` بعد از این اپ آماده می‌شد، یا جنگو
`get_urls` را در نقطهٔ دیگری کش کرده بود، مسیر وجود نداشت. حالا مسیر
**مستقیم در `config/urls.py`** فهرست شده است — یک خطِ صریح که هیچ وابستگی
به ترتیبِ بار‌شدن ندارد.
"""

from __future__ import annotations

from django.apps import AppConfig


class ReportingConfig(AppConfig):
    """پیکربندی اپلیکیشن گزارش‌های آماری، کاوشگر شرکت‌کنندگان و خروجی اکسل."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.reporting"
    verbose_name = "گزارش‌گیری، آمار و قرعه‌کشی"

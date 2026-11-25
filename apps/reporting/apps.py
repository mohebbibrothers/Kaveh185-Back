"""پیکربندی اپلیکیشن گزارش‌گیری و قرعه‌کشی (`apps.reporting`)."""

from __future__ import annotations

from typing import Any

from django.apps import AppConfig


class ReportingConfig(AppConfig):
    """پیکربندی اپلیکیشن گزارش‌های آماری، کاوشگر شرکت‌کنندگان و خروجی اکسل."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.reporting"
    verbose_name = "گزارش‌گیری، آمار و قرعه‌کشی"

    def ready(self) -> None:
        """اتصالِ صفحهٔ «رتبه‌بندی شرکت‌کنندگان» به پنل ادمین، بی‌آنکه `urls.py` دست بخورد.

        چرا این‌جا و نه در `urls.py`؟ چون الگوی `admin.site.urls` یک بار
        گرفته می‌شود و ترتیبِ includeها شکننده است. با `get_urls`، مسیر در
        همان فضای نامِ `admin:` می‌نشیند و `reverse("admin:participant-ranking")`
        همه‌جا کار می‌کند — همان چیزی که لینکِ صفحهٔ اولِ ادمین لازم دارد.
        """
        from django.contrib import admin

        from .ranking_admin import get_ranking_urls

        original_get_urls = admin.site.get_urls

        if getattr(admin.site, "_k185_ranking_attached", False):
            return

        def patched_get_urls() -> list[Any]:
            return get_ranking_urls() + original_get_urls()

        admin.site.get_urls = patched_get_urls  # type: ignore[method-assign]
        admin.site._k185_ranking_attached = True  # type: ignore[attr-defined]

        # میان‌بر در صفحهٔ اولِ ادمین: کارتِ «رتبه‌بندی» بالای فهرستِ مدل‌ها.
        # الگوی خودِ جنگو به ارث می‌رود، پس با ارتقای جنگو نمی‌شکند.
        admin.site.index_template = "admin/k185_index.html"

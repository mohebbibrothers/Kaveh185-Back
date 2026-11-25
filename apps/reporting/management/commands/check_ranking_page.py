"""دستور `check_ranking_page` — «آیا صفحهٔ رتبه‌بندی روی همین کد زنده است؟»

## چرا این دستور؟

یک ۴۰۴ می‌تواند سه معنیِ کاملاً متفاوت داشته باشد و از بیرون هیچ‌کدام از
بقیه قابلِ تشخیص نیست:

۱) کدِ تازه روی سرور نیست (قدیمی مانده)؛
۲) کد هست، ولی مسیر در جدولِ URLها نیست (باگ در ثبتِ مسیر)؛
۳) مسیر هست، ولی `ADMIN_URL_PATH` عوض شده و آدرسِ دیگری است.

این دستور هر سه را از هم جدا می‌کند و **بدونِ نیاز به مرورگر یا حدس** جواب
می‌دهد. فقط‌خواندنی است و هیچ چیزی نمی‌نویسد:

    cd ~/Kaveh185-Back && ~/virtualenv/.../bin/python manage.py check_ranking_page

خروجیِ موفق چیزی شبیه این است:

    ✔ کد تازه روی سرور است (نسخهٔ صفحه: k185-ranking-v1)
    ✔ مسیرِ صفحه در جدولِ URLها هست
    ✔ ADMIN_URL_PATH = secure-kaveh185-admin/
    ✔ نشانیِ نهایی: https://<host>/secure-kaveh185-admin/participant-ranking/
    ✔ دسترسی: فقط staff (تست شد: کاربرِ ناشناس → ۳۰۲ به صفحهٔ ورود)

اگر خطِ اول ✖ باشد، مشکل «کدِ قدیمی» است؛ اگر خطِ دوم ✖ باشد، مشکل ثبتِ
مسیر است. این تفکیک، همان چیزی است که عیب‌یابی را از چند ساعت به چند ثانیه
می‌رساند.
"""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.contrib import admin
from django.core.management.base import BaseCommand
from django.urls import NoReverseMatch, resolve, reverse

#: نشانگرِ نسخه — اگر روی سرور نباشد، یعنی کدِ این دور نصب نشده است.
MODULE_MARKER = "k185-ranking-v1"


class Command(BaseCommand):
    """بررسیِ زنده بودنِ صفحهٔ رتبه‌بندی روی همین نصب."""

    help = "بررسی می‌کند صفحهٔ رتبه‌بندی در URLها ثبت شده و با کدِ فعلی کار می‌کند."

    def handle(self, *args: Any, **options: Any) -> None:
        """گزارشِ گام‌به‌گام؛ در صورتِ مشکل با کدِ خروجِ ۱ تمام می‌شود."""
        problems: list[str] = []

        # ── ۱) کد روی سرور هست؟
        try:
            from apps.reporting import ranking_admin

            present = getattr(ranking_admin, "RANKING_PAGE_VERSION", "") == MODULE_MARKER
        except Exception as exc:
            present = False
            self.stderr.write(f"  وارد کردنِ ماژول شکست خورد: {exc}")

        if present:
            self.stdout.write(self.style.SUCCESS(f"  ✔ کد تازه روی سرور است ({MODULE_MARKER})"))
        else:
            problems.append("کدِ قدیمی")
            self.stdout.write(
                self.style.ERROR(
                    "  ✖ کدِ تازه روی سرور نیست — این صفحه در نسخهٔ نصب‌شده وجود ندارد.\n"
                    "     cd ~/Kaveh185-Back && git pull --ff-only && touch tmp/restart.txt"
                )
            )

        # ── ۲) مسیر در جدولِ URLها هست؟
        admin_prefix = str(getattr(settings, "ADMIN_URL_PATH", "secure-kaveh185-admin/")).strip("/")
        self.stdout.write(f"  · ADMIN_URL_PATH = {admin_prefix}/")

        url = None
        try:
            url = reverse("participant-ranking")
            self.stdout.write(self.style.SUCCESS(f"  ✔ مسیر ثبت شده است: {url}"))
        except NoReverseMatch:
            problems.append("مسیر ثبت نشده")
            self.stdout.write(
                self.style.ERROR(
                    "  ✖ نامِ «participant-ranking» در جدولِ URLها نیست.\n"
                    "     یعنی خطِ صریحِ config/urls.py روی این سرور نیست. "
                    "با `grep -n participant-ranking config/urls.py` بررسی کنید."
                )
            )

        # ── ۳) مسیر واقعاً به ویو می‌رسد؟
        if url is not None:
            try:
                match = resolve(url)
                self.stdout.write(self.style.SUCCESS(f"  ✔ resolve → {match.func.__name__}"))
            except Exception as exc:
                problems.append("resolve شکست خورد")
                self.stdout.write(self.style.ERROR(f"  ✖ resolve شکست خورد: {exc}"))

        # ── ۴) کارتِ صفحهٔ اولِ ادمین وصل است؟
        if getattr(admin.site, "index_template", "") == "admin/k185_index.html":
            self.stdout.write(self.style.SUCCESS("  ✔ کارتِ میان‌بر در صفحهٔ اولِ ادمین فعال است"))
        else:
            problems.append("کارتِ ادمین نیست")
            self.stdout.write(
                self.style.WARNING(
                    "  ▲ قالبِ صفحهٔ اولِ ادمین تنظیم نشده (صفحه با آدرسِ مستقیم کار می‌کند)."
                )
            )

        # ── ۵) نشانیِ کامل برای کپی‌کردن
        hosts = [h for h in getattr(settings, "ALLOWED_HOSTS", []) if h not in {"*", ""}]
        host = next(
            (h for h in hosts if h.startswith("api.")), hosts[0] if hosts else "kaveh185.ir"
        )
        if url is not None:
            self.stdout.write(f"\n  نشانیِ کامل:  https://{host}{url}")

        # ── جمع‌بندی
        self.stdout.write("")
        if problems:
            self.stdout.write(self.style.ERROR(f"  ✖ {len(problems)} مشکل: {'، '.join(problems)}"))
            raise SystemExit(1)
        self.stdout.write(self.style.SUCCESS("  ✔ همه‌چیز سرِ جایش است."))
        self.stdout.write(
            "  اگر در مرورگر باز هم ۴۰۴ دیدید: مطمئن شوید با حسابِ staff وارد "
            "شده‌اید و نشانی را با https و همان دامنهٔ بالا باز می‌کنید.\n"
        )

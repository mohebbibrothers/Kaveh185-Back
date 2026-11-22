"""دستور `recount_mosque_stats` — بازشمارشِ شمارنده‌های مساجد از دادهٔ واقعی.

چه وقت لازم است؟
* بعد از پاک‌سازیِ دستیِ داده یا حذفِ گروهی در پنل ادمین.
* بعد از هر مهاجرت/اسکریپت که کاربر اضافه/حذف می‌کند.
* دوره‌ای، به‌عنوانِ تورِ ایمنی (در `keepalive` هم صدا زده می‌شود).

حالتِ پیش‌فرض **فقط گزارش** است؛ با `--fix` می‌نویسد. این تفکیک عمدی است:
اپراتوری که فقط می‌خواهد بداند «چقدر خرابی هست» نباید ناخواسته داده را
دستکاری کند.
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandParser

from apps.mosques.models import Mosque
from apps.mosques.services import (
    live_completed_exam_count,
    live_registered_count,
    recount_mosque_stats,
)


class Command(BaseCommand):
    """مقایسهٔ شمارنده‌های ذخیره‌شده با شمارشِ زنده و (با `--fix`) اصلاحِ آن‌ها."""

    help = "بازشمارشِ registered_count و completed_exam_count مساجد از دادهٔ واقعی."

    def add_arguments(self, parser: CommandParser) -> None:
        """گزینه‌های خطِ فرمان."""
        parser.add_argument(
            "--fix",
            action="store_true",
            help="مقادیرِ نادرست را بنویس (بدونِ این، فقط گزارش).",
        )
        parser.add_argument(
            "--quiet",
            action="store_true",
            help="فقط خطِ خلاصه (برای کران/keepalive).",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        """گزارشِ انحراف‌ها و اصلاحِ اختیاری."""
        quiet = bool(options.get("quiet"))
        rows: list[tuple[str, str, int, int]] = []
        for mosque in Mosque.all_objects.order_by("display_order", "name").only(
            "id", "code", "name", "registered_count", "completed_exam_count", "is_active"
        ):
            live_reg = live_registered_count(mosque.pk)
            live_done = live_completed_exam_count(mosque.pk)
            if live_reg != mosque.registered_count or live_done != mosque.completed_exam_count:
                rows.append((mosque.code, mosque.name, mosque.registered_count, live_reg))
                if not quiet:
                    flag = "" if mosque.is_active else " (غیرفعال)"
                    self.stdout.write(
                        f"  {mosque.code:<10} {mosque.name[:34]:<34}{flag}\n"
                        f"    ثبت‌نام: ذخیره={mosque.registered_count} → زنده={live_reg}\n"
                        f"    تکمیل  : ذخیره={mosque.completed_exam_count} → زنده={live_done}"
                    )

        if not rows:
            self.stdout.write(self.style.SUCCESS("✔ همهٔ شمارنده‌ها با دادهٔ واقعی هم‌خوان‌اند."))
            return

        if not options.get("fix"):
            self.stdout.write("")
            self.stdout.write(
                self.style.WARNING(
                    f"⚠ {len(rows)} مسجد شمارندهٔ نادرست دارد. برای اصلاح: "
                    "`manage.py recount_mosque_stats --fix`"
                )
            )
            return

        result = recount_mosque_stats()
        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                f"✔ اصلاح شد: {result['fixed']} از {result['checked']} مسجد بازشمارش شد."
            )
        )

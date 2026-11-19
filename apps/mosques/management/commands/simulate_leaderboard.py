"""شبیه‌سازیِ کاملِ جدولِ رتبه‌بندی مساجد — برای تستِ واقعیِ صفحهٔ رتبه‌بندی.

چرا این دستور؟ «تستِ جدول» دو جور ممکن است:

  ۱) **ساختِ کارنامه‌های واقعی** (ثبت‌نام → آزمون → ارسال). دقیق است ولی
     کند و شلوغ است: ۵۰ کارنامه یعنی ۵۰ کاربر، ۵۰ سری پرسش و ۵۰ رسید.
  ۲) **افزایشِ شمارنده‌های انبارشدهٔ مسجد.** همان چیزی که موتورِ آزمون در
     پایانِ هر کارنامه انجام می‌دهد (`increment_mosque_completed_exam_count`)
     و کشِ رتبه‌بندی را هم همان لحظه باطل می‌کند. سریع، برگشت‌پذیر و
     **دقیقاً همان مسیری** که در عمل جدول را تغییر می‌دهد.

این دستور راهِ دوم را می‌رود، با سه تضمین:

  • **محافظِ محیط:** اگر `DEBUG=False` باشد اجرا نمی‌شود (مگر با `--force`)؛
    هرگز روی سایتِ واقعی با دادهٔ واقعی دست نمی‌برد.
  • **سناریوهای آماده:** `realistic` (پیش‌فرض)، `zeros` (شروعِ صفر)،
    `tie` (تساویِ کامل برای تستِ الفبا و رتبهٔ مشترک)، `crowded` (رقابتِ نزدیک).
  • **`--reset`:** شمارنده‌ها را صفر می‌کند تا صفحه به حالتِ «خطِ شروع» برگردد.

نمونه‌ها::

    python manage.py simulate_leaderboard                  # سناریوی واقع‌گرایانه
    python manage.py simulate_leaderboard --scenario tie
    python manage.py simulate_leaderboard --scenario crowded --reset
    python manage.py simulate_leaderboard --list           # فهرستِ سناریوها
    python manage.py simulate_leaderboard --reset          # فقط صفرکردن
"""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError, CommandParser

from apps.mosques.models import Mosque
from apps.mosques.services import increment_mosque_completed_exam_count

# ═══ سناریوها ═══════════════════════════════════════════════════════════════
# هر سناریو یک تابعِ «توزیع» است: به هر مسجد (به ترتیبِ نمایش) تعدادی
# شرکت‌کنندهٔ کامل می‌دهد. اعداد عمداً طوری چیده شده‌اند که **همهٔ حالت‌های
# نمایشی** جدول دیده شود: صدرِ جدول، تساوی، اختلافِ نزدیک، صفرها و رتبهٔ مشترک.
SCENARIOS: dict[str, dict[str, Any]] = {
    "realistic": {
        "help": "رقابتِ زنده با اختلاف‌های طبیعی + چند مسجدِ بی‌مشارکت",
        "counts": [14, 11, 11, 8, 8, 3, 3, 3, 1, 0, 0, 0, 0, 0, 0, 0, 0],
    },
    "crowded": {
        "help": "همه در یک قدمیِ هم — نوارهای سهم کوتاه و نزدیک",
        "counts": [6, 6, 5, 5, 5, 4, 4, 4, 4, 3, 3, 3, 2, 2, 2, 1, 1],
    },
    "tie": {
        "help": "تساویِ گسترده — تستِ الفبای فارسی و رتبهٔ مشترک",
        "counts": [5, 5, 5, 5, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    },
    "top-three": {
        "help": "فقط سه مسجدِ صدر — تستِ سکو و مدال‌ها",
        "counts": [9, 4, 4, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    },
    "single": {
        "help": "یک مسجدِ پیشتاز — تستِ پیامِ پیشتاز بدونِ نفرِ دوم",
        "counts": [3, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    },
    "zeros": {
        "help": "هیچ مشارکتی — تستِ حالتِ «خطِ شروع»",
        "counts": [0] * 17,
    },
}


class Command(BaseCommand):
    """پرکردنِ شمارنده‌های مساجد برای دیدنِ جدولِ رتبه‌بندی در حالت‌های مختلف."""

    help = "شبیه‌سازیِ مشارکتِ مساجد برای تستِ صفحهٔ رتبه‌بندی (فقط محیطِ توسعه)"

    def add_arguments(self, parser: CommandParser) -> None:
        """تعریفِ گزینه‌های خط فرمان."""
        parser.add_argument(
            "--scenario",
            default="realistic",
            help="نامِ سناریو (پیش‌فرض: realistic). با --list ببینید.",
        )
        parser.add_argument(
            "--reset",
            action="store_true",
            help="همهٔ شمارنده‌ها را صفر کن (قبل یا بعد از ساختِ سناریو).",
        )
        parser.add_argument(
            "--only-reset",
            action="store_true",
            help="فقط صفر کن و سناریویی نساز.",
        )
        parser.add_argument(
            "--list",
            action="store_true",
            help="فهرستِ سناریوهای آماده و تعدادشان.",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="اجرا حتی وقتی DEBUG=False (⚠️ روی دادهٔ واقعی).",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        """اجرای سناریوی انتخاب‌شده."""
        del args

        if options["list"]:
            self.stdout.write("سناریوهای آماده:")
            for name, meta in SCENARIOS.items():
                total = sum(meta["counts"])
                self.stdout.write(f"  • {name:12s} — {meta['help']}  (مجموع: {total} شرکت‌کننده)")
            return

        if not settings.DEBUG and not options["force"]:
            raise CommandError(
                "این دستور دادهٔ آماری می‌سازد و روی محیطِ واقعی اجرا نمی‌شود. "
                "اگر واقعاً می‌خواهید، --force بدهید."
            )

        mosques = list(Mosque.objects.filter(is_active=True).order_by("display_order", "id"))
        if not mosques:
            raise CommandError("هیچ مسجدِ فعالی نیست. اول: python manage.py seed_mosques")

        if options["reset"] or options["only_reset"]:
            Mosque.objects.update(completed_exam_count=0, registered_count=0)
            self.stdout.write(self.style.WARNING("همهٔ شمارنده‌ها صفر شد."))
            from apps.core.cache_invalidation import invalidate_domain_cache

            invalidate_domain_cache("mosques", reason="simulate_leaderboard:reset")
            if options["only_reset"]:
                self.stdout.write(self.style.SUCCESS("جدول به «خطِ شروع» برگشت."))
                return

        name = str(options["scenario"])
        scenario = SCENARIOS.get(name)
        if scenario is None:
            raise CommandError(f"سناریوی «{name}» وجود ندارد. با --list فهرست را ببینید.")

        counts: list[int] = list(scenario["counts"])
        if len(counts) != len(mosques):
            # اگر تعدادِ مساجد با سناریو یکی نبود، توزیعِ مشابه و **قطعی**
            # می‌سازیم (بدونِ تصادف: یک الگوی نزولیِ تکرارشونده). تصادفی‌بودن
            # اینجا هیچ ارزشی ندارد و اجرای دوباره را غیرقابلِ بازتولید می‌کند.
            pattern = [14, 11, 8, 5, 3, 2, 1, 0]
            counts = [pattern[i % len(pattern)] for i in range(len(mosques))]
            counts.sort(reverse=True)

        # شمارنده‌ها را می‌نویسیم — از همان سرویسِ واقعیِ موتورِ آزمون، تا کش
        # رتبه‌بندی هم لحظه‌ای باطل شود و صفحه بدونِ انتظار عددِ تازه ببیند.
        for mosque, count in zip(mosques, counts, strict=False):
            for _ in range(int(count)):
                increment_mosque_completed_exam_count(mosque.id)
            if count:
                Mosque.objects.filter(pk=mosque.id).update(
                    registered_count=count + (count // 4) + 1
                )

        total = sum(counts)
        self.stdout.write(
            self.style.SUCCESS(
                f"سناریوی «{name}» ساخته شد — {total} شرکت‌کننده در {len(mosques)} مسجد."
            )
        )
        self.stdout.write("حالا صفحهٔ /mosques را باز کنید (یا دکمهٔ تازه‌سازی مرورگر).")

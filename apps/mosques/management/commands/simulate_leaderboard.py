"""شبیه‌سازیِ کاملِ جدولِ رتبه‌بندی مساجد — برای تستِ واقعیِ صفحهٔ رتبه‌بندی.

چرا این دستور؟ «تستِ جدول» دو جور ممکن است:

  ۱) **ساختِ کارنامه‌های واقعی** (ثبت‌نام → آزمون → ارسال). دقیق است ولی
     کند و شلوغ است: ۵۰ کارنامه یعنی ۵۰ کاربر، ۵۰ سری پرسش و ۵۰ رسید.
  ۲) **افزایشِ شمارنده‌های انبارشدهٔ مسجد.** سریع بود، ولی **غلط از آب درآمد**:
     جدول اکنون از شمارشِ زندهٔ کارنامه‌ها می‌خواند (شمارنده فقط کشِ کارایی
     است)، پس بالا بردنِ آن عدد هیچ ردیفی را در جدول تکان نمی‌داد — و بدتر،
     بعد از آن هر «بازشماری» اعدادِ قلابی را پاک می‌کرد و ادمین فکر می‌کرد
     باگ دارد.

این دستور راهِ اول را می‌رود: **دادهٔ واقعی** (کاربرِ آزمایشی + کارنامهٔ
پایان‌یافته) می‌سازد، با سه تضمین:

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
    python manage.py simulate_leaderboard --purge           # پاک‌کردنِ دادهٔ شبیه‌سازی
    python manage.py simulate_leaderboard --recount        # بازشماری از کارنامه‌های واقعی
    python manage.py simulate_leaderboard --dry-run        # فقط نشان بده چه می‌شود
"""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db import transaction

from apps.mosques.models import Mosque

#: پیشوندِ شمارهٔ کاربرانِ ساختگی؛ تنها راهِ مطمئنِ جدا کردنِ دادهٔ شبیه‌سازی از
#: دادهٔ واقعی. عمداً داخلِ بازهٔ شماره‌های معتبر است تا هیچ اعتبارسنجی‌ای نشکند،
#: ولی هیچ انسانِ واقعی‌ای آن را ندارد (۰۹۹۰).
FAKE_PHONE_PREFIX = "0990"
FAKE_TRACKING_PREFIX = "SIM-"

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
            "--recount",
            action="store_true",
            help=(
                "شمارنده‌ها را از کارنامه‌های واقعیِ پایان‌یافته دوباره بساز "
                "(بازگرداندنِ جدول به حالتِ اولیه پس از شبیه‌سازی)."
            ),
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="فقط نشان بده چه چیزی تغییر می‌کند؛ چیزی ننویس.",
        )
        parser.add_argument(
            "--list",
            action="store_true",
            help="فهرستِ سناریوهای آماده و تعدادشان.",
        )
        parser.add_argument(
            "--purge",
            action="store_true",
            help="همهٔ دادهٔ شبیه‌سازی‌شده (کاربرانِ ۰۹۹۰ و کارنامه‌هایشان) را پاک کن.",
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

        if options["purge"]:
            self._purge(dry_run=bool(options["dry_run"]))
            return

        if options["recount"]:
            self._recount(dry_run=bool(options["dry_run"]))
            return

        if options["reset"] or options["only_reset"]:
            # «صفرکردن» یعنی پاک‌کردنِ دادهٔ شبیه‌سازی، نه صفرکردنِ یک شمارندهٔ
            # آماری — وگرنه جدول (که از دادهٔ زنده می‌خواند) تغییری نمی‌دید.
            self._purge(dry_run=bool(options["dry_run"]))
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

        # ── ساختِ دادهٔ **واقعی** ─────────────────────────────────────────
        # برای هر «شرکت‌کنندهٔ کامل» یک کاربرِ آزمایشی + یک کارنامهٔ پایان‌یافته
        # می‌سازیم. جدول از همین کارنامه‌ها می‌خواند، پس عددی که ادمین می‌بیند
        # دقیقاً همان چیزی است که اتفاق افتاده — نه یک شمارندهٔ قلابی.
        created_users = 0
        created_attempts = 0
        if not options["dry_run"]:
            from apps.exam.services import create_simulated_finished_attempt

            for mosque, count in zip(mosques, counts, strict=False):
                for _ in range(int(count)):
                    create_simulated_finished_attempt(mosque=mosque)
                    created_users += 1
                    created_attempts += 1

        total = sum(counts)
        if options["dry_run"]:
            self.stdout.write(
                self.style.WARNING(
                    f"حالتِ آزمایشی: {total} کاربر و کارنامه ساخته می‌شد؛ چیزی نوشته نشد."
                )
            )
            return
        self.stdout.write(
            self.style.SUCCESS(
                f"سناریوی «{name}» ساخته شد — {created_attempts} کارنامهٔ واقعی "
                f"({created_users} کاربرِ آزمایشی) در {len(mosques)} مسجد."
            )
        )
        self.stdout.write("حالا صفحهٔ /mosques را باز کنید (یا دکمهٔ تازه‌سازی مرورگر).")
        self.stdout.write(
            self.style.WARNING(
                "برای پاک‌کردنِ کاملِ این دادهٔ آزمایشی: python manage.py simulate_leaderboard --purge"
            )
        )

    def _purge(self, *, dry_run: bool) -> None:
        """پاک‌کردنِ همان چیزی که این دستور ساخت — و هیچ‌چیزِ دیگر.

        چرا با پیشوندِ شماره؟ چون تنها نشانهٔ قطعیِ «ساختگی بودن» همین است.
        حذف بر اساسِ تاریخِ ایجاد یا نقش، می‌توانست دادهٔ واقعی را هم ببرد؛
        حذف بر اساسِ پیشوندِ ۰۹۹۰ هیچ کاربرِ واقعی‌ای را لمس نمی‌کند.
        """
        from apps.authentication.models import User
        from apps.exam.models import ExamAttempt

        fakes = User.objects.filter(phone_number__startswith=FAKE_PHONE_PREFIX)
        count_users = fakes.count()
        count_attempts = ExamAttempt.objects.filter(
            tracking_code__startswith=FAKE_TRACKING_PREFIX
        ).count()

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f"حالتِ آزمایشی: {count_users} کاربر و {count_attempts} کارنامه حذف می‌شد."
                )
            )
            return

        with transaction.atomic():
            ExamAttempt.objects.filter(tracking_code__startswith=FAKE_TRACKING_PREFIX).delete()
            # سیگنال‌های حذف، شمارندهٔ مساجد را خودشان هم‌گام می‌کنند.
            fakes.delete()

        self.stdout.write(
            self.style.SUCCESS(
                f"پاک شد: {count_users} کاربرِ آزمایشی و {count_attempts} کارنامه. "
                "جدول اکنون فقط دادهٔ واقعی را نشان می‌دهد."
            )
        )

    def _recount(self, *, dry_run: bool) -> None:
        """شمارنده‌های هر مسجد را از **منبعِ حقیقت** (کارنامه‌ها) از نو می‌سازد.

        چرا لازم است؟ شبیه‌سازی شمارنده‌های انبارشده را بالا می‌برد
        (`completed_exam_count` و `registered_count`) و بعد از تست، آمارِ جدول
        دیگر واقعی نیست. صفرکردن هم پاسخ درست نیست: اگر مسابقه واقعاً در جریان
        باشد، صفر اعدادِ واقعی را می‌سوزاند. راهِ درست: همان کاری که موتورِ
        آزمون در لحظه انجام می‌دهد — شمارش از `ExamAttempt`ها.
        """
        from django.db.models import Count

        from apps.exam.choices import ExamAttemptStatus
        from apps.exam.models import ExamAttempt

        # ── منبعِ حقیقت: کارنامه‌های پایان‌یافته → «شرکت‌کنندهٔ کامل»
        completed_rows = (
            ExamAttempt.objects.filter(status=ExamAttemptStatus.COMPLETED)
            .values("mosque_id")
            .annotate(n=Count("id"))
        )
        completed = {row["mosque_id"]: int(row["n"]) for row in completed_rows}

        # ── «ثبت‌نامی»: کسانی که این مسجد را انتخاب کرده‌اند — همان تعریفی که
        #    خودِ جدول به کار می‌برد (شرکت‌کنندهٔ فعال با نقشِ participant)،
        #    نه تعدادِ کارنامه‌ها. اگر تعریف یکی نباشد، عددِ ستونِ «ثبت‌نامی»
        #    بعد از بازشماری با عددی که جدول نشان می‌دهد یکی نمی‌شود.
        from apps.authentication.choices import UserRole
        from apps.authentication.models import User

        registered = {
            row["mosque_id"]: int(row["n"])
            for row in User.objects.filter(
                is_active=True, role=UserRole.PARTICIPANT, mosque__isnull=False
            )
            .values("mosque_id")
            .annotate(n=Count("id"))
        }

        changes: list[str] = []
        for mosque in Mosque.objects.filter(is_active=True).order_by("display_order", "id"):
            new_completed = completed.get(mosque.pk, 0)
            new_registered = max(registered.get(mosque.pk, 0), new_completed)
            if (
                new_completed == mosque.completed_exam_count
                and new_registered == mosque.registered_count
            ):
                continue
            changes.append(
                f"  • {mosque.code}: کامل {mosque.completed_exam_count} → {new_completed}"
                f" · ثبت‌نامی {mosque.registered_count} → {new_registered}"
            )
            if not dry_run:
                Mosque.objects.filter(pk=mosque.pk).update(
                    completed_exam_count=new_completed,
                    registered_count=new_registered,
                )

        total = sum(completed.values())
        if not changes:
            self.stdout.write(
                self.style.SUCCESS(f"هیچ تغییری لازم نیست — {total} شرکت‌کنندهٔ کاملِ واقعی.")
            )
            return

        self.stdout.write("\n".join(changes))
        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f"حالتِ آزمایشی: {len(changes)} مسجد تغییر می‌کرد "
                    f"({total} شرکت‌کنندهٔ کاملِ واقعی). هیچ چیزی نوشته نشد."
                )
            )
            return

        from apps.core.cache_invalidation import invalidate_domain_cache

        invalidate_domain_cache("mosques", reason="simulate_leaderboard:recount")
        self.stdout.write(
            self.style.SUCCESS(
                f"جدول به دادهٔ واقعی برگشت — {total} شرکت‌کنندهٔ کامل در "
                f"{sum(1 for v in completed.values() if v)} مسجد."
            )
        )

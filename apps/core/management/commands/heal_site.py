"""دستور `heal_site` — یک فرمان که سایت را از دو باگِ گزارش‌شده پاک می‌کند.

چه می‌کند؟
─────────
۱) **شمارنده‌های مساجد**: هر عددِ ذخیره‌شده را با شمارشِ زنده (`User` +
   `ExamAttempt`) مقایسه و اصلاح می‌کند. همان باگی که ادمین دید: «کاربران را
   از پنل پاک کردم، ولی جدول مساجد هنوز می‌شماردشان.»
۲) **دادهٔ ساختگی**: کاربرانِ ۰۹۹۰… و کارنامه‌های `SIM-` را شناسایی و (با
   `--purge-simulated`) پاک می‌کند تا جدول فقط آمارِ واقعی را نشان دهد.
۳) **کاربرانِ نیمه‌کاره**: کسانی که ثبت‌نام کرده‌اند ولی آزمونشان را شروع
   نکرده‌اند را می‌شمارد — همان‌هایی که گزارشِ «دوباره فرم خالی» از آن‌ها بود —
   تا اپراتور بداند چند نفر در این وضعیت‌اند.

حالتِ پیش‌فرض **فقط گزارش** است؛ با `--fix` می‌نویسد. هیچ دادهٔ واقعی حذف
نمی‌شود مگر پارامترِ صریحِ `--purge-simulated` را بدهید.
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandParser
from django.db import transaction

from apps.authentication.choices import UserRole
from apps.authentication.models import User
from apps.exam.choices import ExamAttemptStatus
from apps.exam.models import ExamAttempt
from apps.mosques.models import Mosque


class Command(BaseCommand):
    """گزارش (و در صورتِ نیاز اصلاح) وضعیتِ داده و شمارنده‌های سایت."""

    help = "بررسی و ترمیمِ شمارنده‌های مساجد + گزارشِ دادهٔ ساختگی و کاربرانِ نیمه‌کاره."

    def add_arguments(self, parser: CommandParser) -> None:
        """گزینه‌های خطِ فرمان."""
        parser.add_argument("--fix", action="store_true", help="شمارنده‌های مساجد را اصلاح کن.")
        parser.add_argument(
            "--purge-simulated",
            action="store_true",
            help="کاربرانِ آزمایشی (۰۹۹۰…) و کارنامه‌های SIM- را حذف کن.",
        )
        parser.add_argument("--quiet", action="store_true", help="فقط خلاصه.")

    def handle(self, *args: Any, **options: Any) -> None:
        """اجرای گزارش و اصلاح‌های درخواستی."""
        del args
        quiet = bool(options["quiet"])
        self.stdout.write("")

        # ── ۱) دادهٔ ساختگی ────────────────────────────────────────────────
        fakes = User.objects.filter(phone_number__startswith="0990")
        fake_attempts = ExamAttempt.objects.filter(tracking_code__startswith="SIM-")
        fake_users = fakes.count()
        fake_tries = fake_attempts.count()
        if fake_users or fake_tries:
            self.stdout.write(
                self.style.WARNING(
                    f"⚠ دادهٔ ساختگی: {fake_users} کاربرِ آزمایشی و {fake_tries} کارنامهٔ SIM-."
                )
            )
            if options["purge_simulated"]:
                with transaction.atomic():
                    fake_attempts.delete()
                    fakes.delete()
                self.stdout.write(self.style.SUCCESS("✔ دادهٔ ساختگی پاک شد."))
        elif not quiet:
            self.stdout.write(self.style.SUCCESS("✔ هیچ دادهٔ ساختگی‌ای نیست."))

        # ── ۲) کاربرانِ نیمه‌کاره (ثبت‌نام بدونِ شروعِ آزمون) ────────────────
        participants = User.objects.filter(role=UserRole.PARTICIPANT, is_active=True)
        with_attempt = set(
            ExamAttempt.objects.filter(user__in=participants).values_list("user_id", flat=True)
        )
        pending = [
            u
            for u in participants.only("id", "first_name", "last_name", "phone_number")
            if u.pk not in with_attempt
        ]
        self.stdout.write(
            f"کاربرانِ ثبت‌نام‌شده که هنوز آزمون را شروع نکرده‌اند: {len(pending)}"
            + (" (با ورودِ بازگشتی، همان‌ها مستقیم ادامه می‌دهند)" if pending else "")
        )
        if pending and not quiet:
            for u in pending[:10]:
                masked = u.phone_number[:4] + "***" + u.phone_number[-2:]
                self.stdout.write(f"  • {u.first_name} {u.last_name} — {masked}")

        # ── ۳) شمارنده‌های مساجد ───────────────────────────────────────────
        drift: list[str] = []
        for mosque in Mosque.all_objects.only(
            "id", "code", "name", "registered_count", "completed_exam_count"
        ):
            live_reg = participants.filter(mosque_id=mosque.pk).count()
            live_done = ExamAttempt.objects.filter(
                mosque_id=mosque.pk,
                status__in=[ExamAttemptStatus.COMPLETED, ExamAttemptStatus.TIMED_OUT],
            ).count()
            if live_reg != mosque.registered_count or live_done != mosque.completed_exam_count:
                drift.append(
                    f"  • {mosque.code} {mosque.name[:28]}: "
                    f"ثبت‌نام {mosque.registered_count}→{live_reg} · "
                    f"تکمیل {mosque.completed_exam_count}→{live_done}"
                )

        if not drift:
            self.stdout.write(self.style.SUCCESS("✔ شمارندهٔ مساجد با دادهٔ واقعی هم‌خوان است."))
        else:
            self.stdout.write(self.style.WARNING(f"⚠ انحراف در {len(drift)} مسجد:"))
            for line in drift:
                self.stdout.write(line)
            if options["fix"]:
                from apps.mosques.services import recount_mosque_stats

                result = recount_mosque_stats()
                self.stdout.write(
                    self.style.SUCCESS(
                        f"✔ بازشمارش شد: {result['fixed']} از {result['checked']} مسجد."
                    )
                )

        if not options["fix"] and drift:
            self.stdout.write("")
            self.stdout.write("برای اصلاح: `manage.py heal_site --fix`")
        self.stdout.write("")

"""دستور `reset_test_participants` — پاک‌سازیِ امنِ دادهٔ آزمونِ آزمایشی + کالبدشکافی.

دو کار در یک اجرا:
۱) **کالبدشکافی**: پیش از هر حذفی، برای هر شرکت‌کننده نشان می‌دهد ثبت‌نام از
   چه مسیری انجام شده (`fast_direct` = باگ، `otp` = سالم)، آیا کدِ تأییدشده
   داشته، و آیا هنوز `is_phone_verified=True` است. این‌ها همان شواهدی است که
   نشان می‌دهد چرا کاربر بی‌کد وارد آزمون شده.
۲) **حذف**: با `--yes`، کاربرانِ نقشِ شرکت‌کننده (نه ادمین/اپراتور) و همهٔ
   داده‌های وابسته‌شان پاک می‌شوند تا تستِ دوباره با همان شماره ممکن شود.

حالتِ پیش‌فرض **خشک** است (هیچ چیز حذف نمی‌شود). ادمین‌ها هرگز حذف نمی‌شوند.
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandParser
from django.db import transaction

from apps.audit_logs.choices import AuditAction
from apps.audit_logs.models import AuditLog
from apps.authentication.choices import UserRole
from apps.authentication.models import AuthSession, OTPChallenge, User
from apps.exam.models import ExamAttempt


class Command(BaseCommand):
    """کالبدشکافیِ مسیرِ تأیید + پاک‌سازیِ دادهٔ آزمایشیِ آزمون."""

    help = "گزارشِ کالبدشکافیِ تأییدِ شماره و (با --yes) پاک‌سازیِ کاربرانِ شرکت‌کننده و آزمون‌هایشان."

    def add_arguments(self, parser: CommandParser) -> None:
        """گزینه‌های خطِ فرمان."""
        parser.add_argument(
            "--yes",
            action="store_true",
            help="واقعاً حذف کن. بدونِ این، فقط گزارش چاپ می‌شود.",
        )
        parser.add_argument(
            "--keep-users",
            action="store_true",
            help="کاربران را نگه دار و فقط آزمون‌ها/نشست‌ها را پاک کن (برای تستِ «همان شماره، آزمونِ تازه»).",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        """چاپِ کالبدشکافی، سپس حذفِ مشروط."""
        participants = User.objects.filter(role=UserRole.PARTICIPANT).order_by("created_at")
        total = participants.count()
        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING(f"شرکت‌کنندگان: {total}"))
        self.stdout.write("")

        if total:
            self.stdout.write(
                f"  {'شماره':13s} {'تأیید':6s} {'آزمون':6s} {'کدِ تأییدشده':12s} مسیرِ ثبت‌نام"
            )
            self.stdout.write("  " + "-" * 66)

        suspicious = 0
        for user in participants:
            has_attempt = ExamAttempt.objects.filter(user=user).exists()
            verified_codes = OTPChallenge.objects.filter(
                phone_number=user.phone_number, is_verified=True
            ).count()
            mode = self._register_mode(user)
            flag = "✔" if user.is_phone_verified else "✘"
            # نشانهٔ باگ: نشستی گرفته که کدِ تأییدشده‌ای پشتش نیست.
            if user.is_phone_verified and verified_codes == 0:
                suspicious += 1
                flag += " ⚠"
            self.stdout.write(
                f"  {self._mask(user.phone_number):13s} {flag:6s} "
                f"{'دارد' if has_attempt else '—':6s} {verified_codes:<12d} {mode}"
            )

        self.stdout.write("")
        if suspicious:
            self.stdout.write(
                self.style.WARNING(
                    f"⚠ {suspicious} کاربر «تأییدشده» هستند ولی هیچ کدِ تأییدشده‌ای در دیتابیس "
                    "ندارند ⇒ این‌ها از مسیرِ قدیمیِ باگ‌دار (fast_direct) ساخته شده‌اند."
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS("✔ هیچ کاربری بدونِ کدِ تأییدشده «تأییدشده» نشده است.")
            )

        if not options.get("yes"):
            self.stdout.write("")
            self.stdout.write(
                "این فقط گزارش است. برای حذف، همین دستور را با `--yes` بزنید "
                "(یا `--yes --keep-users` اگر می‌خواهید شماره‌ها بمانند و فقط آزمون پاک شود)."
            )
            return

        deleted = self._purge(keep_users=bool(options.get("keep_users")))
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(f"پاک شد: {deleted}"))

    @staticmethod
    def _mask(phone: str) -> str:
        """پوشاندنِ وسطِ شماره؛ گزارشِ عمومی نباید شمارهٔ کاملِ کسی را لو بدهد."""
        return phone[:4] + "***" + phone[-2:] if len(phone) > 6 else phone

    @staticmethod
    def _register_mode(user: User) -> str:
        """آخرین مسیرِ ثبت‌نام/ورودِ این کاربر از لاگِ ممیزی."""
        log = (
            AuditLog.objects.filter(user=user, action=AuditAction.USER_LOGGED_IN)
            .order_by("-created_at")
            .first()
        )
        if log is None:
            return "—"
        extra = getattr(log, "extra_data", None) or {}
        mode = str(extra.get("mode", ""))
        return {"fast_direct": "fast_direct ⚠ (باگ)", "otp": "otp ✔"}.get(mode, mode or "—")

    @transaction.atomic
    def _purge(self, keep_users: bool) -> str:
        """حذفِ آزمون‌ها/نشست‌ها و (به‌صورتِ پیش‌فرض) خودِ شرکت‌کنندگان."""
        participants = User.objects.filter(role=UserRole.PARTICIPANT)
        attempts = ExamAttempt.objects.filter(user__in=participants).count()
        ExamAttempt.objects.filter(user__in=participants).delete()

        phones = list(participants.values_list("phone_number", flat=True))
        otps = OTPChallenge.objects.filter(phone_number__in=phones)
        otp_count = otps.count()
        otps.delete()

        if keep_users:
            # شماره‌ها می‌مانند، ولی پرچمِ تأیید برداشته می‌شود تا تستِ بعدی
            # واقعاً از مسیرِ کد برود (این همان چیزی است که باگ را پنهان می‌کرد).
            sessions = AuthSession.objects.filter(user__in=participants).count()
            AuthSession.objects.filter(user__in=participants).delete()
            participants.update(is_phone_verified=False)
            return (
                f"{attempts} آزمون، {otp_count} کدِ یک‌بارمصرف، {sessions} نشست؛ "
                f"و پرچمِ تأییدِ {len(phones)} شماره برداشته شد (کاربران ماندند)."
            )

        # ترتیبِ حذف: فرزندان اول، سپس خودِ کاربر.
        from apps.authentication.models import AuthRiskSignal
        from apps.notifications.models import BaleSubscriber, SMSDeliveryLog

        AuthSession.objects.filter(user__in=participants).delete()
        AuthRiskSignal.objects.filter(user__in=participants).delete()
        SMSDeliveryLog.objects.filter(recipient_phone__in=phones).delete()
        BaleSubscriber.objects.filter(phone_number__in=phones).delete()
        # مسجدها باید شمارنده‌شان از صفر بازسازی شود (شمارنده denormalized است).
        mosque_ids = set(participants.values_list("mosque_id", flat=True)) - {None}
        user_count = participants.count()
        participants.delete()

        from apps.mosques.models import Mosque

        for mosque in Mosque.objects.filter(pk__in=mosque_ids):
            Mosque.objects.filter(pk=mosque.pk).update(
                registered_count=User.objects.filter(mosque_id=mosque.pk, is_active=True).count()
            )
        return (
            f"{user_count} کاربر، {attempts} آزمون، {otp_count} کدِ یک‌بارمصرف و "
            "همهٔ نشست‌ها/سیگنال‌های ریسک حذف شدند؛ شمارندهٔ مسجدها بازسازی شد."
        )

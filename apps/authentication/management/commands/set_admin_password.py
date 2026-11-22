"""دستور `set_admin_password` — تعیین/بازنشانیِ رمز یک حسابِ موجود، بی‌حذف.

══ چرا این دستور لازم شد؟ ═════════════════════════════════════════════════
گزارشِ واقعی: «از پنل ادمین بیرون انداخته شدم و با همان یوزر/پس نمی‌توانم
وارد شوم؛ می‌گوید اشتباه است.»

دو دستورِ موجود هیچ‌کدام این حالت را حل نمی‌کردند:
  • `grant_admin` حساب را ادمین می‌کند ولی **عمداً رمز نمی‌دهد**؛ نتیجه
    حسابی است که `has_usable_password()` برایش `False` است ⇒ هر رمزی
    «اشتباه» است، هرچند حساب سالم است.
  • `reset_admin` رمز می‌دهد ولی **همهٔ ادمین‌های دیگر را حذف می‌کند**؛ برای
    «فقط می‌خواهم رمزم را عوض کنم» ابزارِ درستی نیست.

این دستور فقط و فقط رمز را عوض می‌کند: هیچ حسابی ساخته یا حذف نمی‌شود،
نقش‌ها دست‌نخورده می‌مانند، و اگر رمز را ندهید **خودش یک رمزِ قوی می‌سازد و
یک‌بار چاپ می‌کند** تا دیگر کسی قفل نماند.
"""

from __future__ import annotations

import secrets
import string
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db import transaction

from apps.audit_logs.choices import AuditAction
from apps.audit_logs.services import record_audit_log
from apps.authentication.choices import UserRole
from apps.authentication.models import AuthSession, User
from apps.authentication.validators import (
    normalize_and_validate_national_id,
    normalize_and_validate_phone,
)

#: الفبای رمزِ خودکار — بدونِ حروفِ شبیهِ هم (O/0، l/1) تا تایپِ دستی دردسر نداشته باشد.
_ALPHABET = "".join(c for c in (string.ascii_letters + string.digits) if c not in "O0lI1")


class Command(BaseCommand):
    """تعیین یا بازنشانیِ رمزِ عبورِ یک حسابِ موجود، بدونِ ساخت/حذفِ حساب."""

    help = "رمز عبور یک حساب موجود را تعیین یا بازنشانی می‌کند (بی‌حذف، بی‌تغییرِ نقش)."

    def add_arguments(self, parser: CommandParser) -> None:
        """گزینه‌های خطِ فرمان."""
        parser.add_argument(
            "--phone", default="", help="شمارهٔ همراهِ حساب (یا کد ملی با --national-id)."
        )
        parser.add_argument("--national-id", default="", help="کد ملیِ حساب.")
        parser.add_argument(
            "--password",
            default="",
            help="رمز تازه. اگر ندهید، یک رمزِ قویِ ۱۴ کاراکتری ساخته و چاپ می‌شود.",
        )
        parser.add_argument(
            "--promote",
            action="store_true",
            help="همچنین نقش را admin و is_staff/is_superuser را روشن کن (اگر لازم بود).",
        )
        parser.add_argument(
            "--logout-all",
            action="store_true",
            help="همهٔ نشست‌های فعالِ این حساب را باطل کن (وقتی فکر می‌کنید لو رفته).",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        """یافتنِ حساب، تعیینِ رمز، و گزارشِ کوتاه و بی‌راز."""
        del args
        user = self._find_user(str(options["phone"]), str(options["national_id"]))
        password = str(options["password"]) or self._generate()

        if len(password) < 10:
            raise CommandError("رمز باید دست‌کم ۱۰ کاراکتر باشد.")

        with transaction.atomic():
            user.set_password(password)
            if options["promote"]:
                user.role = UserRole.ADMIN
                user.is_staff = True
                user.is_superuser = True
                user.is_active = True
                user.is_phone_verified = True
            user.save()

            if options["logout_all"]:
                AuthSession.objects.filter(user=user, is_revoked=False).update(is_revoked=True)

            record_audit_log(
                action=AuditAction.USER_UPDATED,
                resource_type="user",
                resource_id=user.pk,
                user=user,
                extra_data={
                    "action": "set_admin_password",
                    "generated": not bool(options["password"]),
                    "promoted": bool(options["promote"]),
                    "sessions_revoked": bool(options["logout_all"]),
                },
            )

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("✔ رمز عبور تعیین شد."))
        self.stdout.write(f"  حساب      : {user.phone_number} — {user.full_name}")
        self.stdout.write(f"  نقش       : {user.role}")
        self.stdout.write(f"  فعال      : {user.is_active} · سوپریمدیر: {user.is_superuser}")
        if not options["password"]:
            self.stdout.write("")
            self.stdout.write(
                self.style.WARNING("  رمزِ ساخته‌شده (فقط همین یک‌بار نشان داده می‌شود):")
            )
            self.stdout.write(f"      {password}")
            self.stdout.write("  همین حالا آن را در جای امن ذخیره کنید و بعد عوضش کنید.")
        if options["logout_all"]:
            self.stdout.write("  همهٔ نشست‌های قبلی باطل شد.")
        self.stdout.write("")
        self.stdout.write("  ورود: https://kaveh185.ir/login  →  «ورودِ مدیران و اپراتورها»")
        # ⚠️ پنل روی دامنهٔ API سرو می‌شود؛ `/secure-kaveh185-admin/` روی سایتِ
        # ایستا وجود ندارد و مدیر را به ۴۰۴ می‌برد. آدرس از همان تنظیمِ
        # ALLOWED_HOSTS خوانده می‌شود تا با محیط هم‌خوان بماند.
        api_host = next(
            (h for h in settings.ALLOWED_HOSTS if isinstance(h, str) and h.startswith("api.")),
            settings.ALLOWED_HOSTS[0] if settings.ALLOWED_HOSTS else "127.0.0.1:8000",
        )
        self.stdout.write(f"  یا مستقیم (روی دامنهٔ API): https://{api_host}/secure-kaveh185-admin/")
        self.stdout.write("")

    # ── کمکی ────────────────────────────────────────────────────────────────
    @staticmethod
    def _find_user(phone: str, national_id: str) -> User:
        """یافتنِ حساب با شماره یا کد ملی؛ با پیامِ روشن اگر نبود."""
        if phone.strip():
            try:
                norm = normalize_and_validate_phone(phone)
            except Exception as exc:
                raise CommandError(f"شمارهٔ همراه معتبر نیست: {exc}") from exc
            user = User.objects.filter(phone_number=norm).first()
            if user is None:
                # ⚠️ این خط در عمل رخ داد و مدیر را سردرگم کرد («رمز عوض نشد»).
                # پیام باید دو چیز را بگوید: ۱) مشکل رمز نیست، خودِ حساب نیست؛
                # ۲) دقیقاً با چه دستوری بفهمد چه حساب‌هایی هست.
                raise CommandError(
                    f"هیچ حسابی با شمارهٔ {norm} روی این نصب نیست "
                    "(پس مشکل رمز نبوده؛ حساب ساخته نشده یا با شمارهٔ دیگری است).\n"
                    "  ۱) ببینید چه حساب‌هایی هست:  manage.py whoami_accounts\n"
                    "  ۲) جست‌وجوی دقیق:            manage.py whoami_accounts --exact <شماره یا کد ملی>\n"
                    "  ۳) اگر حساب ادمین وجود ندارد:  manage.py grant_admin "
                    "--phone <شماره> --national-id <کد ملی> --password <رمز>"
                )
            return user

        if national_id.strip():
            try:
                nid = normalize_and_validate_national_id(national_id)
            except Exception as exc:
                raise CommandError(f"کد ملی معتبر نیست: {exc}") from exc
            user = User.objects.filter(national_id=nid).first()
            if user is None:
                raise CommandError(
                    f"هیچ حسابی با کد ملی {nid} روی این نصب نیست.\n"
                    "  فهرستِ حساب‌ها: manage.py whoami_accounts"
                )
            return user

        # هیچ شناسه‌ای نداده ⇒ اگر فقط یک حسابِ مدیریتی هست، همان را بردار.
        admins = list(User.objects.filter(role=UserRole.ADMIN)[:2])
        if len(admins) == 1:
            return admins[0]
        raise CommandError(
            "شناسه بدهید: --phone 09xxxxxxxxx یا --national-id ... "
            f"(تعدادِ ادمین‌های موجود: {len(admins)})"
        )

    @staticmethod
    def _generate() -> str:
        """ساختِ رمزِ خوانا-برای-انسان ولی قوی (۱۴ کاراکتر، بی‌نماد)."""
        return "".join(secrets.choice(_ALPHABET) for _ in range(14))

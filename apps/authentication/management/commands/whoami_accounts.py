"""دستور `whoami_accounts` — «چه حساب‌هایی روی این نصب وجود دارند؟»

══ چرا این دستور؟ ═════════════════════════════════════════════════════════
گزارشِ میدانیِ واقعی: مدیر گفت «از پنل بیرون افتادم و با همان رمز نمی‌شوم»؛
دستورِ بازنشانی رمز اجرا شد و پاسخ گرفت:

    CommandError: حسابی با این شماره نیست.

یعنی مشکل اصلاً رمز نبود — **خودِ شماره در این دیتابیس وجود نداشت** (تایپِ
رقم، ثبت‌نام با شمارهٔ دیگر، یا دیتابیسِ دیگری). بدونِ این دستور، کاربر و
پشتیبان هر دو در تاریکی حدس می‌زنند.

این دستور فقط **می‌خواند**: هیچ حسابی ساخته، حذف یا تغییر داده نمی‌شود.
هیچ رمزی هم در خروجی نیست — فقط نام، نقش، وضعیت و «آیا رمز دارد؟».

── چرا شمارهٔ کامل چاپ نمی‌شود؟ ─────────────────────────────────────────
خروجیِ این دستور ممکن است در تیکتِ پشتیبانی، پیام یا لاگ paste شود.
شماره‌ها پوشانده می‌شوند (`09***41` + چهار رقمِ آخر) و کد ملی هرگز کامل
نمی‌آید. اگر تطبیقِ دقیق لازم بود، با `--exact 09xxxxxxxxx` بجویید؛ آن‌جا
فقط «هست/نیست» و نام گفته می‌شود.
"""

from __future__ import annotations

import re
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db.models import Count, Q

from apps.authentication.choices import UserRole
from apps.authentication.models import User
from apps.authentication.validators import (
    normalize_and_validate_national_id,
    normalize_and_validate_phone,
)
from apps.core.jalali import format_jalali_datetime


def _mask_phone(phone: str) -> str:
    """پوشاندنِ وسطِ شماره: `09904323741` ⇒ `0990***3741`."""
    digits = re.sub(r"\D", "", phone or "")
    if len(digits) < 8:
        return "***"
    return f"{digits[:4]}***{digits[-4:]}"


class Command(BaseCommand):
    """فهرستِ خواندنیِ حساب‌ها برای عیب‌یابیِ ورود (بدونِ تغییرِ داده)."""

    help = "فهرستِ حساب‌های موجود (نقش، وضعیت، داشتن/نداشتنِ رمز) — فقط خواندن."

    def add_arguments(self, parser: CommandParser) -> None:
        """گزینه‌های خطِ فرمان."""
        parser.add_argument(
            "--role",
            default="all",
            choices=["all", "admin", "operator", "participant"],
            help="فقط یک نقش (پیش‌فرض: همه).",
        )
        parser.add_argument(
            "--exact",
            default="",
            help="جست‌وجوی دقیقِ شماره یا کد ملی؛ پاسخِ کوتاه «هست/نیست».",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=40,
            help="حداکثر تعدادِ ردیف در خروجی (پیش‌فرض: ۴۰).",
        )
        parser.add_argument(
            "--login-idle",
            action="store_true",
            help="فقط کمکی: شماره‌هایی که رمز ندارند را با دستورِ درست نشان بده.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        """گزارشِ کوتاه و بی‌راز از وضعیتِ حساب‌ها."""
        del args
        if options["exact"]:
            self._probe(str(options["exact"]))
            return

        qs = User.objects.all()
        role = str(options["role"])
        if role != "all":
            qs = qs.filter(role=role)

        total = User.objects.count()
        by_role = {
            row["role"]: row["n"]
            for row in User.objects.values("role").annotate(n=Count("id")).order_by()
        }
        admins = list(
            User.objects.filter(Q(role=UserRole.ADMIN) | Q(is_superuser=True))
            .distinct()
            .order_by("id")
        )

        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING("═══ حساب‌های این نصب ═══"))
        self.stdout.write(f"  دیتابیس : {self._db_label()}")
        self.stdout.write(f"  کل کاربران: {total}")
        for name, n in sorted(by_role.items()):
            self.stdout.write(f"    · {name}: {n}")

        if not admins:
            self.stdout.write("")
            self.stdout.write(
                self.style.ERROR(
                    "  ⚠ هیچ حسابِ مدیریتی وجود ندارد! برای ساخت:\n"
                    "      manage.py grant_admin --phone 09xxxxxxxxx --password '...' --national-id <کد ملی>\n"
                    "    (یا reset_admin، که ادمین‌های قبلی را هم پاک می‌کند)"
                )
            )
        else:
            self.stdout.write("")
            self.stdout.write(self.style.MIGRATE_HEADING("  حساب‌های مدیریتی:"))
            for u in admins:
                flags = []
                flags.append("فعال" if u.is_active else "غیرفعال")
                flags.append("staff" if u.is_staff else "بدونِ staff")
                flags.append("سوپریمدیر" if u.is_superuser else "—")
                has_pw = "رمز دارد" if u.has_usable_password() else "⚠ رمز ندارد"
                self.stdout.write(
                    f"    · {_mask_phone(u.phone_number)}  {u.full_name or '—'}  "
                    f"[{u.role}]  {has_pw}  ({'، '.join(flags)})"
                )
                if not u.has_usable_password():
                    self.stdout.write(
                        "        ↳ رمز بگذارید: "
                        f"manage.py set_admin_password --phone {u.phone_number} --promote"
                    )

        if role != "all" or options["limit"]:
            rows = list(qs.order_by("-created_at")[: int(options["limit"])])
            self.stdout.write("")
            self.stdout.write(
                self.style.MIGRATE_HEADING(
                    f"  آخرین حساب‌ها (نقش: {role}، تا {options['limit']} ردیف):"
                )
            )
            for u in rows:
                when = format_jalali_datetime(u.created_at) if u.created_at else "—"
                self.stdout.write(
                    f"    · {_mask_phone(u.phone_number)}  {u.full_name or '—'}  "
                    f"[{u.role}]  {when}  "
                    + ("رمز دارد" if u.has_usable_password() else "بدونِ رمز")
                )

        self.stdout.write("")
        self.stdout.write("  نکته: شماره‌ها پوشانده شده‌اند تا این خروجی را بتوانید")
        self.stdout.write("        بدونِ نگرانی در تیکت/پیام بگذارید.")
        self.stdout.write("  جست‌وجوی دقیق: manage.py whoami_accounts --exact 09xxxxxxxxx")
        self.stdout.write("")

    # ── کمکی ────────────────────────────────────────────────────────────────
    def _probe(self, value: str) -> None:
        """پاسخِ کوتاه به «این شماره/کد ملی روی این نصب هست یا نه؟»."""
        user: User | None = None
        kind = ""
        try:
            user = User.objects.filter(phone_number=normalize_and_validate_phone(value)).first()
            kind = "شمارهٔ همراه"
        except Exception:
            try:
                user = User.objects.filter(
                    national_id=normalize_and_validate_national_id(value)
                ).first()
                kind = "کد ملی"
            except Exception as exc:
                raise CommandError("ورودی نه شمارهٔ همراهِ معتبر است و نه کد ملیِ معتبر.") from exc

        if user is None:
            self.stdout.write("")
            self.stdout.write(self.style.ERROR(f"✘ هیچ حسابی با این {kind} روی این نصب نیست."))
            self.stdout.write("  اگر مطمئنید این شماره درست است، یعنی حساب هرگز ساخته نشده")
            self.stdout.write("  (یا با شمارهٔ دیگری ثبت‌نام شده). ساختِ ادمین:")
            self.stdout.write(
                "      manage.py grant_admin --phone 09xxxxxxxxx --password '...' --national-id <کد ملی>"
            )
            self.stdout.write("")
            return

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(f"✔ پیدا شد ({kind})."))
        self.stdout.write(f"  نام       : {user.full_name or '—'}")
        self.stdout.write(f"  شماره     : {_mask_phone(user.phone_number)}")
        self.stdout.write(f"  نقش       : {user.role}")
        self.stdout.write(
            f"  فعال      : {user.is_active} · staff: {user.is_staff} · سوپریمدیر: {user.is_superuser}"
        )
        self.stdout.write(
            "  رمز       : "
            + ("دارد" if user.has_usable_password() else "⚠ ندارد (هر رمزی اشتباه است)")
        )
        self.stdout.write("")
        if not user.has_usable_password():
            self.stdout.write("  برای گذاشتنِ رمز روی همین حساب:")
        else:
            self.stdout.write("  برای عوض کردنِ رمز روی همین حساب:")
        self.stdout.write(
            f"      manage.py set_admin_password --phone {user.phone_number} --promote"
        )
        self.stdout.write("")

    @staticmethod
    def _db_label() -> str:
        """نامِ دیتابیس و میزبان، بدونِ کاربر/رمز."""
        db = settings.DATABASES.get("default", {})
        name = str(db.get("NAME") or "?")
        host = str(db.get("HOST") or "local")
        return f"{name} @ {host}"

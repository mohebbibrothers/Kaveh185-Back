"""حذف حساب‌های ادمین قدیمی و ساخت یک ادمین تازه — در یک فرمان.

چرا این دستور جدا از `grant_admin` لازم شد؟
─────────────────────────────────────────────
`grant_admin` فقط می‌سازد یا ارتقا می‌دهد؛ کاری با حساب‌های قبلی ندارد. روی
هاست، ادمینِ پیش‌فرضِ `seed_kaveh185` (شمارهٔ `09120000000` با رمزی که در
README عمومی پروژه آمده) باقی می‌ماند. برای تحویل نهایی باید پاک شود، وگرنه
هر کسی که آن مخزن را بخواند می‌تواند وارد پنل شود.

این دستور سه محافظ دارد تا در حالت اشتباه، دادهٔ واقعی را نابود نکند:

  ۱) فقط حساب‌هایی را می‌زند که نقش `admin` دارند — شرکت‌کنندگان دست‌نخورده.
  ۲) اگر حساب انتخابی کارنامه یا شرکت‌کنندهٔ وابسته داشته باشد، هشدار
     می‌دهد و بدون `--force` ادامه نمی‌دهد.
  ۳) خودِ حساب تازه ساخته می‌شود، بعد قدیمی‌ها حذف می‌شوند — اگر ساخت
     شکست بخورد، هیچ ادمینی از دست نمی‌رود.

نمونه:

    python manage.py reset_admin \\
        --phone 09121234567 \\
        --national-id 0013542419 \\
        --password 'یک-رمز-قوی' \\
        --first-name مهدی --last-name محبی
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandParser
from django.db import transaction

from apps.authentication.choices import UserRole
from apps.authentication.models import User
from apps.authentication.validators import (
    normalize_and_validate_national_id,
    normalize_and_validate_phone,
)


class Command(BaseCommand):
    """ساخت ادمین تازه و حذف ادمین‌های قبلی."""

    help = "حذف ادمین‌های موجود و ساخت یک ادمین تازه با شماره و رمز دلخواه"

    def add_arguments(self, parser: CommandParser) -> None:
        """تعریف آرگومان‌ها."""
        parser.add_argument("--phone", required=True, help="شمارهٔ موبایل ادمین تازه")
        parser.add_argument("--password", required=True, help="رمز عبور ادمین تازه")
        parser.add_argument(
            "--national-id", default="", help="کد ملی (اگر ندهی، خودکار معتبر ساخته می‌شود)"
        )
        parser.add_argument("--first-name", default="مدیر", help="نام")
        parser.add_argument("--last-name", default="سامانه", help="نام خانوادگی")
        parser.add_argument(
            "--keep-phone",
            action="append",
            default=[],
            help="شماره‌ای که نباید حذف شود (قابل تکرار)",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="حذف ادمینی که دادهٔ وابسته دارد (کارنامه/شرکت‌کننده)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="فقط بگو چه می‌شود، بدون تغییر",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        """اجرای عملیات با محافظ‌های ایمنی."""
        del args
        phone = normalize_and_validate_phone(str(options["phone"]))
        password = str(options["password"])
        raw_nid = str(options.get("national_id") or "").strip()
        keep = {normalize_and_validate_phone(str(p)) for p in options.get("keep_phone") or []}
        dry = bool(options.get("dry_run"))
        force = bool(options.get("force"))

        if len(password) < 10:
            self.stderr.write(self.style.ERROR("رمز باید دست‌کم ۱۰ کاراکتر باشد."))
            raise SystemExit(1)

        # ── کد ملی ────────────────────────────────────────────────────────
        if raw_nid:
            nid = normalize_and_validate_national_id(raw_nid)
            holder = User.objects.filter(national_id=nid).exclude(phone_number=phone).first()
            if holder is not None:
                self.stderr.write(
                    self.style.ERROR(
                        f"کد ملی {nid} به کاربر {holder.phone_number} تعلق دارد. "
                        "کد ملی دیگری بده یا آن حساب را جدا بررسی کن."
                    )
                )
                raise SystemExit(1)
        else:
            nid = self._free_national_id(phone)

        # ── فهرست ادمین‌های قبلی ─────────────────────────────────────────
        existing = list(
            User.objects.filter(role=UserRole.ADMIN).exclude(phone_number=phone).order_by("id")
        )
        existing = [u for u in existing if u.phone_number not in keep]

        self.stdout.write(f"ادمین تازه: {phone}")
        self.stdout.write(f"کد ملی: {nid}")
        if not existing:
            self.stdout.write(self.style.WARNING("ادمین دیگری برای حذف وجود ندارد."))
        else:
            self.stdout.write(f"\nادمین‌هایی که حذف می‌شوند ({len(existing)}):")
            for u in existing:
                self.stdout.write(
                    f"  · {u.phone_number} — {u.first_name} {u.last_name} "
                    f"(id={u.pk}, role={u.role})"
                )

        if dry:
            self.stdout.write(self.style.WARNING("\n[dry-run] هیچ تغییری اعمال نشد."))
            return

        # ── ساخت اول، حذف بعد ───────────────────────────────────────────
        # ترتیب عمدی است: اگر ساخت به هر دلیلی شکست بخورد، ادمین فعلی سالم
        # می‌ماند و پروژه قفل نمی‌شود.
        with transaction.atomic():
            user, created = User.objects.get_or_create(
                phone_number=phone,
                defaults={
                    "national_id": nid,
                    "first_name": str(options["first_name"]),
                    "last_name": str(options["last_name"]),
                },
            )
            user.role = UserRole.ADMIN
            user.is_staff = True
            user.is_superuser = True
            user.is_phone_verified = True
            if not user.national_id:
                user.national_id = nid
            user.set_password(password)
            user.save()
            verb = "ساخته شد" if created else "به‌روز شد"
            self.stdout.write(self.style.SUCCESS(f"✔ ادمین {phone} {verb}"))

            removed = 0
            for u in existing:
                has_data = self._has_related_data(u)
                if has_data and not force:
                    self.stderr.write(
                        self.style.WARNING(
                            f"▲ {u.phone_number} دادهٔ وابسته دارد — حذف نشد. "
                            "اگر مطمئنی، با --force دوباره بزن."
                        )
                    )
                    continue
                u.delete()
                removed += 1
                self.stdout.write(f"  ✖ حذف شد: {u.phone_number}")

        self.stdout.write(
            self.style.SUCCESS(
                f"\nتمام. {removed} ادمین حذف شد. یک ادمین فعال: {phone}\n"
                "ورود: https://kaveh185.ir/secure-kaveh185-admin/"
            )
        )

    # ── کمکی‌ها ─────────────────────────────────────────────────────────
    @staticmethod
    def _has_related_data(user: User) -> bool:
        """آیا این حساب کارنامه یا شرکت‌کنندهٔ وابسته دارد؟

        حذف آبشاری، کارنامهٔ شرکت‌کننده را هم پاک می‌کند. برای یک ادمین
        معمولاً دادهٔ وابسته وجود ندارد؛ اگر هست، یعنی حساب دو نقش دارد و
        کاربر باید آگاهانه تصمیم بگیرد.
        """
        for attr in ("exams", "attempts", "exam_attempts", "participations"):
            manager = getattr(user, attr, None)
            if manager is not None and hasattr(manager, "exists") and manager.exists():
                return True
        return False

    @staticmethod
    def _free_national_id(phone: str) -> str:
        """ساخت کد ملی معتبر و یکتا که به کاربر دیگری تعلق ندارد.

        الگوریتم رسمی: ۹ رقم دلخواه + رقم کنترل. رقم‌ها از شمارهٔ موبایل
        گرفته می‌شوند تا هر بار یکسان و قابل پیش‌بینی برای همان ادمین باشد.
        """
        digits = "".join(ch for ch in phone if ch.isdigit())[-9:].rjust(9, "4")
        total = sum(int(d) * (10 - i) for i, d in enumerate(digits))
        rem = total % 11
        check = rem if rem < 2 else 11 - rem
        candidate = f"{digits}{check}"
        if User.objects.filter(national_id=candidate).exists():
            # افزایش یک‌تای آخر تا آزاد شود
            for i in range(1, 10):
                digits2 = digits[:8] + str(i)
                total2 = sum(int(d) * (10 - j) for j, d in enumerate(digits2))
                r2 = total2 % 11
                candidate = f"{digits2}{r2 if r2 < 2 else 11 - r2}"
                if not User.objects.filter(national_id=candidate).exists():
                    break
        return candidate

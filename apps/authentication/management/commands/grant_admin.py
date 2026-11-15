"""دستور خط فرمان برای ارتقای کاربر یا ساخت مدیر کل سامانه (`python manage.py grant_admin`)."""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandParser

from apps.authentication.choices import UserRole
from apps.authentication.models import User
from apps.authentication.validators import (
    normalize_and_validate_national_id,
    normalize_and_validate_phone,
)


class Command(BaseCommand):
    """ساخت یا ارتقای حساب مدیر کل در سامانهٔ کاوه ۱۸۵."""

    help = "اعطای نقش ادمین یا ساخت کاربر ادمین جدید"

    def add_arguments(self, parser: CommandParser) -> None:
        """تعریف آرگومان‌های خط فرمان."""
        parser.add_argument("--phone", required=True, help="شماره موبایل ادمین")
        parser.add_argument("--national-id", default="0013542419", help="کد ملی ۱۰ رقمی معتبر")
        parser.add_argument("--password", required=True, help="رمز عبور ادمین")
        parser.add_argument("--first-name", default="مدیر", help="نام")
        parser.add_argument("--last-name", default="کاوه ۱۸۵", help="نام خانوادگی")

    def handle(self, *args: Any, **options: Any) -> None:
        """ایجاد یا ارتقای کاربر به نقش مدیر کل."""
        del args
        phone = normalize_and_validate_phone(str(options["phone"]))
        nid = normalize_and_validate_national_id(str(options["national_id"]))
        password = str(options["password"])

        user = User.objects.filter(phone_number=phone).first()

        # اگر کد ملی به کاربر دیگری تعلق دارد، ساختِ کاربر جدید با IntegrityError
        # خام می‌شکست و پیام «duplicate key value violates unique constraint» به
        # کاربر می‌رسید. اینجا صریح گزارش می‌کنیم و راه‌حل را هم می‌گوییم، چون
        # این حالت در عمل رخ می‌دهد: شخصی قبلاً به‌عنوان شرکت‌کننده ثبت‌نام کرده
        # و بعداً می‌خواهیم همان شخص را ادمین کنیم با شمارهٔ دیگر.
        if user is None:
            conflict = User.objects.filter(national_id=nid).first()
            if conflict is not None:
                self.stderr.write(
                    self.style.ERROR(
                        f"کد ملی {nid} قبلاً به کاربر دیگری (شمارهٔ {conflict.phone_number}) "
                        f"تعلق دارد و با شمارهٔ {phone} در تضاد است.\n"
                        f"راه‌حل: یا همان شمارهٔ {conflict.phone_number} را با --phone بده، "
                        f"یا کد ملی دیگری برای این ادمین انتخاب کن."
                    )
                )
                raise SystemExit(1)

            user = User.objects.create_superuser(
                phone_number=phone,
                national_id=nid,
                password=password,
                first_name=str(options["first_name"]),
                last_name=str(options["last_name"]),
            )
            self.stdout.write(
                self.style.SUCCESS(f"ادمین جدید با شماره {user.phone_number} ساخته شد.")
            )
        else:
            user.role = UserRole.ADMIN
            user.is_staff = True
            user.is_superuser = True
            user.is_phone_verified = True
            user.set_password(password)
            user.save()
            self.stdout.write(
                self.style.SUCCESS(f"کاربر {user.phone_number} به مدیر کل ارتقا یافت.")
            )

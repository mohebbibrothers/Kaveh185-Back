"""دستور خط فرمان برای بارگذاری کامل داده‌های اولیه سامانه کاوه ۱۸۵ (۱۷ مسجد + تنظیمات + بانک سوال + داده نمونه)."""

from __future__ import annotations

from datetime import date
from typing import Any

from django.core.management.base import BaseCommand, CommandParser

from apps.authentication.choices import UserRole
from apps.authentication.models import User
from apps.exam.selectors import get_or_create_exam_configuration
from apps.exam.services import (
    finish_exam_attempt,
    seed_default_questions,
    start_or_resume_exam,
    submit_question_answer,
)
from apps.mosques.models import Mosque
from apps.mosques.services import seed_default_mosques

_DEMO_PARTICIPANTS: list[tuple[str, str, date, int]] = [
    ("محمدحسین", "رضایی", date(2010, 5, 14), 1),
    ("امیرعلی", "کاظمی", date(2008, 11, 3), 2),
    ("فاطمه", "محمدی", date(2005, 2, 20), 3),
    ("زهرا", "حسینی", date(2003, 7, 12), 4),
    ("علی‌اکبر", "موسوی", date(1999, 9, 25), 1),
    ("مهدی", "جعفری", date(1995, 4, 8), 2),
    ("ریحانه", "احمدی", date(2011, 1, 19), 3),
    ("حسین", "صادقی", date(1988, 12, 30), 4),
    ("زینب", "مرادی", date(2001, 6, 11), 1),
    ("سجاد", "حیدری", date(1992, 3, 17), 2),
    ("نرگس", "کریمی", date(2007, 8, 5), 1),
    ("ابوالفضل", "قاسمی", date(2009, 10, 22), 3),
    ("کوثر", "عباسی", date(2004, 5, 9), 2),
    ("محمدطاها", "نعمتی", date(2012, 7, 28), 1),
    ("سارا", "توکلی", date(1997, 11, 15), 4),
    ("حمیدرضا", "اکبری", date(1983, 2, 4), 1),
    ("مریم", "سلطانی", date(1975, 9, 18), 2),
]


def _make_valid_national_id(seed_num: int) -> str:
    """تولید کد ملی ۱۰ رقمی معتبر منطبق بر الگوریتم رقم کنترل ایران."""
    base9 = f"{seed_num:09d}"[-9:]
    if len(set(base9)) == 1:
        base9 = f"001{seed_num:06d}"[-9:]
    weighted_sum = sum(int(base9[i]) * (10 - i) for i in range(9))
    rem = weighted_sum % 11
    check = rem if rem < 2 else (11 - rem)
    return f"{base9}{check}"


class Command(BaseCommand):
    """بارگذاری داده‌های اولیهٔ ۱۷ مسجد حوزه ۱۸۵ شهید کاوه، تنظیمات آزمون، بانک سوال و دادهٔ دمو."""

    help = "بارگذاری ۱۷ مسجد پیش‌فرض، تنظیمات آزمون، بانک سوال نمونه و داده‌های دمو برای تیم فرانت‌اند"

    def add_arguments(self, parser: CommandParser) -> None:
        """تعریف آرگومان‌های خط فرمان."""
        parser.add_argument(
            "--with-demo-data",
            action="store_true",
            help="ایجاد اکانت ادمین پیش‌فرض و ۱۷ شرکت‌کنندهٔ نمونه با کارنامهٔ کامل در ۱۷ مسجد",
        )
        parser.add_argument(
            "--admin-phone",
            type=str,
            default="09120000000",
            help="شماره موبایل ادمین پیش‌فرض در حالت --with-demo-data",
        )
        parser.add_argument(
            "--admin-password",
            type=str,
            default="Kaveh185@Admin1405",
            help="رمز عبور ادمین پیش‌فرض در حالت --with-demo-data",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        """اجرای بارگذاری اولیه و داده‌های نمونه در صورت درخواست."""
        del args
        mosque_res = seed_default_mosques()
        config = get_or_create_exam_configuration()
        q_res = seed_default_questions()

        demo_created = 0
        if options.get("with_demo_data"):
            admin_phone = str(options.get("admin_phone") or "09120000000")
            admin_password = str(options.get("admin_password") or "Kaveh185@Admin1405")
            admin_nid = _make_valid_national_id(1850001)
            admin_user, _ = User.objects.get_or_create(
                phone_number=admin_phone,
                defaults={
                    "national_id": admin_nid,
                    "first_name": "مدیر",
                    "last_name": "حوزه ۱۸۵ شهید کاوه",
                    "role": UserRole.ADMIN,
                    "is_staff": True,
                    "is_superuser": True,
                    "is_phone_verified": True,
                },
            )
            admin_user.role = UserRole.ADMIN
            admin_user.is_staff = True
            admin_user.is_superuser = True
            admin_user.set_password(admin_password)
            admin_user.save()

            mosques = list(Mosque.objects.filter(is_active=True).order_by("id"))
            for idx, (fname, lname, bdate, preferred_pos) in enumerate(_DEMO_PARTICIPANTS, start=1):
                phone = f"0912185{idx:04d}"
                if User.objects.filter(phone_number=phone).exists():
                    continue
                mosque = mosques[(idx - 1) % len(mosques)]
                user = User.objects.create_user(
                    phone_number=phone,
                    national_id=_make_valid_national_id(1851000 + idx),
                    first_name=fname,
                    last_name=lname,
                    birth_date=bdate,
                    mosque=mosque,
                    role=UserRole.PARTICIPANT,
                    is_phone_verified=True,
                )
                attempt, _ = start_or_resume_exam(user=user)
                for q_num in range(1, int(attempt.total_questions) + 1):
                    choice = ((preferred_pos + q_num - 2) % 4) + 1
                    submit_question_answer(
                        user=user,
                        question_number=q_num,
                        selected_position=choice,
                    )
                finish_exam_attempt(user=user)
                demo_created += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Kaveh185 Seed Complete | Mosques: {mosque_res['total']} | "
                f"Questions: {q_res['total']} | Demo Participants: {demo_created} | "
                f"Exam Config: {config.title}"
            )
        )

"""دستور خط فرمان برای بارگذاری کامل داده‌های اولیه سامانه کاوه ۱۸۵ (۱۷ مسجد + تنظیمات + بانک سوال)."""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand

from apps.exam.selectors import get_or_create_exam_configuration
from apps.exam.services import seed_default_questions
from apps.mosques.services import seed_default_mosques


class Command(BaseCommand):
    """بارگذاری داده‌های اولیهٔ ۱۷ مسجد حوزه ۱۸۵ شهید کاوه، تنظیمات آزمون و بانک سوال نمونه."""

    help = "بارگذاری ۱۷ مسجد پیش‌فرض، تنظیمات آزمون و بانک سوال نمونه هفته بسیج"

    def handle(self, *args: Any, **options: Any) -> None:
        """اجرای بارگذاری اولیه."""
        del args, options
        mosque_res = seed_default_mosques()
        config = get_or_create_exam_configuration()
        q_res = seed_default_questions()
        self.stdout.write(
            self.style.SUCCESS(
                f"Kaveh185 Seed Complete | Mosques: {mosque_res['total']} | "
                f"Questions: {q_res['total']} | Exam Config: {config.title}"
            )
        )

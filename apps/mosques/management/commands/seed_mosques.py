"""دستور خط فرمان برای بارگذاری ۱۷ مسجد پیش‌فرض حوزه مقاومت بسیج ۱۸۵ شهید کاوه."""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand

from apps.mosques.services import seed_default_mosques


class Command(BaseCommand):
    """بارگذاری ۱۷ مسجد پیش‌فرض حوزه ۱۸۵ شهید کاوه."""

    help = "بارگذاری ۱۷ مسجد پیش‌فرض حوزه مقاومت بسیج ۱۸۵ شهید کاوه در دیتابیس"

    def handle(self, *args: Any, **options: Any) -> None:
        """اجرای بارگذاری اولیه مساجد."""
        del args, options
        res = seed_default_mosques()
        self.stdout.write(
            self.style.SUCCESS(
                f"مساجد حوزه ۱۸۵ شهید کاوه آماده شدند: {res['created']} جدید، {res['existing']} موجود."
            )
        )

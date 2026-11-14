"""دستور خط فرمان برای بررسی یکپارچگی زنجیرهٔ هش حسابرسی (`python manage.py verify_audit_chain`)."""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandError

from apps.audit_logs.chain import verify_audit_chain


class Command(BaseCommand):
    """بررسی کامل سلامت و پیوستگی زنجیرهٔ هش حسابرسی."""

    help = "بررسی صحت زنجیرهٔ هش ضددستکاری لاگ‌های حسابرسی کاوه ۱۸۵"

    def handle(self, *args: Any, **options: Any) -> None:
        """اجرای بررسی و چاپ نتیجه یا پرتاب CommandError در صورت دستکاری."""
        del args, options
        result = verify_audit_chain()
        if not result["valid"]:
            raise CommandError(
                f"زنجیرهٔ حسابرسی در شمارهٔ {result['broken_at_index']} شکسته است: {result['reason']}"
            )
        self.stdout.write(
            self.style.SUCCESS(
                f"زنجیرهٔ حسابرسی کاملاً معتبر است ({result['checked_count']} رکورد بررسی شد)."
            )
        )

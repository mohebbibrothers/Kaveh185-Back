"""تست یکپارچگی مایگریشن‌های دیتابیس و نبود Drift بین مدل‌ها و مایگریشن‌ها."""

from __future__ import annotations

from io import StringIO

import pytest
from django.core.management import call_command


@pytest.mark.django_db()
def test_no_unapplied_or_missing_migrations() -> None:
    """تمام تغییرات مدل‌ها باید دارای فایل مایگریشن ثبت‌شده باشند."""
    out = StringIO()
    call_command("makemigrations", "--check", "--dry-run", stdout=out)
    assert "No changes detected" in out.getvalue()

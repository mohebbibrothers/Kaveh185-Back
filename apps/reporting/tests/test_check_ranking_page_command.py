"""تستِ دستورِ `check_ranking_page` — همان چیزی که کاربر روی هاست اجرا می‌کند.

اگر خودِ ابزارِ عیب‌یابی خراب باشد، بدتر از نبودنش است: آدم را به مسیرِ غلط
می‌فرستد. پس خروجی‌اش را قفل می‌کنیم.
"""

from __future__ import annotations

from io import StringIO

import pytest
from django.core.management import call_command

pytestmark = [pytest.mark.django_db]


def test_command_reports_everything_ok() -> None:
    """روی نصبِ سالم، باید هر پنج خط ✔ باشد و با کدِ صفر تمام شود."""
    out = StringIO()
    call_command("check_ranking_page", stdout=out)
    text = out.getvalue()

    assert "کد تازه روی سرور است" in text
    assert "مسیر ثبت شده است" in text
    assert "resolve → participant_ranking_view" in text
    assert "کارتِ میان‌بر" in text
    assert "نشانیِ کامل" in text
    assert "همه‌چیز سرِ جایش است" in text


def test_command_prints_the_real_url() -> None:
    """نشانی چاپ‌شده باید همان چیزی باشد که `reverse` می‌دهد."""
    from django.urls import reverse

    out = StringIO()
    call_command("check_ranking_page", stdout=out)
    assert reverse("participant-ranking") in out.getvalue()


def test_command_fails_loudly_when_route_is_missing(monkeypatch) -> None:
    """اگر مسیر نبود، دستور باید با کدِ خروجِ ۱ و پیامِ روشن تمام شود.

    این یعنی می‌شود در اسکریپتِ استقرار نوشت: `manage.py check_ranking_page
    || echo "استقرار ناقص است"`.
    """
    import apps.reporting.management.commands.check_ranking_page as module

    monkeypatch.setattr(module, "MODULE_MARKER", "always-mismatch")

    out = StringIO()
    with pytest.raises(SystemExit) as exc_info:
        call_command("check_ranking_page", stdout=out)

    assert exc_info.value.code == 1
    assert "کدِ تازه روی سرور نیست" in out.getvalue()


def test_command_reports_mysql_engine_without_sqlite_backup_advice(monkeypatch) -> None:
    """روی MySQL، توصیهٔ `cp db.sqlite3` نباید چاپ شود (توهمِ امنیت می‌سازد).

    ⚠️ این تست از یک اشتباهِ واقعی می‌آید: راهنما گفت «cp db.sqlite3» و روی
    هاست جواب داد «No such file». اگر ابزار خودش موتور را نگوید، کاربر فکر
    می‌کند نسخهٔ بازگشتی دارد و ندارد.
    """
    from django.conf import settings

    monkeypatch.setitem(settings.DATABASES["default"], "ENGINE", "django.db.backends.mysql")

    out = StringIO()
    call_command("check_ranking_page", stdout=out)
    text = out.getvalue()

    assert "MySQL/MariaDB" in text
    assert "قفلِ سراسریِ SQLite" in text
    assert "cp db.sqlite3" not in text, "روی MySQL نباید پشتیبانِ SQLite توصیه شود"


def test_command_reports_sqlite_engine_with_wal_advice(monkeypatch) -> None:
    """روی SQLite، برعکس: باید بگوید بک‌اندِ ما فعال است."""
    from django.conf import settings

    monkeypatch.setitem(settings.DATABASES["default"], "ENGINE", "apps.core.db_sqlite")

    out = StringIO()
    call_command("check_ranking_page", stdout=out)
    text = out.getvalue()

    assert "SQLite با بک‌اندِ ما" in text
    assert "WAL" in text

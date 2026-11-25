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

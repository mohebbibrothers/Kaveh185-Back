"""تست‌های دستورِ `whoami_accounts` — عیب‌یابیِ «حساب من کجاست؟».

══ چه چیزی را قفل می‌کند؟ ═════════════════════════════════════════════════
این دستور پاسخِ یک پرسشِ واقعیِ پشتیبانی است: «چرا می‌گوید حسابی با این
شماره نیست؟» اگر روزی کسی خروجی را تغییر دهد، باید مطمئن باشیم:

  ۱) **هیچ رازی بیرون نمی‌رود:** شمارهٔ کامل چاپ نمی‌شود، فقط پوشانده.
  ۲) **هیچ داده‌ای تغییر نمی‌کند:** دستور کاملاً خواندنی است.
  ۳) **حسابِ بدونِ رمز دیده می‌شود** — همان علتی که مدیر را قفل می‌کند.
"""

from __future__ import annotations

from io import StringIO
from typing import Any

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.authentication.choices import UserRole
from apps.authentication.models import User

pytestmark = pytest.mark.django_db


def _run(*args: str) -> str:
    """اجرای دستور و برگرداندنِ خروجیِ ادغام‌شده."""
    out = StringIO()
    call_command("whoami_accounts", *args, stdout=out, stderr=out)
    return out.getvalue()


def _admin(phone: str = "09904323741", *, password: str | None = "x" * 12) -> User:
    """ساختِ یک ادمینِ آزمایشی."""
    user: Any = User.objects.create_user(
        phone_number=phone,
        national_id="0013542419",
        first_name="مدیر",
        last_name="آزمایشی",
        password=password,
    )
    user.role = UserRole.ADMIN
    user.is_staff = True
    user.save(update_fields=["role", "is_staff"])
    return user


def test_masks_phone_numbers_and_never_prints_them_fully() -> None:
    """شمارهٔ کامل هرگز در خروجی نیست؛ نسخهٔ پوشانده هست."""
    _admin()
    out = _run()
    assert "09904323741" not in out
    assert "0990***3741" in out


def test_does_not_mutate_any_account() -> None:
    """دستور فقط می‌خواند: تعداد و هشِ رمز تغییر نمی‌کند."""
    user = _admin()
    before = (User.objects.count(), user.password)
    _run()
    user.refresh_from_db()
    assert (User.objects.count(), user.password) == before


def test_flags_admins_without_usable_password() -> None:
    """حسابِ بدونِ رمز با هشدار و دستورِ رفع دیده می‌شود."""
    user = _admin(password=None)
    assert not user.has_usable_password()
    out = _run()
    assert "رمز ندارد" in out
    assert "set_admin_password" in out


def test_warns_when_no_admin_exists() -> None:
    """نصبِ بدونِ ادمین: هشدارِ روشن + دستورِ ساخت."""
    out = _run()
    assert "هیچ حسابِ مدیریتی وجود ندارد" in out
    assert "grant_admin" in out


def test_exact_probe_finds_account_by_phone() -> None:
    """جست‌وجوی دقیق با شماره: «پیدا شد» + نام + راهِ بازنشانیِ رمز."""
    _admin()
    out = _run("--exact", "09904323741")
    assert "پیدا شد" in out
    assert "مدیر آزمایشی" in out
    assert "set_admin_password" in out


def test_exact_probe_finds_account_by_national_id() -> None:
    """جست‌وجوی دقیق با کد ملی هم کار می‌کند."""
    _admin()
    out = _run("--exact", "0013542419")
    assert "پیدا شد" in out


def test_exact_probe_says_clearly_when_absent() -> None:
    """شمارهٔ معتبر ولی ناموجود ⇒ پیامِ صریح، نه سکوت."""
    out = _run("--exact", "09121234567")
    assert "هیچ حسابی با این" in out
    assert "grant_admin" in out


def test_exact_probe_rejects_invalid_input() -> None:
    """ورودیِ بی‌معنا ⇒ خطای روشن (نه استثنای خام)."""
    with pytest.raises(CommandError):
        _run("--exact", "abc")

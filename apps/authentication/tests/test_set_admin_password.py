"""تستِ `set_admin_password` — ابزارِ نجاتِ حسابی که «رمز اشتباه» می‌گفت.

سناریوی واقعی: ادمین از پنل بیرون افتاد و با همان رمز وارد نشد. علتِ رایج:
حساب هرگز رمز نداشت (`has_usable_password()` منفی) چون با `grant_admin`
ساخته شده بود. `reset_admin` هم رمز می‌داد ولی همهٔ ادمین‌ها را حذف می‌کرد.
"""

from __future__ import annotations

from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.authentication.choices import UserRole
from apps.authentication.models import AuthSession, User
from tests.factories import create_test_admin


@pytest.mark.django_db
def test_sets_password_on_existing_account_without_deleting_anything() -> None:
    """رمز ست می‌شود، حساب می‌ماند، نقش دست‌نخورده."""
    admin = create_test_admin(seq=801)
    admin.set_unusable_password()
    admin.save()
    assert admin.has_usable_password() is False

    call_command(
        "set_admin_password",
        "--phone",
        admin.phone_number,
        "--password",
        "SuperSecret123",
        stdout=StringIO(),
    )

    admin.refresh_from_db()
    assert admin.has_usable_password() is True
    assert admin.check_password("SuperSecret123") is True
    assert User.objects.filter(pk=admin.pk).exists()
    assert admin.role == UserRole.ADMIN


@pytest.mark.django_db
def test_generates_a_strong_password_when_none_given() -> None:
    """بدونِ `--password`، رمزِ قوی ساخته و چاپ می‌شود (تا هیچ‌کس قفل نماند)."""
    admin = create_test_admin(seq=802)
    admin.set_unusable_password()
    admin.save()

    out = StringIO()
    call_command("set_admin_password", "--phone", admin.phone_number, stdout=out)
    text = out.getvalue()

    assert "رمزِ ساخته‌شده" in text
    admin.refresh_from_db()
    assert admin.has_usable_password() is True


@pytest.mark.django_db
def test_rejects_short_password_and_unknown_account() -> None:
    """رمزِ کوتاه و حسابِ ناموجود، خطای روشن می‌دهند (نه ۵۰۰)."""
    admin = create_test_admin(seq=803)
    with pytest.raises(CommandError):
        call_command("set_admin_password", "--phone", admin.phone_number, "--password", "short")
    with pytest.raises(CommandError):
        call_command("set_admin_password", "--phone", "09120000000", "--password", "LongEnough123")


@pytest.mark.django_db
def test_promote_and_logout_all() -> None:
    """`--promote` نقش را ادمین می‌کند و `--logout-all` نشست‌ها را می‌بندد."""
    user = create_test_admin(seq=804)
    user.role = UserRole.PARTICIPANT
    user.is_staff = False
    user.is_superuser = False
    user.save()
    from apps.core.uuid7 import uuid7

    AuthSession.objects.create(user=user, session_uid=str(uuid7()))

    call_command(
        "set_admin_password",
        "--phone",
        user.phone_number,
        "--password",
        "AnotherSecret123",
        "--promote",
        "--logout-all",
        stdout=StringIO(),
    )

    user.refresh_from_db()
    assert user.role == UserRole.ADMIN
    assert user.is_superuser is True
    assert all(s.is_revoked for s in AuthSession.objects.filter(user=user))

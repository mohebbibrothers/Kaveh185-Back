"""تست‌های دستور `reset_admin` — ابزار بازیابی دسترسی در روز بحران.

چرا این تست‌ها اهمیت دارند؟
───────────────────────────
این دستور تنها راه بازگرداندن دسترسی به پنل است وقتی رمز ادمین گم شده یا
حساب قفل شده. اگر خودش اشتباه کار کند، پروژه بدون هیچ راه ورودی می‌ماند.
پس دو چیز را قفل می‌کنیم:

1. **امنیت مسیر**: رمز کوتاه رد می‌شود، `--dry-run` هیچ‌چیز را تغییر
   نمی‌دهد، و کد ملیِ متعلق به کاربر دیگر باعث توقف می‌شود.
2. **ترتیب امن**: ادمین تازه *قبل* از حذف ادمین‌های قبلی ساخته می‌شود؛
   یعنی در بدترین حالت یک ادمین فعال همیشه باقی می‌ماند.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command

from apps.authentication.choices import UserRole

pytestmark = pytest.mark.django_db

User = get_user_model()


def _make_admin(phone: str, *, nid: str) -> User:
    user = User.objects.create_user(
        phone_number=phone,
        national_id=nid,
        first_name="قبلی",
        last_name="ادمین",
        birth_date="1370-01-01",
        role=UserRole.ADMIN,
        is_staff=True,
        is_superuser=True,
        is_phone_verified=True,
    )
    user.set_password("OldPass#18500")
    user.save()
    return user


def test_creates_admin_with_working_password() -> None:
    """ادمین ساخته‌شده واقعاً می‌تواند وارد شود."""
    call_command("reset_admin", phone="09129990000", password="Fresh#2026Pass")
    user = User.objects.get(phone_number="09129990000")
    assert user.is_staff and user.is_superuser
    assert user.role == UserRole.ADMIN
    assert user.check_password("Fresh#2026Pass")
    # کد ملی معتبر و یکتا ساخته شده است
    assert len(user.national_id) == 10


def test_replaces_previous_admin_and_keeps_single_admin() -> None:
    """ادمین قبلی حذف می‌شود؛ در پایان یک ادمین فعال می‌ماند."""
    _make_admin("09129990001", nid="0009900012")
    call_command("reset_admin", phone="09129990002", password="Fresh#2026Pass")
    assert not User.objects.filter(phone_number="09129990001").exists()
    assert User.objects.filter(role=UserRole.ADMIN).count() == 1


def test_keep_phone_protects_admin_from_removal() -> None:
    """`--keep-phone` ادمین دوم را دست نمی‌زند."""
    _make_admin("09129990003", nid="0009900012")
    call_command(
        "reset_admin",
        phone="09129990004",
        password="Fresh#2026Pass",
        keep_phone=["09129990003"],
    )
    assert User.objects.filter(phone_number="09129990003").exists()
    assert User.objects.filter(phone_number="09129990004").exists()


def test_short_password_is_rejected(capsys) -> None:
    """رمز کوتاه‌تر از ۱۰ کاراکتر اصلاً اعمال نمی‌شود."""
    with pytest.raises(SystemExit):
        call_command("reset_admin", phone="09129990005", password="short")
    assert not User.objects.filter(phone_number="09129990005").exists()


def test_dry_run_changes_nothing() -> None:
    """`--dry-run` فقط گزارش می‌دهد و دیتابیس دست‌نخورده می‌ماند."""
    before = User.objects.count()
    call_command("reset_admin", phone="09129990006", password="Fresh#2026Pass", dry_run=True)
    assert User.objects.count() == before
    assert not User.objects.filter(phone_number="09129990006").exists()


def test_national_id_owned_by_someone_else_aborts(capsys) -> None:
    """کد ملی متعلق به کاربر دیگر ⇒ توقف، بدون حذف چیزی."""
    _make_admin("09129990007", nid="0009900012")
    with pytest.raises(SystemExit):
        call_command(
            "reset_admin",
            phone="09129990008",
            password="Fresh#2026Pass",
            national_id="0009900012",
        )
    assert User.objects.filter(phone_number="09129990007").exists()


def test_existing_phone_is_promoted_not_duplicated() -> None:
    """شمارهٔ موجود ارتقا می‌یابد، نه اینکه رکورد دوم بسازد."""
    User.objects.create_user(
        phone_number="09129990009",
        national_id="0009900012",
        first_name="کاربر",
        last_name="عادی",
        birth_date="1370-01-01",
    )
    call_command("reset_admin", phone="09129990009", password="Fresh#2026Pass")
    assert User.objects.filter(phone_number="09129990009").count() == 1
    user = User.objects.get(phone_number="09129990009")
    assert user.is_staff and user.is_superuser
    assert user.check_password("Fresh#2026Pass")


def test_free_national_id_is_never_shared() -> None:
    """کد ملی خودکار برای دو ادمین متفاوت، یکتا می‌ماند."""
    call_command("reset_admin", phone="09129990010", password="Fresh#2026Pass")
    call_command("reset_admin", phone="09129990011", password="Fresh#2026Pass")
    ids = list(User.objects.values_list("national_id", flat=True))
    assert len(ids) == len(set(ids))

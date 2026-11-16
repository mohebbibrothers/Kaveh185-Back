"""تست‌های تأیید دومرحله‌ای (TOTP) برای حساب ادمین.

چرا مهم است؟
───────────
پنل ادمین تنها راه ورود دادهٔ واقعی است؛ اگر MFA نادرست کار کند، یا ادمین
برای همیشه بیرون می‌ماند (بدترین حالت برای روز مسابقه) یا با یک ضعف،
دروازهٔ دوم بی‌اثر می‌شود. پس هم مسیر موفق، هم مسیر خطا و هم «کد بازیابی
یک‌بارمصرف» را قفل می‌کنیم.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model

from apps.authentication.services import (
    confirm_user_totp,
    setup_user_totp,
    verify_user_mfa,
)
from apps.authentication.totp import compute_totp_code as generate_totp_code
from apps.core.exceptions import DomainError

pytestmark = pytest.mark.django_db

User = get_user_model()


@pytest.fixture()
def admin_user() -> User:
    return User.objects.create_user(
        phone_number="09127770000",
        national_id="0009900012",
        first_name="امیر",
        last_name="دوعاملی",
        birth_date="1370-01-01",
        is_staff=True,
        is_superuser=True,
        is_phone_verified=True,
    )


def test_setup_returns_valid_otpauth_uri(admin_user) -> None:
    """راه‌اندازی، راز و نشانی otpauth قابل اسکن می‌دهد."""
    data = setup_user_totp(user=admin_user)
    assert data["secret"]
    assert data["otpauth_uri"].startswith("otpauth://totp/")
    admin_user.refresh_from_db()
    assert admin_user.mfa_secret_encrypted
    # راز باید رمزنگاری‌شده ذخیره شود، نه به‌صورت خام
    assert data["secret"] not in str(admin_user.mfa_secret_encrypted)


def test_confirm_requires_setup_first(admin_user) -> None:
    """بدون راه‌اندازی، تأیید کد خطای روشن می‌دهد نه ۵۰۰."""
    with pytest.raises(DomainError) as exc:
        confirm_user_totp(user=admin_user, code="123456")
    assert exc.value.code == "mfa_not_initialized"


def test_confirm_with_wrong_code_fails(admin_user) -> None:
    """کد غلط، MFA را فعال نمی‌کند."""
    setup_user_totp(user=admin_user)
    with pytest.raises(DomainError) as exc:
        confirm_user_totp(user=admin_user, code="000000")
    assert exc.value.code == "invalid_totp_code"
    admin_user.refresh_from_db()
    assert admin_user.mfa_enabled is False


def test_full_enrollment_then_login_verification(admin_user) -> None:
    """چرخهٔ کامل: راه‌اندازی → تأیید → ورود با کد تازه."""
    secret = setup_user_totp(user=admin_user)["secret"]
    codes = confirm_user_totp(user=admin_user, code=generate_totp_code(secret))
    assert len(codes) == 8  # کدهای بازیابی یک‌بارمصرف

    admin_user.refresh_from_db()
    assert admin_user.mfa_enabled is True
    # کدهای بازیابی فقط به‌صورت هش ذخیره می‌شوند
    assert all(len(h) == 64 for h in admin_user.mfa_recovery_codes)

    assert verify_user_mfa(user=admin_user, code=generate_totp_code(secret)) is True


def test_recovery_code_is_single_use(admin_user) -> None:
    """کد بازیابی یک بار کار می‌کند و بار دوم رد می‌شود."""
    secret = setup_user_totp(user=admin_user)["secret"]
    codes = confirm_user_totp(user=admin_user, code=generate_totp_code(secret))
    admin_user.refresh_from_db()

    assert verify_user_mfa(user=admin_user, code=codes[0]) is True
    admin_user.refresh_from_db()
    assert len(admin_user.mfa_recovery_codes) == 7
    with pytest.raises(DomainError):
        verify_user_mfa(user=admin_user, code=codes[0])


def test_verify_fails_when_mfa_not_enabled(admin_user) -> None:
    """حساب بدون MFA، درخواست تأیید را نمی‌پذیرد."""
    with pytest.raises(DomainError) as exc:
        verify_user_mfa(user=admin_user, code="123456")
    assert exc.value.code == "mfa_not_enabled"


def test_invalid_code_is_rejected_after_enrollment(admin_user) -> None:
    """پس از فعال‌سازی، کد نامعتبر رد می‌شود."""
    secret = setup_user_totp(user=admin_user)["secret"]
    confirm_user_totp(user=admin_user, code=generate_totp_code(secret))
    admin_user.refresh_from_db()
    with pytest.raises(DomainError) as exc:
        verify_user_mfa(user=admin_user, code="999999")
    assert exc.value.code == "invalid_mfa_code"

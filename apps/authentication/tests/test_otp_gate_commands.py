"""تستِ دستورهای تشخیصی/پاک‌سازیِ درگاهِ OTP (`verify_otp_gate`, `reset_test_participants`).

این دو دستور ابزارِ عملیاتی‌اند و اگر خودشان خراب باشند، بدترین حالت ممکن
پیش می‌آید: اپراتور خیال می‌کند «درگاه بسته است» یا دادهٔ واقعی را بدونِ
اینکه بفهمد پاک می‌کند. پس رفتارشان قفل می‌شود.
"""

from __future__ import annotations

from io import StringIO

import pytest
from django.core.management import call_command
from django.test import override_settings

from apps.audit_logs.choices import AuditAction
from apps.audit_logs.services import record_audit_log
from apps.authentication.choices import UserRole
from apps.authentication.models import OTPChallenge, User
from apps.exam.models import ExamAttempt
from apps.mosques.models import Mosque


def make_valid_national_id(seed: int) -> str:
    """تولیدِ کدِ ملی با رقمِ کنترلِ درست از یک بذر."""
    digits = [int(c) for c in f"{seed:09d}"[:9]]
    total = sum(digits[i] * (10 - i) for i in range(9))
    rem = total % 11
    check = rem if rem < 2 else 11 - rem
    return "".join(str(d) for d in digits) + str(check)


@pytest.mark.django_db
def test_verify_otp_gate_reports_open_gate_when_policy_is_off() -> None:
    """با سیاستِ فعالِ فعلی (بدونِ کد) درگاه «باز» است و دستور باید همین را بگوید.

    انتظارِ «مسدود» این‌جا غلط است و خودش گمراه‌کننده می‌شد؛ ابزار باید وضعیتِ
    واقعی را بگوید، نه آن‌چه ما دوست داریم.
    """
    Mosque.objects.create(name="مسجد آزمون", is_active=True)
    out = StringIO()
    with pytest.raises(SystemExit):
        call_command("verify_otp_gate", stdout=out)

    text = out.getvalue()
    assert "BALE_OTP_MANDATORY = False" in text
    # با سیاستِ خاموش، گیت باز است و دستور باید صادقانه همین را بگوید.
    assert "باز است" in text
    # کاربرِ موقتِ دستور نباید باقی بماند.
    assert not User.objects.filter(phone_number="09000000000").exists()


@pytest.mark.django_db
@override_settings(BALE_OTP_MANDATORY=True)
def test_verify_otp_gate_confirms_block_when_policy_is_on() -> None:
    """با روشن‌کردنِ سیاست، همان دستور باید «مسدود» را تأیید کند (۴۰۳)."""
    Mosque.objects.create(name="مسجد آزمون ۲", is_active=True)
    out = StringIO()
    call_command("verify_otp_gate", stdout=out)
    text = out.getvalue()
    assert "بسته است" in text
    assert "درگاه بسته است" in text


@pytest.mark.django_db
def test_reset_command_is_dry_by_default() -> None:
    """بدونِ `--yes` هیچ داده‌ای حذف نمی‌شود — گزارشِ فقط‌خواندنی."""
    mosque = Mosque.objects.create(name="مسجد", is_active=True)
    user = User.objects.create_user(
        phone_number="09121110000",
        national_id=make_valid_national_id(211),
        first_name="تست",
        last_name="خشک",
        birth_date="1383-01-01",
        mosque=mosque,
        role=UserRole.PARTICIPANT,
    )
    out = StringIO()
    call_command("reset_test_participants", stdout=out)
    assert User.objects.filter(pk=user.pk).exists()
    assert "فقط گزارش است" in out.getvalue()


@pytest.mark.django_db
def test_reset_command_purges_participants_but_never_admins() -> None:
    """`--yes` شرکت‌کننده را پاک می‌کند، ادمین را هرگز."""
    mosque = Mosque.objects.create(name="م", is_active=True)
    participant = User.objects.create_user(
        phone_number="09121110001",
        national_id=make_valid_national_id(212),
        first_name="شرکت",
        last_name="کننده",
        birth_date="1383-01-01",
        mosque=mosque,
        role=UserRole.PARTICIPANT,
    )
    admin = User.objects.create_user(
        phone_number="09121110002",
        national_id=make_valid_national_id(213),
        first_name="مدیر",
        last_name="کل",
        birth_date="1383-01-01",
        mosque=mosque,
        role=UserRole.ADMIN,
        is_phone_verified=True,
    )
    from django.utils import timezone

    ExamAttempt.objects.create(
        user=participant,
        mosque=mosque,
        tracking_code="TRK-1",
        status="in_progress",
        started_at=timezone.now(),
        expires_at=timezone.now() + timezone.timedelta(minutes=10),
    )

    call_command("reset_test_participants", "--yes", stdout=StringIO())

    assert not User.objects.filter(pk=participant.pk).exists()
    assert User.objects.filter(pk=admin.pk).exists()
    mosque.refresh_from_db()
    assert mosque.registered_count == 1  # فقط ادمین می‌ماند


@pytest.mark.django_db
def test_reset_keep_users_clears_the_false_verified_flag() -> None:
    """`--keep-users` همان پرچمی را برمی‌دارد که باگ باعثِ ست‌شدنش شده بود.

    این حالت را عمداً تست می‌کنیم: کاربر شماره‌اش را از دست نمی‌دهد ولی
    می‌تواند تستِ واقعیِ «کد بیاید یا نه» را دوباره انجام دهد.
    """
    mosque = Mosque.objects.create(name="م", is_active=True)
    user = User.objects.create_user(
        phone_number="09121110003",
        national_id=make_valid_national_id(214),
        first_name="نگه",
        last_name="دار",
        birth_date="1383-01-01",
        mosque=mosque,
        role=UserRole.PARTICIPANT,
        is_phone_verified=True,  # مثلِ مسیرِ باگ‌دار
    )
    OTPChallenge.objects.create(
        phone_number="09121110003",
        code_salt="s" * 8,
        code_hash="h" * 64,
        expires_at="2030-01-01T00:00:00Z",
    )

    call_command("reset_test_participants", "--yes", "--keep-users", stdout=StringIO())

    user.refresh_from_db()
    assert user.is_phone_verified is False
    assert not OTPChallenge.objects.filter(phone_number="09121110003").exists()


@pytest.mark.django_db
def test_reset_reports_fast_direct_mode_as_bug() -> None:
    """گزارش باید مسیرِ ثبت‌نامِ باگ‌دار را «باگ» برچسب بزند، نه «otp»."""
    mosque = Mosque.objects.create(name="م", is_active=True)
    user = User.objects.create_user(
        phone_number="09121110004",
        national_id=make_valid_national_id(215),
        first_name="مسیر",
        last_name="قدیمی",
        birth_date="1383-01-01",
        mosque=mosque,
        role=UserRole.PARTICIPANT,
        is_phone_verified=True,
    )
    record_audit_log(
        action=AuditAction.USER_LOGGED_IN,
        resource_type="user",
        resource_id=user.pk,
        user=user,
        extra_data={"mode": "fast_direct"},
        actor_label="test",
    )
    out = StringIO()
    call_command("reset_test_participants", stdout=out)
    text = out.getvalue()
    assert "fast_direct" in text
    assert "باگ" in text

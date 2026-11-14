"""کارخانه‌های تولید دادهٔ تست (Test Factories) برای دامنه‌های کاوه ۱۸۵."""

from __future__ import annotations

from datetime import date

from apps.authentication.choices import UserRole
from apps.authentication.models import User
from apps.exam.models import Question, QuestionOption
from apps.mosques.models import Mosque


def make_valid_national_id(seq: int) -> str:
    """تولید کد ملی ۱۰ رقمی معتبر ایران با رقم کنترلی صحیح (Mod-11) برای تست‌ها."""
    base9 = f"{(10000000 + int(seq)) % 999999999:09d}"
    if len(set(base9)) == 1:
        base9 = "001354241"
    weighted_sum = sum(int(base9[idx]) * (10 - idx) for idx in range(9))
    rem = weighted_sum % 11
    check_digit = rem if rem < 2 else (11 - rem)
    return f"{base9}{check_digit}"


def create_test_mosque(
    *,
    seq: int = 1,
    name: str | None = None,
    code: str | None = None,
    neighborhood: str = "منطقه کاوه ۱۸۵",
) -> Mosque:
    """ایجاد مسجد نمونه برای تست."""
    m_code = code or f"MSJ-T{seq:03d}"
    m_name = name or f"مسجد جامع نمونه {seq}"
    mosque, _ = Mosque.all_objects.get_or_create(
        code=m_code,
        defaults={
            "name": m_name,
            "neighborhood": neighborhood,
            "display_order": seq,
            "is_active": True,
        },
    )
    return mosque


def create_test_participant(
    *,
    seq: int = 1,
    mosque: Mosque | None = None,
    first_name: str = "علی",
    last_name: str = "رضایی",
    birth_date: date = date(2002, 5, 15),
    is_phone_verified: bool = True,
) -> User:
    """ایجاد شرکت‌کنندهٔ معتبر برای تست."""
    target_mosque = mosque or create_test_mosque(seq=seq)
    phone = f"0912{1000000 + seq:07d}"
    nid = make_valid_national_id(seq)
    return User.objects.create_user(
        phone_number=phone,
        national_id=nid,
        first_name=first_name,
        last_name=last_name,
        birth_date=birth_date,
        mosque=target_mosque,
        role=UserRole.PARTICIPANT,
        is_phone_verified=is_phone_verified,
    )


def create_test_admin(*, seq: int = 900) -> User:
    """ایجاد کاربر مدیر کل (ادمین) برای تست."""
    phone = f"0912{9000000 + seq:07d}"
    nid = make_valid_national_id(9000 + seq)
    return User.objects.create_superuser(
        phone_number=phone,
        national_id=nid,
        password="StrongAdminPass!185",
        first_name="مدیر",
        last_name="کاوه ۱۸۵",
    )


def create_test_question(*, seq: int = 1, correct_option_number: int = 1) -> Question:
    """ایجاد یک سوال چهارگزینه‌ای استاندارد در بانک سوال برای تست."""
    q = Question.objects.create(
        text=f"سوال تستی شماره {seq}: کدام گزینه درباره فرهنگ بسیج صحیح است؟",
        chapter=f"فصل {((seq - 1) % 4) + 1}",
        difficulty="medium",
        explanation=f"توضیح تشریحی سوال {seq}",
        is_active=True,
    )
    for num in range(1, 5):
        QuestionOption.objects.create(
            question=q,
            option_number=num,
            text=f"گزینه {num} برای سوال {seq}",
            is_correct=(num == correct_option_number),
        )
    return q


def seed_test_question_bank(*, count: int = 8) -> list[Question]:
    """ایجاد بانک سوال تستی با حداقل `count` سوال چهارگزینه‌ای فعال."""
    return [
        create_test_question(seq=i, correct_option_number=((i - 1) % 4) + 1)
        for i in range(1, count + 1)
    ]

"""اعتبارسنجی و نرمال‌سازی دقیق کدملی ایران، شماره موبایل و تاریخ تولد شرکت‌کنندگان."""

from __future__ import annotations

import re
from datetime import date

from django.core.exceptions import ValidationError

from apps.core.jalali import calculate_age, normalize_digits, parse_flexible_date

_IRAN_MOBILE_RE = re.compile(r"^09\d{9}$")
_NATIONAL_ID_RE = re.compile(r"^\d{10}$")


def normalize_and_validate_phone(value: str) -> str:
    """نرمال‌سازی شماره موبایل به فرمت استاندارد ۱۱ رقمی `09xxxxxxxxx` و بررسی صحت آن."""
    raw = normalize_digits(str(value or ""))
    raw = re.sub(r"[\s\-()]+", "", raw)
    if raw.startswith("+98"):
        raw = "0" + raw[3:]
    elif raw.startswith("0098"):
        raw = "0" + raw[4:]
    elif raw.startswith("98") and len(raw) == 12:
        raw = "0" + raw[2:]
    elif raw.startswith("9") and len(raw) == 10:
        raw = "0" + raw

    if not _IRAN_MOBILE_RE.match(raw):
        raise ValidationError(
            "شماره تلفن همراه معتبر نیست. لطفاً یک شماره ۱۱ رقمی با پیش‌شماره 09 وارد کنید."
        )
    return raw


def normalize_and_validate_national_id(value: str) -> str:
    """اعتبارسنجی کدملی ۱۰ رقمی ایران بر اساس الگوریتم رسمی رقم کنترل (Mod 11)."""
    raw = normalize_digits(str(value or ""))
    raw = re.sub(r"[\s\-]+", "", raw)

    if not _NATIONAL_ID_RE.match(raw):
        raise ValidationError("کد ملی باید دقیقاً ۱۰ رقم عددی باشد.")

    # کدهای ملی با تمام ارقام یکسان (مثلاً 1111111111 یا 0000000000) نامعتبر هستند
    if len(set(raw)) == 1:
        raise ValidationError("کد ملی واردشده معتبر نیست.")

    check_digit = int(raw[9])
    weighted_sum = sum(int(raw[i]) * (10 - i) for i in range(9))
    remainder = weighted_sum % 11
    valid = (remainder < 2 and check_digit == remainder) or (
        remainder >= 2 and check_digit == (11 - remainder)
    )
    if not valid:
        raise ValidationError("کد ملی واردشده از نظر رقم کنترل معتبر نیست.")
    return raw


def parse_and_validate_birth_date(value: str | date) -> date:
    """پارس و اعتبارسنجی تاریخ تولد (پشتیبانی از شمسی `1382/06/15` و میلادی `2003-09-06`)."""
    try:
        parsed = parse_flexible_date(value)
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc

    age = calculate_age(parsed)
    if age is None or age < 5 or age > 115:
        raise ValidationError("تاریخ تولد واردشده در بازهٔ سنی مجاز (۵ تا ۱۱۵ سال) قرار ندارد.")
    return parsed

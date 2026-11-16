"""تست‌های تقویم شمسی و پارس تاریخ تولد ورودی کاربر.

چرا حیاتی است؟
───────────────
همهٔ اعتبارسنجی‌های سنی مسابقه («متولد ۱۳۸۷ و بعد‌تر») از این ماژول
می‌گذرند. یک اشتباه در تبدیل شمسی↔میلادی یعنی یا یک نوجوان رد می‌شود یا
یک بزرگسال بی‌دلیل پذیرفته/رد می‌شود — و هر دو در داوری مسابقه قابل
شکایت‌اند. پس این‌جا با تاریخ‌های مرجع و حالت‌های واقعی ورودی کاربر
(ارقام فارسی، جداکننده‌های مختلف، اسفند ۳۰، سال کبیسه) تست می‌کنیم.
"""

from __future__ import annotations

from datetime import date, datetime

import pytest

from apps.core.jalali import (
    format_jalali_date,
    format_jalali_datetime,
    gregorian_to_jalali,
    jalali_to_gregorian,
    normalize_digits,
    parse_flexible_date,
    today_jalali,
)


# ── نرمال‌سازی ارقام ──────────────────────────────────────────────────────
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("۱۳۸۲/۰۶/۱۵", "1382/06/15"),
        ("١٣٨٢-٠٦-١٥", "1382-06-15"),
        ("  1382  ", "1382"),
        ("", ""),
    ],
)
def test_normalize_digits(raw: str, expected: str) -> None:
    """ارقام فارسی و عربی هر دو به لاتین تبدیل می‌شوند."""
    assert normalize_digits(raw) == expected


# ── تبدیل‌های مرجع ────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    ("gregorian", "jalali"),
    [
        ((2024, 3, 20), (1403, 1, 1)),  # نوروز ۱۴۰۳
        ((2025, 3, 21), (1404, 1, 1)),  # نوروز ۱۴۰۴
        ((2003, 9, 6), (1382, 6, 15)),
        ((1990, 1, 1), (1368, 10, 11)),
        ((2026, 11, 14), (1405, 8, 23)),
    ],
)
def test_conversion_matches_reference_dates(gregorian, jalali) -> None:
    """تبدیل دوطرفه با تاریخ‌های مرجع معروف می‌خواند."""
    assert gregorian_to_jalali(*gregorian) == jalali
    assert jalali_to_gregorian(*jalali) == gregorian


def test_roundtrip_over_a_year_span() -> None:
    """رفت‌وبرگشت روزانه در یک بازهٔ دو ساله دقیقاً همان تاریخ را می‌دهد."""
    for day_offset in range(0, 730, 7):
        d = date(2024, 1, 1).toordinal() + day_offset
        g = date.fromordinal(d)
        assert jalali_to_gregorian(*gregorian_to_jalali(g.year, g.month, g.day)) == (
            g.year,
            g.month,
            g.day,
        )


def test_invalid_jalali_inputs_raise() -> None:
    """ورودی نامعتبر (ماه ۱۳، روز ۳۲، سال بیرون بازه) خطای روشن می‌دهد."""
    with pytest.raises(ValueError):
        jalali_to_gregorian(1403, 13, 1)
    with pytest.raises(ValueError):
        jalali_to_gregorian(1403, 7, 31)
    with pytest.raises(ValueError):
        jalali_to_gregorian(1000, 1, 1)


def test_non_leap_esfand_30_is_rejected() -> None:
    """۳۰ اسفند در سال غیرکبیسه پذیرفته نمی‌شود."""
    with pytest.raises(ValueError):
        jalali_to_gregorian(1402, 12, 30)


# ── پارس ورودی کاربر ──────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "raw",
    ["1382/06/15", "۱۳۸۲/۰۶/۱۵", "1382-6-15", "1382.06.15", "1382 06 15"],
)
def test_parse_accepts_common_user_formats(raw: str) -> None:
    """همهٔ قالب‌هایی که کاربر ممکن است بنویسد به یک تاریخ می‌رسند."""
    assert parse_flexible_date(raw) == date(2003, 9, 6)


def test_parse_accepts_gregorian_year() -> None:
    """سال میلادی چهاررقمی هم درست تفسیر می‌شود."""
    assert parse_flexible_date("2003-09-06") == date(2003, 9, 6)


def test_parse_passes_through_date_objects() -> None:
    """ورودی که خودش `date`/`datetime` است دست‌نخورده برمی‌گردد."""
    assert parse_flexible_date(date(2003, 9, 6)) == date(2003, 9, 6)
    assert parse_flexible_date(datetime(2003, 9, 6, 10, 30)) == date(2003, 9, 6)


@pytest.mark.parametrize("raw", ["", "1382/06", "abc", "1382/06/15/2", "3000/01/01"])
def test_parse_rejects_garbage(raw: str) -> None:
    """ورودی بی‌معنا خطای قابل نمایش به کاربر می‌دهد، نه ۵۰۰."""
    with pytest.raises(ValueError):
        parse_flexible_date(raw)


# ── خروجی خوانا ───────────────────────────────────────────────────────────
def test_format_jalali_date_and_datetime() -> None:
    """قالب خروجی، رقم دو‌رقمی و جداکنندهٔ دلخواه را رعایت می‌کند."""
    assert format_jalali_date(date(2026, 11, 14)) == "1405/08/23"
    assert format_jalali_date(date(2026, 11, 14), separator="-") == "1405-08-23"
    assert format_jalali_date(None) == ""
    assert format_jalali_datetime(None) == ""


def test_today_jalali_is_a_valid_date_string() -> None:
    """تاریخ امروز قابل پارس است (یعنی قالبش درست است)."""
    value = today_jalali()
    assert len(value.split("-")) == 3
    assert parse_flexible_date(value) <= date.today()

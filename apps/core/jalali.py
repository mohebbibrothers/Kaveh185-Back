"""ابزارهای تقویم هجری شمسی (جلالی)، نرمال‌سازی ارقام و محاسبهٔ دقیق سن شرکت‌کنندگان.

چرا این ماژول وجود دارد:
    در فرم ثبت‌نام مسابقه کاوه ۱۸۵، کاربران ممکن است تاریخ تولد خود را به صورت
    شمسی (مثلاً `1382/06/15` یا `۱۳۸۲-۰۶-۱۵`) یا میلادی (`2003-09-06`) وارد کنند.
    این ماژول بدون نیاز به وابستگی خارجی سنگین، تبدیل دوطرفهٔ دقیق جلالی ↔ میلادی،
    نرمال‌سازی ارقام فارسی/عربی به لاتین و محاسبهٔ سن را انجام می‌دهد.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from zoneinfo import ZoneInfo

from django.utils import timezone

_PERSIAN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
_DATE_SPLIT_RE = re.compile(r"[-/.\s]+")


def normalize_digits(text: str) -> str:
    """تبدیل ارقام فارسی و عربی به ارقام استاندارد لاتین (`0-9`)."""
    return str(text or "").translate(_PERSIAN_DIGITS).strip()


def gregorian_to_jalali(gy: int, gm: int, gd: int) -> tuple[int, int, int]:
    """تبدیل تاریخ میلادی `(gy, gm, gd)` به تاریخ هجری شمسی `(jy, jm, jd)`."""
    g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    if gy > 1600:
        jy = 979
        gy -= 1600
    else:
        jy = 0
        gy -= 621
    gy2 = gy + 1 if gm > 2 else gy
    days = (
        (365 * gy)
        + ((gy2 + 3) // 4)
        - ((gy2 + 99) // 100)
        + ((gy2 + 399) // 400)
        - 80
        + gd
        + g_d_m[gm - 1]
    )
    jy += 33 * (days // 12053)
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    if days < 186:
        jm = 1 + (days // 31)
        jd = 1 + (days % 31)
    else:
        jm = 7 + ((days - 186) // 30)
        jd = 1 + ((days - 186) % 30)
    return jy, jm, jd


def jalali_to_gregorian(jy: int, jm: int, jd: int) -> tuple[int, int, int]:
    """تبدیل تاریخ هجری شمسی `(jy, jm, jd)` به تاریخ میلادی `(gy, gm, gd)`."""
    if jy < 1200 or jy > 1500:
        raise ValueError("سال شمسی خارج از بازهٔ معتبر است.")
    if jm < 1 or jm > 12:
        raise ValueError("ماه شمسی باید بین ۱ تا ۱۲ باشد.")
    max_day = 31 if jm <= 6 else 30
    if jd < 1 or jd > max_day:
        raise ValueError("روز ماه شمسی نامعتبر است.")

    jy_adj = jy - 979
    days = (
        (365 * jy_adj)
        + ((jy_adj // 33) * 8)
        + (((jy_adj % 33) + 3) // 4)
        + 78
        + jd
        + ((jm - 1) * 31 if jm < 7 else ((jm - 7) * 30) + 186)
    )
    gy = 1600 + 400 * (days // 146097)
    days %= 146097
    if days > 36524:
        days -= 1
        gy += 100 * (days // 36524)
        days %= 36524
        if days >= 365:
            days += 1
    gy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        gy += (days - 1) // 365
        days = (days - 1) % 365
    gd = days + 1
    is_leap = (gy % 4 == 0 and gy % 100 != 0) or (gy % 400 == 0)
    sal_a = [0, 31, 29 if is_leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    gm = 0
    while gm < 13 and gd > sal_a[gm]:
        gd -= sal_a[gm]
        gm += 1

    # بررسی صحت کبیسه بودن در صورت انتخاب ۳۰ اسفند
    check_jy, check_jm, check_jd = gregorian_to_jalali(gy, gm, gd)
    if (check_jy, check_jm, check_jd) != (jy, jm, jd):
        raise ValueError("تاریخ شمسی واردشده معتبر نیست (سال کبیسه نیست).")
    return gy, gm, gd


def format_jalali_date(value: date | datetime | None, *, separator: str = "/") -> str:
    """فرمت کردن تاریخ میلادی به رشتهٔ شمسی استاندارد (`1405/08/23`)."""
    if value is None:
        return ""
    if isinstance(value, datetime):
        tehran = ZoneInfo("Asia/Tehran")
        dt = value.astimezone(tehran) if timezone.is_aware(value) else value
        d = dt.date()
    else:
        d = value
    jy, jm, jd = gregorian_to_jalali(d.year, d.month, d.day)
    return f"{jy:04d}{separator}{jm:02d}{separator}{jd:02d}"


def format_jalali_datetime(value: datetime | None) -> str:
    """فرمت کردن زمان به رشتهٔ تاریخ و ساعت شمسی به وقت تهران (`1405/08/23 14:30:00`)."""
    if value is None:
        return ""
    tehran = ZoneInfo("Asia/Tehran")
    dt = value.astimezone(tehran) if timezone.is_aware(value) else value
    jy, jm, jd = gregorian_to_jalali(dt.year, dt.month, dt.day)
    return f"{jy:04d}/{jm:02d}/{jd:02d} {dt.hour:02d}:{dt.minute:02d}:{dt.second:02d}"


def today_jalali(*, separator: str = "-") -> str:
    """بازگرداندن تاریخ امروز به شمسی در منطقهٔ زمانی تهران."""
    now_tehran = timezone.now().astimezone(ZoneInfo("Asia/Tehran")).date()
    return format_jalali_date(now_tehran, separator=separator)


def parse_flexible_date(raw: str | date) -> date:
    """پارس هوشمند تاریخ تولد/فیلتر چه به صورت شمسی (`1380/05/14`) و چه میلادی (`2001-08-05`)."""
    if isinstance(raw, datetime):
        return raw.date()
    if isinstance(raw, date):
        return raw
    cleaned = normalize_digits(str(raw))
    parts = [p for p in _DATE_SPLIT_RE.split(cleaned) if p]
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        raise ValueError("فرمت تاریخ نامعتبر است. نمونهٔ معتبر: 1380/05/14 یا 2001-08-05.")
    year, month, day = int(parts[0]), int(parts[1]), int(parts[2])
    if 1250 <= year <= 1450:
        gy, gm, gd = jalali_to_gregorian(year, month, day)
        return date(gy, gm, gd)
    if 1900 <= year <= 2100:
        return date(year, month, day)
    raise ValueError("سال تاریخ واردشده خارج از محدودهٔ مجاز است.")


parse_Flexible_birth_date = parse_flexible_date


def calculate_age(birth_date: date | None, *, reference_date: date | None = None) -> int | None:
    """محاسبهٔ دقیق سن بر حسب سال کامل در تاریخ مرجع (یا امروز)."""
    if birth_date is None:
        return None
    ref = reference_date or timezone.now().astimezone(ZoneInfo("Asia/Tehran")).date()
    age = ref.year - birth_date.year - ((ref.month, ref.day) < (birth_date.month, birth_date.day))
    return max(0, age)

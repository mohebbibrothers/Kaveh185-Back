"""تنظیم بازهٔ واقعی مسابقه — جایگزین مقدار پیش‌فرض مدل.

چرا این دستور لازم است
──────────────────────
`ExamConfiguration.starts_at/ends_at` مقدار پیش‌فرضی دارند که نسبت به لحظهٔ
ساخت رکورد محاسبه می‌شود (`now() - 1h` و `now() + 7 روز`). این برای محیط
توسعه درست است، ولی روی سرور واقعی یعنی: **هر بار seed بزنید، مهلت آزمون
جابه‌جا می‌شود.** لندینگ هم همان را نشان می‌دهد و کاربر عدد بی‌معنی می‌بیند.

این دستور بازه را از پارامتر صریح می‌گیرد و در صورت نیاز، بازه را روی
پیکربندی موجود بازنویسی می‌کند. تاریخ‌ها را می‌توانید به شمسی بدهید
(`--starts 1405/08/29`) یا ISO (`--starts 2026-11-20T08:00:00`).

نمونه
─────
    # هفتهٔ بسیج ۱۴۰۵: ۲۹ آبان تا ۵ آذر
    python manage.py set_exam_window --starts 1405/08/29 --ends 1405/12/05

    # با ساعت مشخص (به وقت تهران)
    python manage.py set_exam_window \\
        --starts 1405/08/29T08:00 --ends 1405/09/05T23:59

    # فقط نمایش وضعیت فعلی بدون تغییر
    python manage.py set_exam_window --show

نکتهٔ منطقهٔ زمانی
──────────────────
اگر ساعت نداده باشید، شروع روی `00:00` و پایان روی `23:59:59` همان روز
به وقت `TIME_ZONE` پروژه (Asia/Tehran) تنظیم می‌شود — یعنی مهلت تا آخرین
لحظهٔ آن روز باز است، که همان چیزی است که برگزارکننده انتظار دارد.
"""

from __future__ import annotations

import re
from datetime import datetime, time, timedelta
from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.utils import timezone

from apps.exam.selectors import get_or_create_exam_configuration

_JALALI_RE = re.compile(r"^(?P<y>\d{4})[/-](?P<m>\d{1,2})[/-](?P<d>\d{1,2})$")
_ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}")
_JALALI_WITH_TIME_RE = re.compile(
    r"^(?P<y>\d{4})[/-](?P<m>\d{1,2})[/-](?P<d>\d{1,2})[T ](?P<H>\d{1,2}):(?P<M>\d{2})$"
)


def _jalali_to_gregorian(jy: int, jm: int, jd: int) -> tuple[int, int, int]:
    """تبدیل تاریخ شمسی به میلادی — الگوریتم استاندارد بدون وابستگی بیرونی.

    از الگوریتم شناخته‌شدهٔ `jalaali` استفاده می‌کند که در کتابخانه‌های
    متعدد فارسی تکرار شده است. صحت آن با تست قفل شده (نوروز ۱۴۰۵ = ۲۰ مارس ۲۰۲۶).
    """
    jy -= 979
    jm -= 1
    jd -= 1

    j_day_no = 365 * jy + (jy // 33) * 8 + ((jy % 33) + 3) // 4
    for i in range(jm):
        j_day_no += 31 if i < 6 else 30
    j_day_no += jd

    g_day_no = j_day_no + 79

    gy = 1600 + 400 * (g_day_no // 146097)
    g_day_no %= 146097
    leap = True
    if g_day_no >= 36525:
        g_day_no -= 1
        gy += 100 * (g_day_no // 36524)
        g_day_no %= 36524
        if g_day_no >= 365:
            g_day_no += 1
        else:
            leap = False

    gy += 4 * (g_day_no // 1461)
    g_day_no %= 1461
    if g_day_no >= 366:
        leap = False
        g_day_no -= 1
        gy += g_day_no // 365
        g_day_no %= 365

    gd = g_day_no + 1
    months = [31, 29 if leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    gm = 1
    for m_len in months:
        if gd <= m_len:
            break
        gd -= m_len
        gm += 1

    return gy, gm, gd


def _assert_jalali_year(year: int) -> None:
    """سال شمسی باید در بازهٔ معقول باشد تا ISO اشتباهاً شمسی تفسیر نشود.

    بدون این بررسی، «2026-11-20» اگر به شاخهٔ شمسی برسد سال ۲۶۴۷ میلادی
    می‌شود — خطای خاموشی که فقط وقتی مهلت آزمون شش قرن بعد باشد دیده می‌شود.
    """
    if not 1300 <= year <= 1500:
        raise CommandError(
            f"سال {year} برای تاریخ شمسی معقول نیست (بازهٔ مجاز: ۱۳۰۰ تا ۱۵۰۰). "
            "اگر تاریخ میلادی است، قالب ISO را با خط تیره بدهید: 2026-11-20"
        )


def _parse_boundary(raw: str, *, end_of_day: bool, tz: Any) -> datetime:
    """تجزیهٔ ورودی کاربر به datetime آگاه از منطقهٔ زمانی.

    دو شکل پذیرفته می‌شود: شمسی (`1405/08/29`) و ISO میلادی (`2026-11-20`).
    اگر ساعت داده نشده باشد، مرز روز اعمال می‌شود: شروع ۰۰:۰۰ و پایان ۲۳:۵۹:۵۹.
    """
    text = raw.strip()
    if not text:
        raise CommandError("مقدار خالی برای تاریخ مجاز نیست")

    hour, minute, second = (23, 59, 59) if end_of_day else (0, 0, 0)

    # ترتیب مهم است!
    # الگوی شمسی جداکنندهٔ «/» و «-» را هر دو می‌پذیرد، پس تاریخ ISO مثل
    # «2026-11-20» هم با آن تطبیق می‌کند و اگر شمسی تفسیر شود، سال ۲۰۲۶
    # هجری شمسی می‌شود — یعنی حدود سال ۲۶۴۷ میلادی. یک اشتباه ۶۰۰ ساله که
    # هیچ خطایی هم نمی‌دهد. بنابراین ISO را اول می‌سنجیم و سال شمسی را
    # محدود به بازهٔ معقول می‌کنیم.
    if _ISO_RE.match(text):
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if timezone.is_naive(dt):
            if dt.time() == time(0, 0) and end_of_day:
                dt = datetime.combine(dt.date(), time(hour, minute, second))
            dt = timezone.make_aware(dt, tz)
        return dt

    jalali_time = _JALALI_WITH_TIME_RE.match(text)
    if jalali_time:
        g = jalali_time.groupdict()
        year = int(g["y"])
        _assert_jalali_year(year)
        gy, gm, gd = _jalali_to_gregorian(year, int(g["m"]), int(g["d"]))
        naive = datetime(gy, gm, gd, int(g["H"]), int(g["M"]), 0)
        return timezone.make_aware(naive, tz)

    jalali = _JALALI_RE.match(text)
    if jalali:
        g = jalali.groupdict()
        year = int(g["y"])
        _assert_jalali_year(year)
        gy, gm, gd = _jalali_to_gregorian(year, int(g["m"]), int(g["d"]))
        naive = datetime.combine(timezone.datetime(gy, gm, gd).date(), time(hour, minute, second))
        return timezone.make_aware(naive, tz)

    raise CommandError(
        f"تاریخ «{raw}» قابل تفسیر نیست. "
        "شکل‌های پذیرفته‌شده: 1405/08/29 یا 1405/08/29T08:00 یا 2026-11-20"
    )


class Command(BaseCommand):
    """ثبت بازهٔ زمانی واقعی برگزاری مسابقه روی پیکربندی آزمون."""

    help = "بازهٔ واقعی شروع و پایان مسابقه را تنظیم می‌کند (شمسی یا ISO)."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--starts", help="تاریخ شروع (شمسی 1405/08/29 یا ISO)")
        parser.add_argument("--ends", help="تاریخ پایان (شمسی 1405/09/05 یا ISO)")
        parser.add_argument(
            "--show",
            action="store_true",
            help="فقط نمایش بازهٔ فعلی، بدون تغییر",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="بدون تأیید، بازهٔ موجود را بازنویسی کن",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        config = get_or_create_exam_configuration()
        tz = timezone.get_current_timezone()

        if options["show"] or not (options["starts"] and options["ends"]):
            if not options["show"]:
                raise CommandError("هر دو گزینهٔ --starts و --ends لازم است (یا --show)")
            self._report(config, tz, prefix="بازهٔ فعلی")
            return

        starts = _parse_boundary(options["starts"], end_of_day=False, tz=tz)
        ends = _parse_boundary(options["ends"], end_of_day=True, tz=tz)

        if ends <= starts:
            raise CommandError(
                f"پایان ({ends:%Y-%m-%d %H:%M}) باید بعد از شروع ({starts:%Y-%m-%d %H:%M}) باشد"
            )

        now = timezone.now()
        if ends < now and not options["force"]:
            raise CommandError(
                "بازهٔ داده‌شده در گذشته تمام می‌شود. اگر عمدی است، --force را اضافه کنید."
            )
        if starts > now + timedelta(days=365):
            raise CommandError("شروع بیش از یک سال بعد است — احتمالاً سال را اشتباه وارد کردید")

        config.starts_at = starts
        config.ends_at = ends
        config.save(update_fields=["starts_at", "ends_at", "updated_at"])

        self.stdout.write(self.style.SUCCESS("بازهٔ مسابقه ثبت شد."))
        self._report(config, tz, prefix="بازهٔ جدید")

        remaining = ends - now
        days = remaining.days
        hours = remaining.seconds // 3600
        self.stdout.write(f"  زمان باقی‌مانده تا پایان: {days} روز و {hours} ساعت")

    def _report(self, config: Any, tz: Any, *, prefix: str) -> None:
        starts_local = timezone.localtime(config.starts_at, tz)
        ends_local = timezone.localtime(config.ends_at, tz)
        self.stdout.write(f"{prefix}:")
        self.stdout.write(f"  شروع : {starts_local:%Y-%m-%d %H:%M} ({tz})")
        self.stdout.write(f"  پایان: {ends_local:%Y-%m-%d %H:%M} ({tz})")
        self.stdout.write(f"  مدت  : {(config.ends_at - config.starts_at).days} روز")

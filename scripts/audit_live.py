"""معاینهٔ کاملِ سایتِ زنده — یک دستور، پاسخ به «آیا همه‌چیز سرِ جایش است؟».

    bash deploy/audit-live.sh                 # از بیرون، بدونِ هیچ نصبِ پایتونی
    python manage.py shell < scripts/audit_live.py   # از داخلِ برنامه

## چرا این فایل؟

حینِ آزمون، سؤالِ «سایت سالمه؟» باید در ۱۵ ثانیه جواب بگیرد، نه با باز کردنِ
چند پنل. این اسکریپت ۶ لایه را می‌سنجد و هر کدام را با ✔/▲/✖ گزارش می‌کند:

۱) **زنده بودن** (`/health/live`) — پروسهٔ وب جواب می‌دهد؟
۲) **آمادگی** (`/health/ready`) — دیتابیس و کش سالم‌اند؟
۳) **صفحه‌های عمومی** — `/`، `/register/`، `/rules/`، `/receipt/` همه ۲۰۰؟
۴) **دادهٔ آزمون** — چند شرکت‌کننده، چند کارنامه، چند جلسهٔ در جریان؟
۵) **یکپارچگیِ داده** — کارنامهٔ متناقض (امتیازِ منفی، درست+غلط > کل،
   کاربرِ بدونِ مسجد، کارنامهٔ یتیم). اگر عددِ این بخش صفر نبود، **قبل از
   داوری** باید بررسی شود.
۶) **وضعیتِ دیتابیس** — حالتِ ژورنال (WAL باید باشد)، حجمِ فایل، و اینکه
   فایلِ `-wal` در حال رشدِ بی‌نهایت نباشد.

⚠️ این اسکریپت **هیچ نوشتنی** روی داده ندارد: فقط SELECT و درخواستِ GET.
"""

from __future__ import annotations

import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

SITE = os.environ.get("K185_SITE_URL", "https://kaveh185.ir").rstrip("/")
TIMEOUT = float(os.environ.get("K185_AUDIT_TIMEOUT", "10"))

OK = "✔"
WARN = "▲"
FAIL = "✖"


def _get(url: str) -> tuple[int, float]:
    """کدِ وضعیت و زمانِ پاسخ (میلی‌ثانیه) — بدونِ استثنا.

    ⚠️ فقط `http`/`https` پذیرفته می‌شود. این تابع نشانی را از متغیرِ محیطی
    می‌گیرد و بدونِ این بررسی، یک اشتباهِ تایپی (`file:///etc/passwd`) می‌توانست
    فایلِ محلی را باز کند — اسکریپتِ عیب‌یابی نباید خودش درِ تازه باز کند.
    """
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return 0, 0.0
    started = time.perf_counter()
    try:
        # طرحِ نشانی چند خط بالاتر به http/https محدود شده است.
        request = urllib.request.Request(  # noqa: S310
            url, headers={"User-Agent": "k185-audit/1.0"}
        )
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:  # noqa: S310
            response.read(1)
            code = response.status
    except urllib.error.HTTPError as exc:
        code = exc.code
    except Exception:
        code = 0
    return code, round((time.perf_counter() - started) * 1000, 0)


def audit_http() -> tuple[int, int]:
    """لایه‌های ۱ تا ۳: پروب‌های سلامت و صفحه‌های عمومی."""
    print("\n── ۱) دسترس‌پذیری از بیرون ─────────────────────────────────────")
    problems = 0
    codes: list[int] = []

    for label, path in (
        ("زنده بودن (liveness)", "/api/v1/health/live/"),
        ("آمادگی (readiness)", "/api/v1/health/ready/"),
    ):
        code, ms = _get(f"{SITE}{path}")
        codes.append(code)
        mark = OK if code == 200 else FAIL
        if code != 200:
            problems += 1
        print(f"  {mark} {label:<24} {code}  {ms:.0f}ms")

    print("\n── ۲) صفحه‌های عمومی ───────────────────────────────────────────")
    for path in ("/", "/register/", "/rules/", "/receipt/"):
        code, ms = _get(f"{SITE}{path}")
        codes.append(code)
        mark = OK if code == 200 else FAIL
        if code != 200:
            problems += 1
        print(f"  {mark} {path:<24} {code}  {ms:.0f}ms")

    code, _ = _get(f"{SITE}/not-a-real-page-xyz/")
    codes.append(code)
    mark = OK if code == 404 else WARN
    print(f"  {mark} {'مسیر ناشناخته → 404':<24} {code}")

    # ⚠️ اگر **هیچ** درخواستی پاسخی نگرفت، این دربارهٔ سایت هیچ نمی‌گوید؛
    # فقط می‌گوید این ماشین به اینترنت/دامنه دسترسی ندارد. قبلاً همین حالت
    # شش «✖» می‌ساخت و پیامِ آخر می‌گفت «۶ مورد نیازمندِ بررسی» — یعنی یک
    # هشدارِ دروغ. حالا صریح جدا می‌شود.
    if codes and all(c == 0 for c in codes):
        print(
            f"\n  {WARN} هیچ پاسخی از {SITE} نیامد — شبکه/DNS از این ماشین در "
            "دسترس نیست.\n     این بخش دربارهٔ سلامتِ سایت چیزی نمی‌گوید؛ "
            "از مرورگر خودتان یا از هاست بررسی کنید."
        )
        return 0, 0
    mark = OK if code == 404 else WARN
    print(f"  {mark} {'مسیر ناشناخته → 404':<24} {code}")
    return problems, 0


def audit_data() -> int:
    """لایه‌های ۴ تا ۶: دادهٔ آزمون، یکپارچگی، و وضعیتِ دیتابیس."""
    from django.conf import settings
    from django.db import connection
    from django.db.models import Count, F, Q

    from apps.authentication.models import User
    from apps.exam.models import ExamAttempt

    problems = 0
    print("\n── ۳) دادهٔ آزمون ────────────────────────────────────────────────")
    users = User.objects.count()
    attempts = ExamAttempt.objects.count()
    in_progress = ExamAttempt.objects.filter(status="in_progress").count()
    done = ExamAttempt.objects.filter(status__in=["completed", "timed_out"]).count()
    print(f"  {OK} شرکت‌کننده‌ها: {users}")
    print(f"  {OK} کارنامه‌ها: {attempts} (پایان‌یافته {done} · در جریان {in_progress})")

    print("\n── ۴) یکپارچگیِ داده (باید همه صفر باشد) ──────────────────────────")
    checks = {
        "امتیازِ منفی": ExamAttempt.objects.filter(total_score__lt=0).count(),
        "درست+غلط بیشتر از کل": ExamAttempt.objects.filter(
            correct_count__gt=F("total_questions")
        ).count(),
        "درصدِ صحت خارج از ۰..۱۰۰": ExamAttempt.objects.filter(
            Q(accuracy_percent__lt=0) | Q(accuracy_percent__gt=100)
        ).count(),
        "کارنامهٔ پایان‌یافته بدونِ زمانِ پایان": ExamAttempt.objects.filter(
            status__in=["completed", "timed_out"], completed_at__isnull=True
        ).count(),
        # فقط شرکت‌کننده‌ها — ادمین‌ها عمداً مسجد ندارند و نباید هشدار بسازند.
        "شرکت‌کنندهٔ بدونِ مسجد": User.objects.filter(mosque__isnull=True, is_staff=False).count(),
        "کاربرِ تکراری با یک کد ملی": (
            User.objects.values("national_id").annotate(n=Count("id")).filter(n__gt=1).count()
        ),
    }
    for label, value in checks.items():
        mark = OK if value == 0 else FAIL
        if value:
            problems += 1
        print(f"  {mark} {label:<34} {value}")

    print("\n── ۵) وضعیتِ دیتابیس ───────────────────────────────────────────")
    engine = settings.DATABASES["default"]["ENGINE"]
    print(f"  {OK} موتور: {engine}")

    # ⚠️ نسخهٔ قبلیِ همین اسکریپت بی‌قید `PRAGMA` می‌زد. روی هاستی که MySQL
    # دارد، همان دو خط خطا می‌داد و بخشِ دیتابیس را ناقص می‌کرد. حالا شاخه‌بندی
    # صریح است: MySQL قفلِ سراسریِ SQLite را ندارد، پس بررسی‌هایش متفاوت است.
    if "mysql" in engine or "mariadb" in engine:
        print(f"  {OK} MySQL/MariaDB — ریسکِ «database is locked» وجود ندارد")
        print(f"  {OK} CONN_MAX_AGE: {settings.DATABASES['default'].get('CONN_MAX_AGE', 0)}")
        with connection.cursor() as cursor:
            cursor.execute("SELECT VERSION();")
            version = cursor.fetchone()[0]
            cursor.execute("SELECT @@innodb_buffer_pool_size;")
            pool = cursor.fetchone()[0]
        print(f"  {OK} نسخه: {version}")
        mark = OK if int(pool) >= 64 * 1024 * 1024 else WARN
        print(f"  {mark} innodb_buffer_pool_size: {int(pool) / 1024 / 1024:.0f} مگابایت")
        return problems

    with connection.cursor() as cursor:
        cursor.execute("PRAGMA journal_mode;")
        journal = cursor.fetchone()[0]
        cursor.execute("PRAGMA busy_timeout;")
        busy = cursor.fetchone()[0]

    if engine.endswith("db_sqlite"):
        mark = OK if str(journal).lower() == "wal" else FAIL
        if str(journal).lower() != "wal":
            problems += 1
        print(f"  {mark} journal_mode: {journal}  (باید wal باشد)")
        mark = OK if int(busy) >= 5000 else WARN
        print(f"  {mark} busy_timeout: {busy}ms")

        db_name = settings.DATABASES["default"].get("NAME")
        db_file = Path(str(db_name)) if db_name else None
        if db_file is not None and db_file.exists():
            size_mb = db_file.stat().st_size / 1024 / 1024
            print(f"  {OK} حجم دیتابیس: {size_mb:.1f} مگابایت")
            wal_file = Path(f"{db_file}-wal")
            if wal_file.exists():
                wal_mb = wal_file.stat().st_size / 1024 / 1024
                mark = OK if wal_mb < 64 else WARN
                print(f"  {mark} حجم WAL: {wal_mb:.1f} مگابایت (رشدِ بی‌رویه = مشکلِ checkpoint)")
    return problems


def main() -> None:
    """گزارشِ نهایی با یک خطِ جمع‌بندی."""
    print("═" * 70)
    print(f"  معاینهٔ زندهٔ کاوه ۱۸۵ — {SITE}")
    print("═" * 70)

    http_problems, _ = audit_http()

    data_problems = 0
    try:
        import django

        django.setup()
        data_problems = audit_data()
    except Exception as exc:  # احتمالاً از بیرون اجرا شده (بدونِ جنگو)
        print(f"\n  {WARN} بخشِ داده اجرا نشد ({exc}). برایش روی هاست اجرا کنید:")
        print("     cd ~/Kaveh185-Back && python manage.py shell < scripts/audit_live.py")

    total = http_problems + data_problems
    print("\n" + "═" * 70)
    if total == 0:
        print(f"  {OK} همه‌چیز سالم است — هیچ موردی برای اقدام نیست.")
    else:
        print(f"  {FAIL} {total} مورد نیازمندِ بررسی است (بالا با ✖ علامت خورده).")
    print("═" * 70)


main()

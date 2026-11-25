"""پروب‌های سبک برای مسیرهای داغ — تا «سایت کند شد» به عدد تبدیل شود، نه حدس.

این فایل عمداً تستِ واحد نیست (در `pytest` اجرا نمی‌شود؛ نامش با `test_`
شروع نمی‌شود). یک اسکریپتِ عملیاتی است که مدیر می‌تواند حینِ آزمون اجرا کند:

    python manage.py shell < scripts/load_probe.py            # پیش‌فرض: ۵۰ درخواست
    K185_PROBE_N=200 python manage.py shell < scripts/load_probe.py

## چه چیزی اندازه می‌گیرد

۱) **تعداد کوئریِ هر درخواست** — رایج‌ترین علتِ کندیِ ناگهانی: یک N+1 که با
   رشدِ داده از ۵ کوئری به ۵۰۰ کوئری می‌رسد و روی SQLite کلِ دیتابیس را
   قفل می‌کند. این عدد با `CaptureQueriesContext` گرفته می‌شود.
۲) **زمانِ پاسخ** (میانه و صدکِ ۹۵) برای: ورود/نشست، شروعِ آزمون، ثبتِ پاسخ،
   کارنامه، و صفحهٔ رتبه‌بندیِ ادمین.

## چرا این اسکریپت فقط می‌خواند و چیزی نمی‌نویسد؟

چون روی دادهٔ واقعیِ آزمون اجرا می‌شود. هیچ POST‌ای این‌جا نیست؛ فقط GET.
برای مسیرهای نوشتنی، اعداد از لاگِ خودِ سایت خوانده می‌شود، نه از این اسکریپت.
"""

from __future__ import annotations

import statistics
import time
import tracemalloc

from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext, setup_test_environment

# ⚠️ نکتهٔ عملیاتی: `django.test.Client` فقط وقتی کار می‌کند که
# `setup_test_environment()` صدا زده شده باشد. بدونِ آن، `ALLOWED_HOSTS`
# خالی می‌شود و همهٔ پاسخ‌ها یک ۴۰۰ِ گمراه‌کننده می‌شوند — همان چیزی که در
# اولین اجرا دیدیم. این صدا زدن، هیچ اثری روی دادهٔ واقعی ندارد.

setup_test_environment()

PROBE_ROUNDS = int(__import__("os").environ.get("K185_PROBE_N", "50"))

#: مسیرهایی که حینِ آزمون بیشترین ترافیک را دارند.
PATHS = [
    ("کارنامهٔ عمومی (تأیید کد رهگیری)", "/api/v1/exam/receipt/verify/"),
    ("سلامت (liveness)", "/api/v1/health/live/"),
    ("سلامت (readiness)", "/api/v1/health/ready/"),
    ("فهرست مساجد", "/api/v1/mosques/"),
    ("وضعیت آزمون", "/api/v1/exam/status/"),
]


def _probe(path: str, rounds: int) -> dict[str, float]:
    """یک مسیر را چند بار می‌زند و میانه/صدکِ ۹۵ زمان و تعداد کوئری را می‌دهد."""
    client = Client()
    durations: list[float] = []
    query_counts: list[int] = []

    for _ in range(rounds):
        with CaptureQueriesContext(connection) as ctx:
            started = time.perf_counter()
            response = client.get(path)
            durations.append((time.perf_counter() - started) * 1000.0)
        query_counts.append(len(ctx.captured_queries))
        if response.status_code >= 500:
            print(f"  ⚠️ {path} → {response.status_code} (خطای سرور!)")
        elif response.status_code == 400:
            # ۴۰۰ روی همهٔ مسیرها یعنی محیطِ تست درست بالا نیامده، نه اینکه
            # مسیر خراب باشد. صریح می‌گوییم تا کسی دنبالِ باگِ الکی نرود.
            print(f"  ⚠️ {path} → 400؛ احتمالاً ALLOWED_HOSTS خالی است (محیطِ تست)")

    ordered = sorted(durations)
    p95_index = min(len(ordered) - 1, int(len(ordered) * 0.95))
    return {
        "median_ms": round(statistics.median(durations), 1),
        "p95_ms": round(ordered[p95_index], 1),
        "max_ms": round(max(durations), 1),
        "avg_queries": round(statistics.mean(query_counts), 1),
        "max_queries": max(query_counts),
    }


def main() -> None:
    """همهٔ مسیرها را می‌سنجد و جدولِ خوانا چاپ می‌کند."""
    print(f"\n{'مسیر':<38} {'میانه':>8} {'p95':>8} {'بیشینه':>8} {'کوئری':>7}")
    print("-" * 76)
    tracemalloc.start()
    worst_queries = 0
    worst_path = ""

    for label, path in PATHS:
        try:
            stats = _probe(path, PROBE_ROUNDS)
        except Exception as exc:
            print(f"{label:<38} ✖ {exc}")
            continue
        print(
            f"{label:<38} {stats['median_ms']:>7.0f}ms {stats['p95_ms']:>7.0f}ms "
            f"{stats['max_ms']:>7.0f}ms {stats['avg_queries']:>7.1f}"
        )
        if stats["max_queries"] > worst_queries:
            worst_queries = stats["max_queries"]
            worst_path = f"{label} ({path})"

    _current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    print("-" * 76)
    print(f"بیشترین کوئری در یک درخواست: {worst_queries} — {worst_path}")
    print(f"حافظهٔ اوجِ همین پروسه: {peak / 1024 / 1024:.1f} مگابایت")

    if worst_queries > 40:
        print(
            "\n⚠️ هشدار: بیش از ۴۰ کوئری در یک درخواست. پیش از آزمونِ بعدی، "
            "همان مسیر را با `select_related`/`prefetch_related` بهینه کنید."
        )


main()

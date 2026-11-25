"""تست‌های لایهٔ کشِ «سرریز» — تضمینِ «صفحهٔ خطا نمی‌دهیم».

## چرا این تست مهم است

هدفِ این لایه دقیقاً وقتی است که **تست کردنش سخت است**: وسطِ آزمون و با
دیتابیسِ تحتِ فشار. اگر تست نشود، تنها راهِ فهمیدنِ اینکه کار می‌کند یا نه،
روزِ حادثه است. پس سناریوها را عمداً این‌جا می‌سازیم:

۱) کشِ خالی ⇒ تولید می‌کند و ذخیره می‌کند.
۲) کشِ داغ ⇒ تولید را **صدا نمی‌زند** (این ادعای اصلی است).
۳) تولیدکننده خطا داد ولی نسخهٔ قبلی هست ⇒ نسخهٔ قبلی برمی‌گردد، نه استثنا.
۴) تولیدکننده خطا داد و نسخهٔ قبلی هم نیست ⇒ استثنا بالا می‌آید (تا فراخوان
   بتواند «صفرِ امن» بدهد؛ ما هرگز خطا را بی‌صدا نمی‌بلعیم).
۵) کلیدهای ادمین با فیلترهای متفاوت به هم نشت نمی‌کنند.
"""

from __future__ import annotations

import pytest
from django.core.cache import cache

from apps.reporting.caching import (
    admin_ranking_cache_scope,
    cached_with_stale_fallback,
    invalidate_rank_caches,
)


@pytest.fixture(autouse=True)
def _clean_cache():
    cache.clear()
    yield
    cache.clear()


def test_cold_cache_computes_and_stores() -> None:
    calls: list[int] = []

    def producer() -> int:
        calls.append(1)
        return 42

    assert cached_with_stale_fallback(key="x", ttl_seconds=5, producer=producer) == 42
    assert len(calls) == 1

    # بارِ دوم: از کش می‌خواند، تولیدکننده دوباره صدا زده نمی‌شود.
    assert cached_with_stale_fallback(key="x", ttl_seconds=5, producer=producer) == 42
    assert len(calls) == 1, "کشِ داغ نباید تولیدکننده را صدا بزند"


def test_producer_failure_serves_stale_copy() -> None:
    """قلبِ ماجرا: دیتابیس خطا می‌دهد، ولی کاربر عددِ قدیمی می‌بیند نه ۵۰۰."""
    cached_with_stale_fallback(key="y", ttl_seconds=1, producer=lambda: "نسخهٔ سالم")
    cache.delete("rank:y")  # نسخهٔ تازه را پاک می‌کنیم؛ نسخهٔ سرریز می‌ماند

    def broken() -> str:
        raise RuntimeError("database is locked")

    result = cached_with_stale_fallback(key="y", ttl_seconds=1, producer=broken)
    assert result == "نسخهٔ سالم"


def test_producer_failure_without_stale_copy_raises() -> None:
    def broken() -> str:
        raise RuntimeError("database is locked")

    with pytest.raises(RuntimeError):
        cached_with_stale_fallback(key="never-cached", ttl_seconds=1, producer=broken)


def test_invalidate_clears_both_fresh_and_stale() -> None:
    cached_with_stale_fallback(key="z", ttl_seconds=60, producer=lambda: 7)
    invalidate_rank_caches("z")

    calls: list[int] = []

    def producer() -> int:
        calls.append(1)
        return 8

    assert cached_with_stale_fallback(key="z", ttl_seconds=60, producer=producer) == 8
    assert len(calls) == 1, "پس از ابطال باید دوباره محاسبه شود"


def test_admin_scope_differs_per_filter_set() -> None:
    """دو تبِ ادمین با فیلترِ متفاوت نباید فهرستِ هم را ببینند."""
    a = admin_ranking_cache_scope({"mosque_id": 3, "status": "completed"})
    b = admin_ranking_cache_scope({"mosque_id": 4, "status": "completed"})
    c = admin_ranking_cache_scope({"status": "completed", "mosque_id": 3})
    assert a != b
    assert a == c, "ترتیبِ پارامترها نباید کلید را عوض کند"
    assert admin_ranking_cache_scope({}) == "admin-list:default"


@pytest.mark.django_db
def test_wal_pragmas_are_applied() -> None:
    """بک‌اندِ سفارشی باید WAL و انتظارِ قفل را واقعاً تنظیم کند (نه فقط ادعا).

    ⚠️ در تست‌ها دیتابیس `:memory:` است و `journal_mode` حافظه‌ای می‌ماند —
    یعنی همین‌جا نمی‌شود WAL را دید. پس همان PRAGMAهایی را می‌سنجیم که روی
    حافظه هم معنا دارند و وجودِ بک‌اند را قفل می‌کنیم؛ رفتارِ WAL روی فایل با
    `scripts/load_probe.py` و در محیطِ واقعی سنجیده می‌شود.
    """
    from django.conf import settings
    from django.db import connection

    assert settings.DATABASES["default"]["ENGINE"] == "apps.core.db_sqlite", (
        "بک‌اندِ SQLite باید سفارشی باشد؛ وگرنه در پیکِ آزمون «database is locked» برمی‌گردد"
    )

    with connection.cursor() as cursor:
        cursor.execute("PRAGMA busy_timeout;")
        assert cursor.fetchone()[0] == 20000, "انتظارِ قفل باید ۲۰ ثانیه باشد"
        cursor.execute("PRAGMA cache_size;")
        assert cursor.fetchone()[0] == -65536

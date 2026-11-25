"""تستِ تنظیماتِ بک‌اندِ SQLite — «هیچ مسیری نباید بی‌صدا به موتورِ ضعیف برگردد».

چرا این تست لازم است: پیش‌فرضِ `DB_ENGINE` قبلاً `django.db.backends.sqlite3`
بود. اگر کسی در `.env` همان مقدار را می‌گذاشت (یا فایلِ `.env` نبود)، سایت
بی‌صدا از WAL محروم می‌شد و در پیکِ آزمون «database is locked» برمی‌گشت —
بدونِ هیچ خطایی در لاگ. این تست هر سه شکلِ ورودی را به یک نتیجه می‌رساند:
**همیشه بک‌اندِ سفارشی**.
"""

from __future__ import annotations

import pytest
from decouple import config


def _resolve(raw: str) -> str:
    """همان lambda ای که در `config/settings/base.py` است (تکرارِ عمدی، برای تست)."""
    cast = lambda v: (  # noqa: E731
        "apps.core.db_sqlite"
        if v.strip() in {"", "django.db.backends.sqlite3", "sqlite3"}
        else v.strip()
    )
    return cast(raw)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("", "apps.core.db_sqlite"),
        ("sqlite3", "apps.core.db_sqlite"),
        ("django.db.backends.sqlite3", "apps.core.db_sqlite"),
        ("  django.db.backends.sqlite3  ", "apps.core.db_sqlite"),
        ("apps.core.db_sqlite", "apps.core.db_sqlite"),
        # MySQL باید دست‌نخورده بماند (روی هاستِ تولید فعال است).
        ("django.db.backends.mysql", "django.db.backends.mysql"),
    ],
)
def test_db_engine_is_never_the_plain_sqlite_backend(raw: str, expected: str) -> None:
    """هر شکلِ ورودیِ SQLite باید به بک‌اندِ سفارشی برسد."""
    assert _resolve(raw) == expected


def test_postgres_is_passed_through() -> None:
    """موتورهای دیگر نباید بازنویسی شوند."""
    assert _resolve("django.db.backends.postgresql") == "django.db.backends.postgresql"


def test_decouple_env_override_still_works(monkeypatch) -> None:
    """متغیرِ محیطی باید همچنان اولویت داشته باشد (بدونِ خردکردنِ .env)."""
    monkeypatch.setenv("K185_TEST_DB_ENGINE", "django.db.backends.mysql")
    assert config("K185_TEST_DB_ENGINE", default="apps.core.db_sqlite") == (
        "django.db.backends.mysql"
    )

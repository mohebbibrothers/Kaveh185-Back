"""تستِ واقعیِ بک‌اندِ SQLite — نه فقط وجودِ نامش.

در CI یک شغلِ دوم روی MariaDB اجرا می‌شود و آن‌جا `apps.core.db_sqlite` هیچ‌وقت
بار نمی‌شود؛ نتیجه: پوششِ صفر و افتادنِ گیتِ ۹۰٪. این تست همان wrapper را
مستقیم روی یک دیتابیسِ `:memory:` می‌سازد تا رفتارش — مستقل از موتورِ فعالِ
پروژه — سنجیده شود.

⚠️ `journal_mode=WAL` روی `:memory:` معنا ندارد (SQLite آن را به `memory`
می‌برد)؛ پس این‌جا همان چیزهایی را می‌سنجیم که روی حافظه هم معنا دارند:
`busy_timeout`, `cache_size`, `temp_store` و اینکه **هیچ استثنایی** بالا نرود.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import pytest

from apps.core.db_sqlite.base import DatabaseWrapper


def _wrapper() -> DatabaseWrapper:
    """یک wrapper با تنظیماتِ کمینه می‌سازد (بدونِ راه‌اندازیِ کاملِ جنگو)."""
    settings_dict: dict[str, Any] = {
        "ENGINE": "apps.core.db_sqlite",
        # ⚠️ روی دیسکِ موقت، نه `:memory:`: یک اتصالِ دوم به `:memory:` دیتابیسِ
        # جدا می‌سازد و PRAGMAهای این تست به اتصالِ اصلیِ جنگو نشت نمی‌کند —
        # در اجرای واقعی هم دیدیم که همین باعث شد `cache_size` مقدارِ ۲۰۰۰
        # (پیش‌فرض) را نشان دهد. فایلِ یکتا هم تا آلودگی بین تست‌ها نباشد.
        "NAME": str(Path(tempfile.mkdtemp(prefix="k185-wrapper-")) / "test.sqlite3"),
        "ATOMIC_REQUESTS": False,
        "AUTOCOMMIT": True,
        "CONN_MAX_AGE": 0,
        "CONN_HEALTH_CHECKS": False,
        "OPTIONS": {},
        "TIME_ZONE": None,
        "USER": "",
        "PASSWORD": "",
        "HOST": "",
        "PORT": "",
        "TEST": {"NAME": None, "CHARSET": None, "COLLATION": None, "MIRROR": None},
    }
    return DatabaseWrapper(settings_dict, alias="wrapper-test")


def test_get_connection_params_sets_busy_timeout() -> None:
    """انتظارِ قفل باید در سطحِ `sqlite3.connect` هم ست شود، نه فقط PRAGMA."""
    params = _wrapper().get_connection_params()
    assert params["timeout"] == 20.0


@pytest.mark.django_db
def test_pragmas_are_applied_on_real_connection() -> None:
    """روی یک اتصالِ واقعی، PRAGMAها باید اثر کنند و استثنا ندهند."""
    wrapper = _wrapper()
    wrapper.connect()

    with wrapper.cursor() as cursor:
        cursor.execute("PRAGMA busy_timeout;")
        assert cursor.fetchone()[0] == 20000
        cursor.execute("PRAGMA cache_size;")
        assert cursor.fetchone()[0] == -65536
        cursor.execute("PRAGMA temp_store;")
        assert cursor.fetchone()[0] == 2  # MEMORY

    wrapper.close()


@pytest.mark.django_db
def test_broken_pragma_does_not_kill_the_connection(monkeypatch) -> None:
    """اگر میزبان اجازهٔ یک PRAGMA را نداد، اتصال نباید بمیرد.

    این همان سناریوی هاستِ اشتراکی است: فایل‌سیستمی که `mmap` یا فایل‌های
    جانبیِ WAL را نمی‌پذیرد. اگر استثنا بالا برود، **هر** درخواست می‌شکند —
    یعنی خودمان قطعی ساخته‌ایم.

    ⚠️ `sqlite3.Cursor` یک نوعِ immutable است و monkeypatch نمی‌شود؛ پس به‌جای
    دست‌کاریِ درایور، یک PRAGMAِ عمداً خراب به فهرستِ خودِ wrapper اضافه می‌کنیم.
    این همان مسیرِ کد را می‌آزماید (`try/except` دورِ هر PRAGMA).
    """
    wrapper = _wrapper()
    monkeypatch.setattr(
        DatabaseWrapper,
        "_PRAGMAS",
        (("bogus", "PRAGMA definitely_not_a_real_pragma=1;"), *DatabaseWrapper._PRAGMAS),
    )
    wrapper.connect()  # نباید استثنا بدهد

    with wrapper.cursor() as cursor:
        cursor.execute("PRAGMA busy_timeout;")
        assert cursor.fetchone()[0] == 20000, "بقیهٔ PRAGMAها باید اعمال شوند"

    wrapper.close()

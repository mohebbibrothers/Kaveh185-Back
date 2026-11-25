"""بک‌اندِ SQLite با WAL و انتظارِ قفل — تفاوتِ «کند» و «قطع».

## مشکل، دقیقاً

SQLite در حالتِ پیش‌فرض با ژورنالِ `DELETE` کار می‌کند. در آن حالت **نویسنده،
کلِ دیتابیس را قفل می‌کند** و هر خواننده‌ای که در آن لحظه سراغِ فایل برود،
با `database is locked` می‌خورد. روی هاستِ اشتراکیِ cPanel (که Passenger چند
پروسهٔ هم‌زمان دارد) این یعنی: وقتی ۳۰۰ نفر هم‌زمان پاسخ می‌فرستند، هر
درخواستی که فقط می‌خواست *بخواند* ممکن است ۵۰۰ بگیرد. این تنها باگی است که
می‌تواند سایت را در دقیقهٔ اوج **واقعاً از دسترس خارج کند**، بدونِ اینکه
هیچ کدی عوض شده باشد.

با `WAL`:
* نوشتن‌ها در فایلِ `-wal` کنارِ دیتابیس می‌نشینند و قفلِ انحصاری حذف می‌شود؛
* خواننده‌ها **هم‌زمان با** نویسنده کار می‌کنند (عکسِ وضعیتِ قبل)؛
* `busy_timeout` جای خطای فوری، تا N میلی‌ثانیه صبر می‌کند.

با `synchronous=NORMAL` (امنِ همین حالتِ WAL) هر COMMIT دیگر منتظرِ
`fsync`ِ دیسک نمی‌ماند؛ روی دیسکِ کندِ هاستِ اشتراکی این تفاوت چند برابری است.
⚠️ در حالتِ WAL، خطرِ از دست دادنِ داده فقط وقتی است که **برق/کرنل** وسطِ کار
بمیرد — نه وقتی فقط پروسهٔ پایتون بمیرد. برای این کاربرد (آزمونِ آنلاین) این
معاوضه درست است؛ اگر روزی تراکنش‌های مالی اضافه شد، `synchronous=FULL`.

## چرا به‌جای سیگنال، بک‌اند؟

تنظیمِ `PRAGMA` با یک `connection_created`-سیگنال هم ممکن است، ولی آن روش
برای هر اتصالِ تازه باید اجرا شود و اگر جایی فراموش شود، بی‌صدا از کار
می‌افتد. با زیرکلاسِ بک‌اند، **هر** اتصالی که جنگو باز می‌کند (وب، دستورهای
`manage.py`، Celery) همین رفتار را دارد — و اگر کسی `DB_ENGINE` را عوض کند،
این فایل کاملاً بی‌اثر می‌شود (بازگشتِ بی‌خطر).
"""

from __future__ import annotations

import logging
import os
from typing import Any

from django.db.backends.sqlite3.base import DatabaseWrapper as SQLiteDatabaseWrapper

logger = logging.getLogger(__name__)


class DatabaseWrapper(SQLiteDatabaseWrapper):
    """SQLite با تنظیمِ WAL، انتظارِ قفل و همگام‌سازیِ سبک."""

    def get_connection_params(self) -> dict[str, Any]:
        """افزودنِ `timeout` به پارامترهای اتصال (انتظارِ قفل در سطحِ sqlite3)."""
        params = super().get_connection_params()
        # ۲۰ ثانیه: در پیکِ آزمون، صفِ نوشتن کوتاه است؛ ۵ ثانیه کم بود.
        params.setdefault("timeout", float(os.environ.get("SQLITE_BUSY_TIMEOUT", "20")))
        return params

    #: PRAGMAهایی که اگر اجرا نشوند، سایت نباید بخوابد.
    #: ⚠️ این محافظ **حیاتی** است: روی هاستِ اشتراکی ممکن است پوشهٔ دیتابیس
    #: مجوزِ نوشتن برای فایل‌های جانبیِ WAL نداشته باشد، یا فایل‌سیستم از
    #: صفحاتِ حافظه‌ای پشتیبانی نکند. در آن حالت `PRAGMA` خطا می‌دهد و اگر
    #: استثنا را بالا بدهیم، **هر اتصال** می‌شکند — یعنی خودمان قطعی می‌سازیم.
    #: پس هر PRAGMA جداگانه امتحان می‌شود و شکستش فقط لاگ می‌شود.
    _PRAGMAS: tuple[tuple[str, str], ...] = (
        ("journal_mode", "PRAGMA journal_mode=WAL;"),
        ("synchronous", "PRAGMA synchronous=NORMAL;"),
        ("busy_timeout", "PRAGMA busy_timeout=20000;"),
        ("cache_size", "PRAGMA cache_size=-65536;"),
        ("temp_store", "PRAGMA temp_store=MEMORY;"),
        ("wal_autocheckpoint", "PRAGMA wal_autocheckpoint=400;"),
        ("mmap_size", "PRAGMA mmap_size=268435456;"),
    )

    def init_connection_state(self) -> None:
        """اجرای PRAGMAهای عملکردی روی هر اتصالِ تازه — هرگز استثنا نمی‌دهد."""
        super().init_connection_state()
        for name, statement in self._PRAGMAS:
            try:
                with self.cursor() as cursor:
                    cursor.execute(statement)
            except Exception:  # pragma: no cover - وابسته به فایل‌سیستمِ میزبان
                logger.warning(
                    "PRAGMA %s اجرا نشد؛ سایت با تنظیماتِ پیش‌فرض ادامه می‌دهد",
                    name,
                    exc_info=True,
                )

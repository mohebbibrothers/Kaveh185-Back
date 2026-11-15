"""پکیج پیکربندی مرکزی پروژه جنگو سامانه کاوه ۱۸۵."""

from __future__ import annotations

# ─────────────────────────────────────────────────────────────────────────────
# درایور MySQL
#
# چرا اینجا؟ چون جنگو برای ENGINE=...mysql قبل از هر چیز `import MySQLdb` می‌کند.
# روی هاست اشتراکیِ cPanel، کامپایل mysqlclient نیاز به هدرهای MySQL و ابزار
# بیلد دارد که معمولاً نیست؛ PyMySQL یک درایور خالص پایتون است و کافی. با
# install_as_MySQLdb، PyMySQL خودش را جای MySQLdb جا می‌زند.
#
# این کار فقط وقتی لازم است که واقعاً MySQL انتخاب شده باشد؛ روی SQLite/Postgres
# هیچ هزینه‌ای ندارد (import سبک است و خطا هم بلعیده می‌شود).
# ─────────────────────────────────────────────────────────────────────────────
try:  # pragma: no cover — وابسته به محیط استقرار
    import pymysql

    pymysql.install_as_MySQLdb()
except ImportError:  # pragma: no cover
    pass

from .celery import app as celery_app

__all__ = ("celery_app",)

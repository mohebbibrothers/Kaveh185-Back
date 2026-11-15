"""قفل تصمیم «کدام پایگاه داده» تا بی‌صدا برنگردد.

چرا این تست وجود دارد
─────────────────────
روی هاست cPanel این پروژه، دو پایگاه داده نصب است:

* PostgreSQL **13.23** — Django 6.1 حداقل **۱۵** می‌خواهد → بدون وصله کار نمی‌کند.
* MariaDB **11.4.13**    — Django 6.1 حداقل **10.11** می‌خواهد → پشتیبانی رسمی دارد.

پس MariaDB انتخاب شد. این تصمیم یک‌بار با دلیل گرفته شد؛ این تست جلوی
بازگشت اتفاقی به PostgreSQL قدیمی (یا MySQL قدیمی) را می‌گیرد.

اگر روزی PostgreSQL هاست به ۱۵+ ارتقا یافت و خواستید برگردید، این تست
باید آگاهانه و همراه با به‌روزرسانی همین توضیح تغییر کند — نه تصادفی.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

# ریشهٔ مخزن: از apps/core/tests/ سه پله بالا
REPO_ROOT = Path(__file__).resolve().parents[3]
MAKE_ENV = REPO_ROOT / "deploy" / "host" / "make-env.sh"

# حداقل نسخه‌هایی که Django 6.1 خودش اعمال می‌کند (سورس:
# django/db/backends/mysql/features.py و .../postgresql/features.py)
DJANGO_61_MINIMUM = {
    "mysql": {"mariadb": (10, 11), "mysql": (8, 4)},
    "postgresql": (15,),
}

# نسخه‌های واقعیِ تأییدشدهٔ هاست (با `mysql --version` و `psql --version`)
HOST_VERSIONS = {"mariadb": (11, 4, 13), "postgresql": (13, 23)}


def _parse_version(text: str) -> tuple[int, ...]:
    """«11.4.13-MariaDB» → (11, 4, 13)"""
    head = re.split(r"[-+\s]", text.strip(), maxsplit=1)[0]
    return tuple(int(part) for part in head.split("."))


class TestHostDatabaseVersions:
    """سنجش نسخه‌های هاست در برابر آستانه‌های Django 6.1."""

    def test_mariadb_on_host_passes_django_gate(self) -> None:
        """MariaDB 11.4.13 هاست ≥ 10.11 است، پس رسمی پشتیبانی می‌شود."""
        host = HOST_VERSIONS["mariadb"]
        required = DJANGO_61_MINIMUM["mysql"]["mariadb"]
        assert host >= required, f"MariaDB هاست {host} کمتر از حداقل Django 6.1 {required} است"

    def test_postgresql_on_host_fails_django_gate(self) -> None:
        """PostgreSQL 13.23 هاست < 15 است — این دلیل انتخاب MariaDB است.

        این تست «شکست را تأیید می‌کند»، نه قابلیت. اگر روزی هاست ارتقا یافت
        و این تست شکست، یعنی خبر خوبی است: باید تصمیم را بازبینی کنید.
        """
        host = HOST_VERSIONS["postgresql"]
        required = DJANGO_61_MINIMUM["postgresql"]
        assert host < required, (
            f"PostgreSQL هاست اکنون {host} است و {required} را پاس می‌کند — "
            "وقت بازبینی تصمیم پایگاه داده است"
        )

    def test_mysql_84_gate_is_not_met_by_mariadb_comparison(self) -> None:
        """MariaDB با آستانهٔ MySQL سنجیده نمی‌شود (۸.۴ در برابر ۱۰.۱۱).

        اگر کسی اشتباهاً نسخهٔ MariaDB را با آستانهٔ MySQL مقایسه کند،
        ۱۱.۴ ≥ ۸.۴ می‌شود و نتیجه درست است ولی دلیل غلط. این تست تفکیک
        دو مسیر را قفل می‌کند.
        """
        mariadb_host = HOST_VERSIONS["mariadb"]
        assert mariadb_host >= DJANGO_61_MINIMUM["mysql"]["mariadb"]
        # آستانهٔ MySQL عدد متفاوتی است و نباید جابه‌جا استفاده شود
        assert DJANGO_61_MINIMUM["mysql"]["mysql"] != DJANGO_61_MINIMUM["mysql"]["mariadb"]


class TestMakeEnvScript:
    """اسکریپت ساخت .env باید MariaDB را پیش‌فرض بدهد."""

    @pytest.fixture(scope="class")
    def script_text(self) -> str:
        assert MAKE_ENV.is_file(), f"{MAKE_ENV} پیدا نشد"
        return MAKE_ENV.read_text(encoding="utf-8")

    def test_default_engine_is_mysql(self, script_text: str) -> None:
        """DB_ENGINE پیش‌فرض باید mysql باشد، نه postgresql قدیمی."""
        match = re.search(r'^DB_ENGINE="([^"]+)"', script_text, re.MULTILINE)
        assert match, "خط DB_ENGINE پیش‌فرض در make-env.sh پیدا نشد"
        assert match.group(1) == "django.db.backends.mysql"

    def test_default_port_is_mariadb_port(self, script_text: str) -> None:
        """پورت پیش‌فرض ۳۳۰۶ باشد نه ۵۴۳۲."""
        assert 'DB_PORT="3306"' in script_text
        assert 'DB_PORT="5432"' not in script_text

    def test_engine_is_overridable(self, script_text: str) -> None:
        """--db-engine باید وجود داشته باشد تا مسیر جایگزین قفل نشود."""
        assert "--db-engine)" in script_text

    def test_script_is_valid_bash(self) -> None:
        """اسکریپت باید از bash -n سالم بگذرد."""
        import subprocess

        result = subprocess.run(
            ["bash", "-n", str(MAKE_ENV)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, f"خطای نحوی bash: {result.stderr}"


class TestPyMySQLDriver:
    """درایور باید بدون کامپایل کار کند — شرط بقا روی هاست اشتراکی."""

    def test_pymysql_installable_and_importable(self) -> None:
        """PyMySQL باید نصب و قابل import باشد (درایور خالص پایتون)."""
        pymysql = pytest.importorskip("pymysql")
        # توجه: pymysql.__version__ نسخهٔ پروتکل است (۲.۲.۸)، نه نسخهٔ بسته.
        # نسخهٔ واقعی در VERSION تاپل است.
        assert isinstance(pymysql.VERSION, tuple)
        assert pymysql.VERSION >= (1, 2, 0), f"PyMySQL {pymysql.VERSION} برای Django 6.1 قدیمی است"

    def test_install_as_mysqldb_is_wired_in_config(self) -> None:
        """config/__init__.py باید install_as_MySQLdb را صدا بزند.

        بدون این، Django هنگام `ENGINE=...mysql` تلاش می‌کند mysqlclient
        را import کند که روی هاست اشتراکی کامپایل نمی‌شود.
        """
        config_init = REPO_ROOT / "config" / "__init__.py"
        text = config_init.read_text(encoding="utf-8")
        assert "install_as_MySQLdb" in text
        assert "import pymysql" in text


class TestTestSettingsSwitch:
    """settings.test باید هم SQLite (CI) و هم دیتابیس واقعی را بپذیرد."""

    def test_default_is_sqlite_for_ci_speed(self) -> None:
        """بدون DB_ENGINE، تست‌ها روی SQLite اجرا شوند تا CI سریع بماند."""
        env_backup = {k: os.environ.pop(k, None) for k in ("DB_ENGINE", "DB_NAME")}
        try:
            import importlib

            import config.settings.test as test_settings

            importlib.reload(test_settings)
            assert test_settings.DATABASES["default"]["ENGINE"].endswith("sqlite3")
        finally:
            for key, value in env_backup.items():
                if value is not None:
                    os.environ[key] = value

    def test_db_engine_env_overrides_to_real_backend(self) -> None:
        """با DB_ENGINE در محیط، تست باید روی موتور واقعی اجرا شود."""
        env_backup = {k: os.environ.get(k) for k in ("DB_ENGINE", "DB_NAME", "DB_USER")}
        os.environ["DB_ENGINE"] = "django.db.backends.mysql"
        os.environ["DB_NAME"] = "example_db"
        os.environ["DB_USER"] = "example_user"
        try:
            import importlib

            import config.settings.test as test_settings

            importlib.reload(test_settings)
            engine = test_settings.DATABASES["default"]["ENGINE"]
            assert engine == "django.db.backends.mysql"
            assert test_settings.DATABASES["default"]["NAME"] == "example_db"
        finally:
            for key, value in env_backup.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

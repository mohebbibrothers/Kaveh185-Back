"""تستِ منطقِ اسکریپتِ معاینه (`scripts/audit_live.py`).

چرا؟ چون این اسکریپت روزِ حادثه اجرا می‌شود و اگر خودش بشکند (مثل نسخهٔ اول
که بی‌قید `PRAGMA` می‌زد و روی MySQL خطا می‌داد)، بدتر از نبودنش است.
اسکریپت به‌صورتِ `manage.py shell < ...` اجرا می‌شود، پس مستقیم import
نمی‌شود؛ این‌جا فقط مسیرهای اجرایی که ممکن است خطا بدهند را می‌سنجیم.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

BACK = Path(__file__).resolve().parents[3]


def test_script_compiles() -> None:
    """فقط همین: باید بدونِ خطای سینتکس کامپایل شود (اجرا در محیطِ زنده است)."""
    source = (BACK / "scripts" / "audit_live.py").read_text(encoding="utf-8")
    compile(source, "audit_live.py", "exec")


def test_script_never_runs_pragma_on_mysql() -> None:
    """PRAGMAها باید داخلِ شاخهٔ SQLite باشند، نه بی‌قید.

    اگر روزی کسی PRAGMA را بیرون از شرط بگذارد، روی MySQL بخشِ دیتابیس
    می‌شکند — همان باگی که یک بار دیدیم.
    """
    source = (BACK / "scripts" / "audit_live.py").read_text(encoding="utf-8")
    assert 'if "mysql" in engine' in source
    pragma_index = source.index("PRAGMA journal_mode")
    mysql_index = source.index('if "mysql" in engine')
    assert mysql_index < pragma_index, "شاخهٔ MySQL باید پیش از PRAGMAها باشد"


@pytest.mark.parametrize("script", ["scripts/audit_live.py", "scripts/load_probe.py"])
def test_scripts_are_valid_python(script: str) -> None:
    """همهٔ اسکریپت‌های عملیاتی باید کامپایل شوند."""
    result = subprocess.run(
        [sys.executable, "-m", "py_compile", str(BACK / script)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_unknown_path_probe_is_printed_once() -> None:
    """خطِ «مسیر ناشناخته» نباید دو بار چاپ شود.

    ⚠️ این از خروجیِ واقعیِ هاست آمد: دو خطِ یکسان «مسیر ناشناخته → 404 404»
    دیده شد، چون هنگامِ جدا کردنِ حالتِ «شبکه در دسترس نیست» یک `print` جا
    مانده بود. یک ابزارِ عیب‌یابی که خروجیِ تکراری می‌دهد، اعتماد را می‌برد.
    """
    source = (BACK / "scripts" / "audit_live.py").read_text(encoding="utf-8")
    assert source.count("مسیر ناشناخته → 404") == 1


def test_backup_script_picks_mariadb_dump_first() -> None:
    """روی MariaDB 11، `mysqldump` منسوخ است؛ اسکریپت باید `mariadb-dump` را اول ببیند."""
    script = (BACK / "deploy" / "backup-db.sh").read_text(encoding="utf-8")
    mariadb_at = script.index("command -v mariadb-dump")
    mysqld_at = script.index("command -v mysqldump")
    assert mariadb_at < mysqld_at, "mariadb-dump باید اول بررسی شود"


def test_backup_script_verifies_its_own_output() -> None:
    """پشتیبانی که باز نمی‌شود، پشتیبان نیست — اسکریپت باید خودش بسنجد."""
    script = (BACK / "deploy" / "backup-db.sh").read_text(encoding="utf-8")
    assert "gzip -t" in script, "سلامتِ فایلِ gzip باید بررسی شود"
    assert "CREATE TABLE" in script, "وجودِ جدول‌ها در فایل باید بررسی شود"
    assert "--single-transaction" in script, "پشتیبان‌گیری نباید جدول‌ها را قفل کند"

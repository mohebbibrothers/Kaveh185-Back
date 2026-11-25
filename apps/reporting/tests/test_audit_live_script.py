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

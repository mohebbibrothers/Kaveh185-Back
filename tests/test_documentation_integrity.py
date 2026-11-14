"""تست یکپارچگی مستندات، فایل‌های قفل (`requirements-lock.txt`) و `STRUCTURE.md`."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent

REQUIRED_DOCS = (
    "README.md",
    "STRUCTURE.md",
    "SECURITY.md",
    "docs/FRONTEND_HANDOFF.md",
    "docs/API_REFERENCE.md",
    "docs/SECURITY_THREAT_MODEL.md",
    "docs/CACHING_STRATEGY.md",
    "docs/CPANEL_DEPLOYMENT.md",
    "docs/DOCKER_DEPLOYMENT.md",
)


def test_required_documentation_files_exist_and_are_rich() -> None:
    """تمام مستندات کلیدی پروژه و راهنمای فرانت‌اند باید موجود و غیرخالی باشند."""
    missing_or_short: list[str] = []
    for rel_path in REQUIRED_DOCS:
        p = ROOT_DIR / rel_path
        if not p.exists() or len(p.read_text(encoding="utf-8").strip()) < 300:
            missing_or_short.append(rel_path)
    assert not missing_or_short, f"Missing or incomplete documentation files: {missing_or_short}"


def test_lockfiles_are_in_sync_with_direct_requirements() -> None:
    """فایل‌های `requirements-lock.txt` و `requirements-dev-lock.txt` باید بدون Drift باشند."""
    res = subprocess.run(  # noqa: S603
        [sys.executable, str(ROOT_DIR / "scripts" / "generate_locks.py"), "--check"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 0, f"Lockfile drift detected: {res.stdout}\n{res.stderr}"


def test_structure_md_is_in_sync_with_repository_tree() -> None:
    """فایل `STRUCTURE.md` باید دقیقاً منطبق با درخت واقعی مخزن باشد."""
    res = subprocess.run(  # noqa: S603
        [sys.executable, str(ROOT_DIR / "scripts" / "generate_structure.py"), "--check"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 0, f"STRUCTURE.md drift detected: {res.stdout}\n{res.stderr}"

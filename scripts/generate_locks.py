#!/usr/bin/env python
"""تولید و بررسی فایل‌های قفل وابستگی برای پروژهٔ کاوه ۱۸۵ (Kaveh185).

چرا لازم است:
    `requirements.txt` وابستگی‌های مستقیم را نگه می‌دارد و transitiveها را پین
    نمی‌کند. برای بازتولیدپذیری کامل در Docker و CI، دو قفل مجزا تولید می‌شود:
    * `requirements-lock.txt`     → فقط runtime (مصرف‌کننده: Dockerfile)
    * `requirements-dev-lock.txt` → runtime + ابزارهای کیفیت/تست (مصرف‌کننده: CI)

استفاده:
    python scripts/generate_locks.py          # بازتولید
    python scripts/generate_locks.py --check  # بررسی عدم drift در CI
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

PROD_HEADER = """# ============================================================
# قفل وابستگی‌های production — Kaveh185
# ============================================================
# این فایل به‌صورت خودکار تولید می‌شود. دستی ویرایشش نکنید:
#     make lock
# ============================================================

"""

DEV_HEADER = """# ============================================================
# قفل وابستگی‌های production + development — Kaveh185
# ============================================================
# تولید خودکار — دستی ویرایش نکنید:
#     make lock
# ============================================================

"""

TARGETS = (
    ("requirements-lock.txt", ("requirements.txt",), PROD_HEADER),
    (
        "requirements-dev-lock.txt",
        ("requirements.txt", "requirements-dev.txt"),
        DEV_HEADER,
    ),
)


def resolve(sources: tuple[str, ...]) -> list[tuple[str, str]]:
    """پین‌های کامل یک مجموعه requirements را با resolver خود pip محاسبه می‌کند."""
    args: list[str] = []
    for source in sources:
        args += ["-r", str(ROOT / source)]

    with tempfile.NamedTemporaryFile(suffix=".json") as report:
        subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--dry-run",
                "--ignore-installed",
                "--quiet",
                "--report",
                report.name,
                *args,
            ],
            check=True,
            cwd=ROOT,
        )
        data = json.loads(Path(report.name).read_text(encoding="utf-8"))

    return sorted(
        (item["metadata"]["name"], item["metadata"]["version"]) for item in data["install"]
    )


def render(sources: tuple[str, ...], header: str) -> str:
    """رندر محتوای نهایی فایل lock."""
    pins = resolve(sources)
    return header + "\n".join(f"{name}=={version}" for name, version in pins) + "\n"


def main() -> int:
    """تولید یا بررسی فایل‌های قفل."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="فقط بررسی همگام بودن قفل‌ها؛ چیزی نوشته نمی‌شود.",
    )
    options = parser.parse_args()

    drifted: list[str] = []
    for filename, sources, header in TARGETS:
        path = ROOT / filename
        rendered = render(sources, header)

        if options.check:
            current = path.read_text(encoding="utf-8") if path.exists() else ""
            if current != rendered:
                drifted.append(filename)
            continue

        path.write_text(rendered, encoding="utf-8")
        print(f"نوشته شد: {filename}")

    if drifted:
        print(
            "قفل وابستگی‌ها هماهنگ نیست: " + "، ".join(drifted) + "\nبرای اصلاح: make lock",
            file=sys.stderr,
        )
        return 1

    if options.check:
        print("قفل وابستگی‌ها هماهنگ است.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

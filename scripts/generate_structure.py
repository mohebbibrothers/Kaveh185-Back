#!/usr/bin/env python
"""بازتولید خودکار STRUCTURE.md از ساختار واقعی مخزن کاوه ۱۸۵ (Kaveh185).

استفاده:
    make structure        # بازتولید STRUCTURE.md
    make structure-check  # تشخیص drift در CI
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
APPS_ROOT = REPO_ROOT / "apps"

SKIP_DIRS = {"__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache", ".git", "node_modules"}

LAYER_NOTES: dict[str, str] = {
    "models.py": "مدل‌های داده و قیود یکپارچگی دیتابیس",
    "selectors.py": "خواندن داده و کوئری‌های بهینه‌شده (بدون side effect)",
    "services.py": "منطق کسب‌وکار، تراکنش‌های اتمی و نوشتن",
    "serializers.py": "قرارداد اعتبارسنجی ورودی و خروجی",
    "views.py": "لایهٔ مرز HTTP و ارکستریشن",
    "filters.py": "فیلترهای پیشرفته و چندبعدی queryset",
    "permissions.py": "کنترل دسترسی نقش‌محور (RBAC) و Step-Up MFA",
    "tasks.py": "تسک‌های پس‌زمینه و Celery",
    "throttles.py": "محدودسازی نرخ و محافظت در برابر سوءاستفاده",
    "choices.py": "مقادیر ثابت و ماشین‌های حالت دامنه",
    "validators.py": "اعتبارسنج‌های قابل استفادهٔ مجدد (کدملی، موبایل، تاریخ جلالی)",
    "excel.py": "موتور تولید گزارش اکسل چندبرگی بازتولیدپذیر",
    "urls.py": "قرارداد مسیرهای API",
}


def _count_nodes(path: Path, base_names: set[str]) -> int:
    """شمارش کلاس‌هایی که از یکی از کلاس‌های پایهٔ مشخص‌شده ارث‌بری می‌کنند."""
    if not path.exists():
        return 0
    try:
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    except SyntaxError:
        return 0
    count = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        for parent in node.bases:
            name = ""
            if isinstance(parent, ast.Attribute):
                name = parent.attr
            elif isinstance(parent, ast.Name):
                name = parent.id
            if name in base_names:
                count += 1
                break
    return count


def _app_rows() -> list[tuple[str, int, int, int, int]]:
    """جمع‌آوری آمار هر اپ: تعداد مدل‌ها، مایگریشن‌ها، ویوها و مسیرها."""
    rows: list[tuple[str, int, int, int, int]] = []
    for app_dir in sorted(APPS_ROOT.iterdir()):
        if not app_dir.is_dir() or app_dir.name in SKIP_DIRS:
            continue
        if not (app_dir / "__init__.py").exists():
            continue

        models = _count_nodes(
            app_dir / "models.py", {"Model", "BaseModel", "AbstractBaseUser", "AbstractUser"}
        )
        migrations_dir = app_dir / "migrations"
        migrations = len(list(migrations_dir.glob("0*.py"))) if migrations_dir.exists() else 0
        views = _count_nodes(
            app_dir / "views.py",
            {"APIView", "GenericAPIView"},
        )
        urls_path = app_dir / "urls.py"
        endpoints = 0
        if urls_path.exists():
            source = urls_path.read_text(encoding="utf-8-sig")
            endpoints = source.count("path(") + source.count("re_path(")
        rows.append((app_dir.name, models, migrations, views, endpoints))
    return rows


def _tree_lines(root: Path, prefix: str = "", depth: int = 0, max_depth: int = 2) -> list[str]:
    """رندر درخت دایرکتوری بدون اندازهٔ فایل‌ها برای جلوگیری از drift کاذب."""
    if depth > max_depth or not root.exists():
        return []
    entries = sorted(
        (p for p in root.iterdir() if p.name not in SKIP_DIRS and not p.name.startswith(".")),
        key=lambda p: (p.is_file(), p.name),
    )
    lines: list[str] = []
    for index, entry in enumerate(entries):
        last = index == len(entries) - 1
        connector = "└── " if last else "├── "
        if entry.is_dir():
            lines.append(f"{prefix}{connector}{entry.name}/")
            lines.extend(
                _tree_lines(entry, prefix + ("    " if last else "│   "), depth + 1, max_depth)
            )
        elif entry.suffix == ".py":
            note = LAYER_NOTES.get(entry.name, "")
            suffix = f"  # {note}" if note else ""
            lines.append(f"{prefix}{connector}{entry.name}{suffix}")
    return lines


def build_document() -> str:
    """ساخت محتوای کامل فایل STRUCTURE.md."""
    rows = _app_rows()
    total_models = sum(r[1] for r in rows)
    total_migrations = sum(r[2] for r in rows)
    total_views = sum(r[3] for r in rows)
    total_endpoints = sum(r[4] for r in rows)

    lines: list[str] = [
        "# ساختار پروژه — کاوه ۱۸۵ (Kaveh185)",
        "",
        "> این فایل **به‌صورت خودکار** تولید شده است. دستی ویرایشش نکنید.",
        "> بازتولید: `make structure` — بررسی عدم انحراف در CI: `make structure-check`",
        "",
        "این سند نقشهٔ معماری واقعی مخزن **Kaveh185-Back** (سامانه مسابقه بزرگ فرهنگی و کتابخوانی",
        "هفته بسیج — حوزه مقاومت بسیج ۱۸۵ شهید کاوه) را نشان می‌دهد و در هر اجرای CI با ساختار",
        "واقعی کد تطبیق داده می‌شود.",
        "",
        "## اپلیکیشن‌ها",
        "",
        f"مجموع: **{len(rows)} اپ** · {total_models} مدل · {total_migrations} مایگریشن · "
        f"{total_views} ویو · {total_endpoints} مسیر",
        "",
        "| اپ | مدل | مایگریشن | ویو | مسیر |",
        "|---|---:|---:|---:|---:|",
    ]
    for name, models, migrations, views, endpoints in rows:
        lines.append(f"| `{name}` | {models} | {migrations} | {views} | {endpoints} |")

    lines += [
        "",
        "## قرارداد لایه‌ها",
        "",
        "هر اپ دامنه‌ای از تفکیک سخت‌گیرانهٔ مسئولیت‌ها پیروی می‌کند:",
        "",
        "| فایل | مسئولیت |",
        "|---|---|",
    ]
    for filename, note in LAYER_NOTES.items():
        lines.append(f"| `{filename}` | {note} |")

    lines += [
        "",
        "قواعدی که با گیت تست معماری (`tests/test_architecture_discipline.py`) به‌صورت خودکار اعمال می‌شوند:",
        "",
        "- تمام ماژول‌های کد تولیدی (`apps/` و `config/`) باید دارای docstring سطح ماژول باشند.",
        "- تمام کلاس‌ها و توابع سطح ماژول در کد تولیدی باید دارای docstring باشند.",
        "- `views.py` حق ندارد مستقیماً روی manager یا queryset مدل عملیات نوشتن انجام دهد؛ تمام تغییرات باید از لایهٔ `services.py` عبور کنند.",
        "- لایه‌های دامنه (`models.py`, `services.py`, `selectors.py`) نباید وابستگی معکوس به لایهٔ HTTP داشته باشند.",
        "- استفاده از `print`، بدنهٔ خالی `pass`، زمان بدون منطقهٔ زمانی و `random` غیرامن در کد تولیدی ممنوع است.",
        "",
        "## درخت دایرکتوری اپ‌ها (`apps/`)",
        "",
        "```text",
        "Kaveh185-Back/apps/",
    ]
    lines.extend(_tree_lines(REPO_ROOT / "apps", max_depth=1))
    lines += [
        "```",
        "",
        "## زیرساخت مشترک (`apps/core`)",
        "",
        "```text",
        "apps/core/",
    ]
    lines.extend(_tree_lines(REPO_ROOT / "apps" / "core", max_depth=1))
    lines += ["```", ""]

    return "\n".join(lines)


def main() -> int:
    """نوشتن یا بررسی همگامی STRUCTURE.md."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="فقط بررسی عدم drift")
    args = parser.parse_args()

    target = REPO_ROOT / "STRUCTURE.md"
    content = build_document()

    if args.check:
        current = target.read_text(encoding="utf-8") if target.exists() else ""
        if current != content:
            sys.stderr.write(
                "STRUCTURE.md با ساختار واقعی مخزن همگام نیست. "
                "«make structure» را اجرا و نتیجه را commit کنید.\n"
            )
            return 1
        return 0

    target.write_text(content, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

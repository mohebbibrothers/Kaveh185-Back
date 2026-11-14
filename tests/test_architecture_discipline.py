"""تست‌های انضباط معماری، تفکیک لایه‌ها و پاکیزگی کد (AST Architecture Guards)."""

from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
APPS_DIR = ROOT_DIR / "apps"
CONFIG_DIR = ROOT_DIR / "config"

FORBIDDEN_MANAGER_MUTATIONS = {
    "create",
    "bulk_create",
    "update",
    "bulk_update",
    "delete",
    "get_or_create",
    "update_or_create",
}
MANAGER_ATTRS = {"objects", "all_objects", "_default_manager", "_base_manager"}
TODO_PATTERN = re.compile(r"#\s*(TODO|FIXME|XXX|HACK)\b", re.IGNORECASE)
VALID_TRACKED_TODO_PATTERN = re.compile(r"#\s*TODO\(#[0-9]+\):\s+\S+")


def _iter_production_py_files() -> list[Path]:
    """پیمایش تمام فایل‌های پایتون تولیدی در `apps/` و `config/` (به‌جز تست‌ها)."""
    files: list[Path] = []
    for base in (APPS_DIR, CONFIG_DIR):
        for path in sorted(base.rglob("*.py")):
            if "tests" in path.parts or "__pycache__" in path.parts:
                continue
            files.append(path)
    return files


def test_views_do_not_perform_direct_orm_mutations() -> None:
    """ویوها باید نازک باشند و هرگز مستقیماً روی Manager مدل‌ها عملیات نوشتن انجام ندهند."""
    violations: list[str] = []
    for view_file in sorted(APPS_DIR.rglob("views.py")):
        tree = ast.parse(view_file.read_text(encoding="utf-8"), filename=str(view_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                method_name = node.func.attr
                if method_name not in FORBIDDEN_MANAGER_MUTATIONS:
                    continue
                target = node.func.value
                if isinstance(target, ast.Attribute) and target.attr in MANAGER_ATTRS:
                    rel = view_file.relative_to(ROOT_DIR)
                    violations.append(f"{rel}:{node.lineno} calls .{target.attr}.{method_name}()")
    assert not violations, f"Direct ORM mutations in views.py are forbidden: {violations}"


def test_domain_models_and_selectors_do_not_import_drf() -> None:
    """ماژول‌های دامنه (`models.py`, `selectors.py`) نباید به `rest_framework` وابسته باشند."""
    violations: list[str] = []
    for filename in ("models.py", "selectors.py"):
        for py_file in sorted(APPS_DIR.rglob(filename)):
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name.startswith("rest_framework"):
                            violations.append(f"{py_file.relative_to(ROOT_DIR)}:{node.lineno}")
                elif isinstance(node, ast.ImportFrom):
                    mod = node.module or ""
                    if mod.startswith("rest_framework"):
                        violations.append(f"{py_file.relative_to(ROOT_DIR)}:{node.lineno}")
    assert not violations, f"Domain layer imported rest_framework: {violations}"


def test_no_print_statements_in_production_code() -> None:
    """هیچ فراخوانی `print()` نباید در کدهای تولیدی `apps/` و `config/` وجود داشته باشد."""
    violations: list[str] = []
    for py_file in _iter_production_py_files():
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "print"
            ):
                violations.append(f"{py_file.relative_to(ROOT_DIR)}:{node.lineno}")
    assert not violations, f"print() found in production modules: {violations}"


def test_all_production_modules_have_module_docstrings() -> None:
    """تمام ماژول‌های پایتون در `apps/` و `config/` باید دارای Docstring ماژول باشند."""
    missing: list[str] = []
    for py_file in _iter_production_py_files():
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        if not ast.get_docstring(tree):
            missing.append(str(py_file.relative_to(ROOT_DIR)))
    assert not missing, f"Modules missing module-level docstring: {missing}"


def test_no_untracked_todo_or_fixme_markers() -> None:
    """هیچ نشانگر `TODO`/`FIXME` بدون شماره Issue (`# TODO(#123): ...`) مجاز نیست."""
    violations: list[str] = []
    for py_file in _iter_production_py_files():
        for idx, line in enumerate(py_file.read_text(encoding="utf-8").splitlines(), start=1):
            if TODO_PATTERN.search(line) and not VALID_TRACKED_TODO_PATTERN.search(line):
                violations.append(f"{py_file.relative_to(ROOT_DIR)}:{idx}")
    assert not violations, f"Untracked TODO/FIXME markers found: {violations}"

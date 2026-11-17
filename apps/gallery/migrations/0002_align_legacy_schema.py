"""هم‌ترازکردنِ جداولِ گالری با هر شِمایی که از قبل روی پایگاه‌داده هست.

── چرا این مهاجرت وجود دارد؟ ─────────────────────────────────────────────
روی هاست، نسخهٔ **قبلیِ** اپ گالری یک بار نصب و مهاجرت شده بود و جدول‌های
`gallery_*` را با ستونِ `order` (به‌جای `display_order`) و چند ستون دیگر
ساخته بود. در چنین پایگاه‌داده‌ای، `0001_initial` **بی‌اثر** است: جنگو
جدول را موجود می‌بیند و ستون‌ها را لمس نمی‌کند. نتیجه، خطای زمان اجرا:

    no such column: gallery_leaderportrait.display_order

── چرا فقط «افزودن ستون» کافی نیست؟ ────────────────────────────────────
ستونِ قدیمی `order` با `NOT NULL` و **بدون پیش‌فرض** ساخته شده و هیچ کدی
آن را پر نمی‌کند، پس هر درجِ تازه شکست می‌خورد:

    NOT NULL constraint failed: gallery_leaderportrait.order

و SQLite (پایگاه‌دادهٔ هاست اشتراکی) `ALTER COLUMN` را پشتیبانی نمی‌کند.
پس تنها راه درست، **بازسازی جدول** است:

  ۱) ردیف‌ها خوانده و در حافظه نگه داشته می‌شوند (گالری چند ده ردیف است).
  ۲) جدول قدیمی حذف می‌شود.
  ۳) جدول تازه با شِمای دقیقِ مدل ساخته می‌شود.
  ۴) ردیف‌ها ستون‌به‌ستون برمی‌گردند و `order` دقیقاً به `display_order`
     می‌ریزد، پس ترتیبِ ادمین حفظ می‌شود.

⚠️ چرا `DROP` و نه `RENAME`؟ نامِ ایندکس‌ها در SQLite سراسری است؛ با
`RENAME`، `create_model` روی نامِ ایندکسِ موجود می‌شکند.

روی پایگاه‌داده‌ای که از اول با `0001_initial` ساخته شده، این مهاجرت
هیچ کاری نمی‌کند: نه ستونِ قدیمی هست، نه ستونِ گم‌شده.
"""

from __future__ import annotations

from typing import Any

from django.db import migrations

# نگاشت ستون‌های شمای قدیمی به ستون‌های تازه.
LEGACY_ALIASES: dict[str, str] = {"display_order": "order"}

MODELS: tuple[str, ...] = ("LeaderPortrait", "Martyr")


def _columns(schema_editor: Any, table: str) -> set[str]:
    """نام ستون‌های یک جدول."""
    with schema_editor.connection.cursor() as cursor:
        description = schema_editor.connection.introspection.get_table_description(cursor, table)
    return {col.name for col in description}


def _read_rows(schema_editor: Any, table: str) -> list[dict[str, Any]]:
    """خواندن همهٔ ردیف‌ها به‌صورت دیکشنری ستون→مقدار.

    `# nosec B608` — نام جدول از `model._meta.db_table` می‌آید (نه از ورودی
    کاربر) و با `quote_name` نقل‌قول می‌شود؛ هیچ مقدارِ کاربری در این SQL
    نیست. Bandit نمی‌تواند این را از روی رشته بفهمد، پس صریح مستثنا شده.
    """
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(f"SELECT * FROM {schema_editor.quote_name(table)}")  # nosec B608
        names = [col[0] for col in cursor.description]
        return [dict(zip(names, row, strict=False)) for row in cursor.fetchall()]


def _rebuild(schema_editor: Any, model: Any) -> None:
    """بازسازی یک جدول با شمای مدل، همراه با انتقال دادهٔ موجود."""
    table = model._meta.db_table
    quote = schema_editor.quote_name

    rows = _read_rows(schema_editor, table)
    schema_editor.execute(f"DROP TABLE {quote(table)}")
    schema_editor.create_model(model)

    expected = [field.column for field in model._meta.local_concrete_fields]
    for row in rows:
        targets: list[str] = []
        values: list[Any] = []
        for column in expected:
            legacy = LEGACY_ALIASES.get(column)
            if column in row:
                targets.append(quote(column))
                values.append(row[column])
            elif legacy and legacy in row:
                targets.append(quote(column))
                values.append(row[legacy])
        if not targets:
            continue
        placeholders = ", ".join(["%s"] * len(values))
        with schema_editor.connection.cursor() as cursor:
            # nosec B608 — نام جدول/ستون‌ها از متادیتای مدل می‌آیند و
            # مقادیر با پارامتر پاس می‌شوند (نه با رشته‌سازی).
            cursor.execute(
                f"INSERT INTO {quote(table)} ({', '.join(targets)}) VALUES ({placeholders})",  # nosec B608
                values,
            )


def align_columns(apps: Any, schema_editor: Any) -> None:
    """هم‌ترازکردنِ جداول گالری — idempotent و بی‌خطر در هر دو حالت."""
    tables = set(schema_editor.connection.introspection.table_names())

    for model_name in MODELS:
        model = apps.get_model("gallery", model_name)
        table = model._meta.db_table
        if table not in tables:
            # جدول نیست ⇒ `0001_initial` ساخته است؛ کاری لازم نیست.
            continue

        existing = _columns(schema_editor, table)
        expected = {field.column for field in model._meta.local_concrete_fields}

        has_legacy_column = any(alias in existing for alias in LEGACY_ALIASES.values())
        missing_column = expected - existing
        if not has_legacy_column and not missing_column:
            # شِما از قبل درست است (پایگاه‌دادهٔ تازه).
            continue

        if has_legacy_column:
            _rebuild(schema_editor, model)
            continue

        # حالت میانی: ستون‌ها ناقص‌اند ولی ستونِ قدیمی هم نیست ⇒ افزودن ساده.
        quote = schema_editor.quote_name
        for field in model._meta.local_concrete_fields:
            if field.column in existing:
                continue
            column_type = field.db_type(schema_editor.connection) or "text"
            default = " DEFAULT 0" if "int" in column_type.lower() else " DEFAULT ''"
            schema_editor.execute(
                f"ALTER TABLE {quote(table)} ADD COLUMN {quote(field.column)} {column_type}{default}"
            )


class Migration(migrations.Migration):
    """مهاجرت هم‌ترازسازی — بی‌اثر روی پایگاه‌دادهٔ تازه."""

    dependencies = [("gallery", "0001_initial")]

    operations = [migrations.RunPython(align_columns, migrations.RunPython.noop)]

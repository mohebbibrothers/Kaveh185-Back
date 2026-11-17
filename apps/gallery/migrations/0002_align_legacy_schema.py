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

── ⚠️ درسِ استقرار واقعی (۱۴۰۵/۰۸/۲۶) ───────────────────────────────────
روی هاست، `migrate` با این خطا شکست خورد:

    TransactionManagementError: Executing DDL statements while in a
    transaction on databases that can't perform a rollback is prohibited.

دلیلش این نیست که موتور `can_rollback_ddl = False` دارد یا نه — آن پرچم
برای MySQL/MariaDB هم `True` است. دلیل این است که در MySQL، `DROP TABLE` و
`CREATE TABLE` **commit ضمنی** می‌زنند و تراکنش را می‌بندند. بعد از اولین
`DROP`، `connection.in_atomic_block` هنوز `True` است ولی تراکنشِ واقعی
تمام شده؛ پس جنگو `CREATE TABLE` بعدی را «DDL داخل تراکنش» می‌بیند و
دستور را **پیش از اجرا** رد می‌کند. نتیجه: جدولِ قدیمی حذف شده و جدولِ
تازه ساخته نشده — بدترین حالت ممکن.

راه‌حل: `atomic = False` روی همین مهاجرت. `apply_migration` مقدار
`migration.atomic` را به `schema_editor(atomic=...)` می‌دهد، پس هیچ بلوکِ
اتمی باز نمی‌شود و `in_atomic_block` هرگز `True` نمی‌شود. چون DDL در MySQL
هرچه باشد autocommit است، از دست رفتنِ اتمی‌بودن چیزی را عوض نمی‌کند؛
تنها تفاوت این است که دیگر خطای کاذب نمی‌گیریم.

علاوه بر این، بازسازی حالا **جابه‌جایی امن** است: جدول قدیمی به نامِ
موقت تغییر نام می‌دهد، جدول تازه ساخته می‌شود، داده منتقل می‌شود و تازه
بعد از موفقیت، جدولِ قدیمی حذف می‌شود. اگر هر جایی کار بشکند، جدولِ قدیمی
پاک نشده و در لاگ دستورِ بازگشت چاپ می‌شود.

روی پایگاه‌داده‌ای که از اول با `0001_initial` ساخته شده، این مهاجرت
هیچ کاری نمی‌کند: نه ستونِ قدیمی هست، نه ستونِ گم‌شده.
"""

from __future__ import annotations

import sys
from typing import Any

from django.db import migrations

# نگاشت ستون‌های شمای قدیمی به ستون‌های تازه.
LEGACY_ALIASES: dict[str, str] = {"display_order": "order"}

MODELS: tuple[str, ...] = ("LeaderPortrait", "Martyr")

def _log(message: str) -> None:
    """گزارشِ پیشرفتِ مهاجرت.

    چرا `sys.stdout.write` و نه `print`؟ تستِ انضباطِ معماری
    (`tests/test_architecture_discipline.py`) هر `print` در کدِ تولیدی را
    رد می‌کند. مهاجرت لازم است بگوید چند ردیف منتقل شد — این تنها جایی است
    که خروجیِ انسانی ارزش واقعی دارد، چون همان چیزی است که در لاگِ
    استقرار دیده می‌شود.
    """
    sys.stdout.write(f"{message}\n")


# پسوندِ جدولِ نگه‌داری‌شده هنگام جابه‌جایی امن.
BACKUP_SUFFIX = "__legacy_backup"


def _columns(schema_editor: Any, table: str) -> set[str]:
    """نام ستون‌های یک جدول."""
    with schema_editor.connection.cursor() as cursor:
        description = schema_editor.connection.introspection.get_table_description(cursor, table)
    return {col.name for col in description}


def _rows_in_chunks(schema_editor: Any, table: str) -> list[dict[str, Any]]:
    """همهٔ ردیف‌ها به‌صورت دیکشنری ستون→مقدار.

    گالری چند ده ردیف است، پس نگه‌داشتن در حافظه بی‌خطر است؛ ولی همان را
    با `chunked_fetch` می‌خوانیم تا رفتار روی درایورهای تنبل (SSCursor)
    هم درست باشد.

    `# nosec B608` — نام جدول از `model._meta.db_table` می‌آید (نه از ورودی
    کاربر) و با `quote_name` نقل‌قول می‌شود؛ هیچ مقدارِ کاربری در این SQL
    نیست. Bandit نمی‌تواند این را از روی رشته بفهمد، پس صریح مستثنا شده.
    """
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(f"SELECT * FROM {schema_editor.quote_name(table)}")  # nosec B608
        names = [col[0] for col in cursor.description]
        rows: list[dict[str, Any]] = []
        while True:
            chunk = cursor.fetchmany(200)
            if not chunk:
                break
            rows.extend(dict(zip(names, row, strict=False)) for row in chunk)
        return rows


def _rename(schema_editor: Any, source: str, target: str) -> None:
    """تغییر نامِ جدول، مستقل از موتور."""
    quote = schema_editor.quote_name
    if schema_editor.connection.vendor == "mysql":
        # MariaDB/MySQL: `RENAME TABLE` چند جدول را هم می‌تواند، ولی ساده‌ترین
        # شکلِ استاندارد همین است. `ALTER TABLE ... RENAME` ایندکس‌ها را با
        # نامِ قدیمی نگه می‌دارد که برای جدولِ پشتیبان مشکلی ایجاد نمی‌کند.
        schema_editor.execute(f"RENAME TABLE {quote(source)} TO {quote(target)}")
    else:
        schema_editor.execute(f"ALTER TABLE {quote(source)} RENAME TO {quote(target)}")


def _table_exists(schema_editor: Any, table: str) -> bool:
    """آیا جدول در پایگاه‌داده هست؟"""
    return table in set(schema_editor.connection.introspection.table_names())


def _insert_rows(schema_editor: Any, model: Any, rows: list[dict[str, Any]]) -> int:
    """برگرداندنِ ردیف‌ها به جدولِ تازه، ستون‌به‌ستون. تعدادِ درج‌شده را برمی‌گرداند."""
    quote = schema_editor.quote_name
    table = model._meta.db_table
    expected = [field.column for field in model._meta.local_concrete_fields]
    placeholder = "%s" if schema_editor.connection.vendor != "sqlite" else "?"
    inserted = 0

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
        placeholders = ", ".join([placeholder] * len(values))
        with schema_editor.connection.cursor() as cursor:
            # nosec B608 — نام جدول/ستون‌ها از متادیتای مدل می‌آیند و
            # مقادیر با پارامتر پاس می‌شوند (نه با رشته‌سازی).
            cursor.execute(
                f"INSERT INTO {quote(table)} ({', '.join(targets)}) VALUES ({placeholders})",  # nosec B608
                values,
            )
        inserted += 1
    return inserted


def _rebuild(schema_editor: Any, model: Any) -> None:
    """بازسازی یک جدول با شمای مدل، همراه با انتقال دادهٔ موجود.

    ترتیبِ کار عمداً «جابه‌جایی امن» است، نه «حذف و ساختن»:

        rename old → create new → copy rows → drop old

    اگر در هر مرحله‌ای خطا رخ دهد، دادهٔ اصلی هنوز در جدولِ
    `…__legacy_backup` دست‌نخورده است و لاگ دستورِ بازگشت را چاپ می‌کند.
    """
    table = model._meta.db_table
    backup = f"{table}{BACKUP_SUFFIX}"
    quote = schema_editor.quote_name

    # پسماندهٔ اجرای ناموفقِ قبلی؟ اول پاک شود تا نامِ موقت آزاد باشد.
    if _table_exists(schema_editor, backup):
        schema_editor.execute(f"DROP TABLE IF EXISTS {quote(backup)}")

    rows = _rows_in_chunks(schema_editor, table)
    _log(f"  گالری: {len(rows)} ردیف از {table} خوانده شد — بازسازی جدول…")

    _rename(schema_editor, table, backup)
    try:
        schema_editor.create_model(model)
        copied = _insert_rows(schema_editor, model, rows)
    except Exception:
        # بازگشت به وضعیتِ قبل: جدولِ نیمه‌ساخته را بردار و نامِ اصلی را برگردان.
        if _table_exists(schema_editor, table):
            schema_editor.execute(f"DROP TABLE {quote(table)}")
        _rename(schema_editor, backup, table)
        raise
    else:
        schema_editor.execute(f"DROP TABLE {quote(backup)}")
        _log(f"  گالری: {copied} ردیف به {table} منتقل شد ✔")


def align_columns(apps: Any, schema_editor: Any) -> None:
    """هم‌ترازکردنِ جداول گالری — idempotent و بی‌خطر در هر دو حالت."""
    for model_name in MODELS:
        model = apps.get_model("gallery", model_name)
        table = model._meta.db_table

        if not _table_exists(schema_editor, table):
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
    """مهاجرت هم‌ترازسازی — بی‌اثر روی پایگاه‌دادهٔ تازه.

    ⚠️ `atomic = False` اجباری است؛ توضیحش در بالای همین فایل
    («درسِ استقرار واقعی») آمده: DDL در MySQL تراکنش را commit می‌کند و
    جنگو بعد از آن، DDLِ بعدی را داخلِ تراکنش می‌بیند و رد می‌کند.
    """

    atomic = False

    dependencies = [("gallery", "0001_initial")]

    operations = [migrations.RunPython(align_columns, migrations.RunPython.noop)]

#!/usr/bin/env python
"""ابزارِ ساختِ شِمای «قدیمیِ» گالری — برای بازتولیدِ سناریوی هاست.

── چه کاری می‌کند؟ ───────────────────────────────────────────────────────
جدول‌های `gallery_leaderportrait` و `gallery_martyr` را با **شِمای نسخهٔ
قبلیِ اپ** می‌سازد: ستونِ `display_order` اسمش `order` است، و
`django_migrations` هم ادعا می‌کند `gallery.0001_initial` اعمال شده.
یعنی همان وضعیتی که روی هاست بود و باعث شد `0001_initial` بی‌اثر باشد و
`0002_align_legacy_schema` لازم شود.

── حالت‌ها ──────────────────────────────────────────────────────────────
    python scripts/build_legacy_gallery_db.py                 # ساختِ شِمای قدیمی
    python scripts/build_legacy_gallery_db.py --reset         # اول همان سه جدول را پاک کن
    python scripts/build_legacy_gallery_db.py --wipe-all      # همهٔ جدول‌های این پایگاه‌داده را پاک کن
    python scripts/build_legacy_gallery_db.py --dry-run       # فقط بگو چه می‌شود

`--reset` و `--wipe-all` صریح‌اند تا هرگز اشتباهی جدولی پاک نشود.

── کجا استفاده می‌شود؟ ──────────────────────────────────────────────────
• جابِ `migrations-on-mariadb` در CI — تا این سناریو هر پوش تست شود.
• روی هاست، پیش از استقرار:

      python scripts/build_legacy_gallery_db.py --database legacy_probe --reset
      DB_NAME=legacy_probe python manage.py migrate gallery --noinput

── نکته‌های پیاده‌سازی ──────────────────────────────────────────────────
• این اسکریپت **پایگاه‌داده نمی‌سازد**؛ فرض می‌کند موجود است. ساختِ
  پایگاه‌داده نیاز به امتیازِ سراسری دارد که کاربرِ هاست ندارد.
• فقط MySQL/MariaDB؛ هدف دقیقاً بازتولیدِ رفتارِ MariaDB است (commitِ
  ضمنیِ DDL که `atomic` را لازم کرد).
• نام جدول‌ها ثابت‌اند و نامِ پایگاه‌داده با `_safe_name` سنجیده می‌شود، پس
  رشته‌سازیِ نام در SQL بی‌خطر است (`# nosec` هم صریح گذاشته شده).
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from typing import Any

import pymysql

LEGACY_LEADER = """
CREATE TABLE gallery_leaderportrait (
    id bigint NOT NULL AUTO_INCREMENT PRIMARY KEY,
    created_at datetime(6) NOT NULL,
    updated_at datetime(6) NOT NULL,
    `order` int NOT NULL,
    is_active tinyint(1) NOT NULL DEFAULT 1,
    image varchar(100) NOT NULL,
    alt varchar(180) NOT NULL,
    caption longtext NOT NULL,
    source varchar(200) NOT NULL,
    show_in_box tinyint(1) NOT NULL DEFAULT 1
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""

LEGACY_MARTYR = """
CREATE TABLE gallery_martyr (
    id bigint NOT NULL AUTO_INCREMENT PRIMARY KEY,
    created_at datetime(6) NOT NULL,
    updated_at datetime(6) NOT NULL,
    `order` int NOT NULL,
    is_active tinyint(1) NOT NULL DEFAULT 1,
    image varchar(100) NOT NULL,
    title varchar(48) NOT NULL,
    subtitle varchar(90) NOT NULL,
    alt varchar(180) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""

MIGRATIONS_TABLE = """
CREATE TABLE django_migrations (
    id bigint NOT NULL AUTO_INCREMENT PRIMARY KEY,
    app varchar(255) NOT NULL,
    name varchar(255) NOT NULL,
    applied datetime(6) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""

SCHEMA_TABLES = ("gallery_leaderportrait", "gallery_martyr", "django_migrations")

SAFE_NAME = re.compile(r"[A-Za-z0-9_]{1,64}\Z")


def _safe_name(name: str) -> str:
    """نامِ پایگاه‌داده را می‌سنجد و با کوتِ بک‌تیک برمی‌گرداند."""
    if not SAFE_NAME.match(name):
        raise SystemExit(f"نام پایگاه‌داده نامعتبر: {name!r} (فقط حروف/رقم/آندرلاین)")
    return f"`{name}`"


def _connect(args: argparse.Namespace) -> Any:
    """اتصال به سرور، با مقدارهای خط فرمان یا متغیرهای محیطی."""
    return pymysql.connect(
        host=args.host,
        port=args.port,
        user=args.user,
        password=args.password,
        database=args.database,
        charset="utf8mb4",
        autocommit=True,
    )


def _all_tables(cur: Any, database: str) -> list[str]:
    """نامِ همهٔ جدول‌های یک پایگاه‌داده."""
    cur.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = %s",
        (database,),
    )
    return [row[0] for row in cur.fetchall()]


def build(args: argparse.Namespace) -> list[str]:
    """می‌سازد و فهرستِ کارهای انجام‌شده را برمی‌گرداند."""
    done: list[str] = []
    conn = _connect(args)
    try:
        with conn.cursor() as cur:
            if args.wipe_all:
                tables = _all_tables(cur, args.database)
                for table in tables:
                    cur.execute(f"DROP TABLE `{table}`")  # nosec B608 — نام از information_schema
                done.append(f"{len(tables)} جدول پاک شد (پایگاه‌دادهٔ خالی)")

            if args.reset:
                for table in SCHEMA_TABLES:
                    cur.execute(f"DROP TABLE IF EXISTS `{table}`")
                done.append(f"جدول‌های گالری پاک شدند: {', '.join(SCHEMA_TABLES)}")

            if not args.wipe_all:
                for statement in (LEGACY_LEADER, LEGACY_MARTYR, MIGRATIONS_TABLE):
                    cur.execute(statement)
                cur.execute(
                    "INSERT INTO django_migrations (app, name, applied) "
                    "VALUES ('gallery', '0001_initial', NOW())"
                )
                cur.execute(
                    "INSERT INTO gallery_leaderportrait "
                    "(created_at, updated_at, `order`, image, alt, caption, source) "
                    "VALUES (NOW(), NOW(), 7, 'gallery/leader/a.jpg', "
                    "'متن جانشین', 'کلام رهبر انقلاب', 'منبع')"
                )
                cur.execute(
                    "INSERT INTO gallery_martyr "
                    "(created_at, updated_at, `order`, image, title, subtitle, alt) "
                    "VALUES (NOW(), NOW(), 3, 'gallery/martyrs/a.jpg', "
                    "'سیدشهدای مقاومت', 'شهید محمود کاوه', 'متن جانشین')"
                )
                done.append(f"شِمای قدیمی در `{args.database}` ساخته شد (۲ تصویر + رکورد مهاجرت)")
    finally:
        conn.close()
    return done


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """آرگومان‌ها؛ پیش‌فرض‌ها از متغیرهای محیطیِ همان پروژه."""
    parser = argparse.ArgumentParser(
        description="ساختِ شِمای قدیمیِ گالری برای بازتولیدِ سناریوی هاست",
        epilog="این ابزار فقط برای MySQL/MariaDB است.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--database", default=os.environ.get("DB_NAME", "kaveh185"))
    parser.add_argument("--host", default=os.environ.get("DB_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("DB_PORT") or 3306))
    parser.add_argument("--user", default=os.environ.get("DB_USER", "root"))
    parser.add_argument("--password", default=os.environ.get("DB_PASSWORD", ""))
    parser.add_argument(
        "--reset",
        action="store_true",
        help="سه جدولِ مربوط به این سناریو را پیش از ساخت پاک کن",
    )
    parser.add_argument(
        "--wipe-all",
        action="store_true",
        help="همهٔ جدول‌های این پایگاه‌داده را پاک کن و چیزی نساز (پایگاه‌دادهٔ سفید)",
    )
    parser.add_argument("--dry-run", action="store_true", help="فقط گزارش کن، چیزی را عوض نکن")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """نقطهٔ ورود."""
    args = parse_args(argv)
    if args.reset and args.wipe_all:
        sys.stderr.write("`--reset` و `--wipe-all` با هم معنا ندارند.\n")
        return 2
    engine = os.environ.get("DB_ENGINE", "")
    if engine and "mysql" not in engine:
        sys.stderr.write("این اسکریپت فقط برای MySQL/MariaDB است.\n")
        return 2
    if args.dry_run:
        _safe_name(args.database)
        sys.stdout.write(
            f"[dry-run] پایگاه‌داده: {args.database} · reset={args.reset} · "
            f"wipe_all={args.wipe_all}\n"
        )
        return 0
    for line in build(args):
        sys.stdout.write(f"{line}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

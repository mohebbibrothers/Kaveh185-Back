#!/usr/bin/env python
"""ساختِ یک پایگاه‌دادهٔ «قدیمیِ» گالری، برای بازتولیدِ سناریوی هاست.

── چه کاری می‌کند؟ ───────────────────────────────────────────────────────
جدول‌های `gallery_leaderportrait` و `gallery_martyr` را با **شِمای نسخهٔ
قبلیِ اپ** می‌سازد: ستونِ `display_order` اسمش `order` است، و
`django_migrations` هم ادعا می‌کند `gallery.0001_initial` اعمال شده.
یعنی همان وضعیتی که روی هاست بود و باعث شد `0001_initial` بی‌اثر باشد و
`0002_align_legacy_schema` لازم شود.

── کجا استفاده می‌شود؟ ──────────────────────────────────────────────────
• جابِ `migrations-on-mariadb` در CI — تا این سناریو هر پوش تست شود.
• روی هاست، اگر خواستی پیش از استقرار بازتولیدش کنی:

      python scripts/build_legacy_gallery_db.py --database legacy_probe --drop
      DB_NAME=legacy_probe python manage.py migrate gallery --noinput

── نکتهٔ امنیتی ─────────────────────────────────────────────────────────
فقط MySQL/MariaDB. روی SQLite اجرا نمی‌شود، چون هدف دقیقاً بازتولیدِ
رفتارِ MariaDB است (commitِ ضمنیِ DDL). `--drop` صریح است تا هرگز
اشتباهی یک پایگاه‌دادهٔ واقعی پاک نشود.

نامِ پایگاه‌داده در `USE` با کوتِ بک‌تیک و فقط از کاراکترهای
`[A-Za-z0-9_]` ساخته می‌شود (`_safe_name`)، پس رشته‌سازیِ نام در SQL
بی‌خطر است.
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
        charset="utf8mb4",
        autocommit=True,
    )


def build(args: argparse.Namespace) -> list[str]:
    """می‌سازد و فهرستِ کارهای انجام‌شده را برمی‌گرداند."""
    name = _safe_name(args.database)
    done: list[str] = []
    conn = _connect(args)
    try:
        with conn.cursor() as cur:
            if args.drop:
                cur.execute(f"DROP DATABASE IF EXISTS {name}")
                done.append(f"پایگاه‌دادهٔ قبلی حذف شد: {args.database}")
            cur.execute(f"CREATE DATABASE IF NOT EXISTS {name} CHARACTER SET utf8mb4")
            cur.execute(f"USE {name}")
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
    finally:
        conn.close()
    done.append(f"شِمای قدیمی در `{args.database}` ساخته شد (۵ جدول/ردیف)")
    return done


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """آرگومان‌ها؛ پیش‌فرض‌ها از متغیرهای محیطیِ همان پروژه."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--database", default=os.environ.get("DB_NAME", "legacy_probe"))
    parser.add_argument("--host", default=os.environ.get("DB_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("DB_PORT") or 3306))
    parser.add_argument("--user", default=os.environ.get("DB_USER", "root"))
    parser.add_argument("--password", default=os.environ.get("DB_PASSWORD", ""))
    parser.add_argument(
        "--drop",
        action="store_true",
        help="پایگاه‌دادهٔ همنام را اول پاک کن (برای اجرای تازه در CI)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """نقطهٔ ورود."""
    args = parse_args(argv)
    engine = os.environ.get("DB_ENGINE", "")
    if engine and "mysql" not in engine:
        sys.stderr.write("این اسکریپت فقط برای MySQL/MariaDB است.\n")
        return 2
    for line in build(args):
        sys.stdout.write(f"{line}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

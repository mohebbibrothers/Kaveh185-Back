"""تستِ مهاجرت هم‌ترازسازیِ گالری (`0002_align_legacy_schema`).

── چرا این تست اتصالِ جدا می‌سازد؟ ───────────────────────────────────────
این مهاجرت جدول را **بازسازی** می‌کند (rename → create → copy → drop). تستش
باید روی یک پایگاه‌دادهٔ واقعی و جدا از پایگاه‌دادهٔ تستِ pytest اجرا شود،
وگرنه یا جدول‌های خودِ pytest دست‌کاری می‌شوند یا در تراکنشِ تست گیر
می‌کنیم. پس یک `DatabaseWrapper` مستقل روی فایلِ `tmp_path` ساخته و
**موقتاً** جای `default` گذاشته می‌شود؛ در پایان، اتصالِ اصلی برگردانده
می‌شود.

── درسی که این تست از آن زاده شد ────────────────────────────────────────
روی هاست، همین مهاجرت با

    TransactionManagementError: Executing DDL statements while in a
    transaction …

شکست خورد؛ چون در MySQL هر `DROP TABLE` تراکنش را commit می‌کند و جنگو
`CREATE TABLE` بعدی را «DDL داخلِ تراکنش» می‌بیند. `atomic = False` همان
چیزی است که این تست پاییدنش می‌کند.
"""

from __future__ import annotations

import contextlib
import importlib
import sqlite3
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from django.db import connections
from django.db.backends.sqlite3.base import DatabaseWrapper

MODULE: ModuleType = importlib.import_module("apps.gallery.migrations.0002_align_legacy_schema")

ALIAS = "default"


def _config(path: Path) -> dict[str, Any]:
    """پیکربندیِ کاملِ یک اتصالِ SQLite مستقل."""
    return {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": str(path),
        "ATOMIC_REQUESTS": False,
        "AUTOCOMMIT": True,
        "CONN_MAX_AGE": 0,
        "CONN_HEALTH_CHECKS": False,
        "OPTIONS": {},
        "TIME_ZONE": None,
        "USER": "",
        "PASSWORD": "",
        "HOST": "",
        "PORT": "",
        "TEST": {"NAME": None, "CHARSET": None, "COLLATION": None, "MIRROR": None},
    }


class Probe:
    """اتصالِ آزمایشی + جای‌گذاریِ موقت آن به‌جای اتصالِ `default`."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.wrapper = DatabaseWrapper(_config(path), alias=ALIAS)
        self.storage = connections._connections._get_storage()
        self.previous = vars(self.storage).get(ALIAS)

    def __enter__(self) -> Probe:
        vars(self.storage)[ALIAS] = self.wrapper
        return self

    def __exit__(self, *_: Any) -> None:
        self.wrapper.close()
        if self.previous is None:
            vars(self.storage).pop(ALIAS, None)
        else:
            vars(self.storage)[ALIAS] = self.previous


@contextlib.contextmanager
def _connect(path: Path) -> Any:
    """اتصال به همان فایل و **بستنِ قطعی** آن.

    ⚠️ `with sqlite3.connect(...)` اتصال را نمی‌بندد، فقط commit می‌کند؛
    نتیجه: ده‌ها اتصالِ باز که هنگام garbage-collect هشدارِ
    `PytestUnraisableExceptionWarning` می‌دهند و تستِ بعدی را می‌اندازند.
    """
    raw = sqlite3.connect(path)
    try:
        yield raw
        raw.commit()
    finally:
        raw.close()


def _legacy_schema(path: Path) -> None:
    """ساختِ همان شِمایی که نسخهٔ قبلیِ اپ روی هاست ساخته بود (ستون `order`)."""
    with _connect(path) as raw:
        raw.executescript(
            """
            CREATE TABLE gallery_leaderportrait (
                id integer PRIMARY KEY AUTOINCREMENT,
                created_at datetime NOT NULL,
                updated_at datetime NOT NULL,
                "order" integer NOT NULL,
                is_active bool NOT NULL DEFAULT 1,
                image varchar(100) NOT NULL,
                alt varchar(180) NOT NULL,
                caption text NOT NULL,
                source varchar(200) NOT NULL,
                show_in_box bool NOT NULL DEFAULT 1
            );
            CREATE TABLE gallery_martyr (
                id integer PRIMARY KEY AUTOINCREMENT,
                created_at datetime NOT NULL,
                updated_at datetime NOT NULL,
                "order" integer NOT NULL,
                is_active bool NOT NULL DEFAULT 1,
                image varchar(100) NOT NULL,
                title varchar(48) NOT NULL,
                subtitle varchar(90) NOT NULL,
                alt varchar(180) NOT NULL
            );
            INSERT INTO gallery_leaderportrait
                (created_at, updated_at, "order", image, alt, caption, source)
            VALUES ('2026-01-01 00:00:00', '2026-01-01 00:00:00', 7,
                    'gallery/leader/a.jpg', 'متن جانشین', 'کلام رهبر انقلاب', 'منبع');
            INSERT INTO gallery_martyr
                (created_at, updated_at, "order", image, title, subtitle, alt)
            VALUES ('2026-01-01 00:00:00', '2026-01-01 00:00:00', 3,
                    'gallery/martyrs/a.jpg', 'سیدشهدای مقاومت',
                    'شهید محمود کاوه', 'متن جانشین');
            """
        )


def _columns(path: Path, table: str) -> set[str]:
    """نام ستون‌های یک جدول در همان فایلِ SQLite."""
    with _connect(path) as raw:
        return {row[1] for row in raw.execute(f'PRAGMA table_info("{table}")')}


def _rows(path: Path, table: str) -> list[tuple[Any, ...]]:
    """همهٔ ردیف‌های یک جدول."""
    with _connect(path) as raw:
        return list(raw.execute(f'SELECT * FROM "{table}"'))  # noqa: S608 — جدول در تست ثابت است


def _tables(path: Path) -> set[str]:
    """نام همهٔ جدول‌های همان فایل."""
    with _connect(path) as raw:
        return {row[0] for row in raw.execute("SELECT name FROM sqlite_master WHERE type='table'")}


@pytest.fixture(autouse=True)
def _allow_db(django_db_blocker: Any) -> Any:
    """دسترسی به پایگاه‌داده را باز می‌کند؛ ولی هیچ تستی `django_db` نمی‌خواهد.

    لازم است چون pytest-django متدِ اتصال را برای تست‌های بدونِ `django_db`
    می‌بندد و اتصالِ آزمایشیِ ما هم از همان کلاس است.
    """
    django_db_blocker.unblock()
    yield


@pytest.fixture
def probe(tmp_path: Path) -> Any:
    """اتصالِ مستقل + شِمای قدیمی."""
    path = tmp_path / "probe.sqlite3"
    _legacy_schema(path)
    with Probe(path) as installed:
        yield installed


def _apps() -> Any:
    """رجیستریِ مدل‌های واقعی برنامه."""
    from django.apps import apps as global_apps

    return global_apps


def test_migration_is_non_atomic_so_mysql_ddl_is_allowed() -> None:
    """⚠️ هستهٔ رفعِ باگ هاست: `atomic` باید صریحاً `False` باشد.

    اگر روزی کسی این خط را بردارد، روی MySQL/MariaDB همان
    `TransactionManagementError` برمی‌گردد و جدولِ گالری نیمه‌کاره می‌ماند.
    """
    assert MODULE.Migration.atomic is False


def test_migration_dependency_is_the_initial_one() -> None:
    """مهاجرت باید بعد از `0001_initial` بیاید."""
    assert MODULE.Migration.dependencies == [("gallery", "0001_initial")]


def test_align_columns_rebuilds_legacy_tables_and_keeps_every_row(probe: Probe) -> None:
    """شمای قدیمی ⇒ جدول تازه با ستون درست، و همان ردیف‌ها با همان ترتیب."""
    with probe.wrapper.schema_editor(atomic=False) as editor:
        MODULE.align_columns(_apps(), editor)

    columns = _columns(probe.path, "gallery_martyr")
    assert "display_order" in columns
    assert "order" not in columns

    martyr = _rows(probe.path, "gallery_martyr")
    assert len(martyr) == 1
    assert martyr[0][3] == 3  # display_order از `order` قدیمی آمده
    assert {"سیدشهدای مقاومت", "شهید محمود کاوه"} <= {str(cell) for cell in martyr[0]}

    portrait = _rows(probe.path, "gallery_leaderportrait")
    assert len(portrait) == 1
    assert "کلام رهبر انقلاب" in [str(cell) for cell in portrait[0]]
    assert portrait[0][3] == 7

    # جدولِ نگه‌داریِ موقت نباید باقی بماند.
    assert not any(name.endswith(MODULE.BACKUP_SUFFIX) for name in _tables(probe.path))


def test_align_columns_is_idempotent_on_an_already_correct_schema(probe: Probe) -> None:
    """اجرای دوباره نباید چیزی را بشکند و نه ردیفی را تکرار کند."""
    for _ in range(2):
        with probe.wrapper.schema_editor(atomic=False) as editor:
            MODULE.align_columns(_apps(), editor)

    assert len(_rows(probe.path, "gallery_martyr")) == 1
    assert len(_rows(probe.path, "gallery_leaderportrait")) == 1


def test_align_columns_adds_only_the_missing_columns_in_the_middle_state(tmp_path: Path) -> None:
    """حالت میانی: ستونِ قدیمی نیست ولی ستون‌ها ناقص‌اند ⇒ افزودنِ ساده."""
    path = tmp_path / "middle.sqlite3"
    with _connect(path) as raw:
        raw.execute(
            """
            CREATE TABLE gallery_martyr (
                id integer PRIMARY KEY AUTOINCREMENT,
                created_at datetime NOT NULL,
                updated_at datetime NOT NULL,
                is_active bool NOT NULL DEFAULT 1,
                image varchar(100) NOT NULL,
                title varchar(48) NOT NULL,
                subtitle varchar(90) NOT NULL,
                alt varchar(180) NOT NULL
            )
            """
        )
        raw.execute(
            "INSERT INTO gallery_martyr "
            "(created_at, updated_at, image, title, subtitle, alt) "
            "VALUES ('2026-01-01', '2026-01-01', 'x.jpg', 'بی‌ستون', '', '')"
        )

    with Probe(path) as installed, installed.wrapper.schema_editor(atomic=False) as editor:
        MODULE.align_columns(_apps(), editor)

    assert "display_order" in _columns(path, "gallery_martyr")
    assert len(_rows(path, "gallery_martyr")) == 1


def test_rebuild_restores_the_original_table_when_copying_fails(
    probe: Probe, monkeypatch: pytest.MonkeyPatch
) -> None:
    """اگر انتقالِ داده بشکند، نامِ اصلی برمی‌گردد و ردیف‌ها از دست نمی‌روند.

    این همان نکته‌ای است که «جابه‌جایی امن» را از «حذف و ساختن» جدا می‌کند:
    هیچ لحظه‌ای وجود ندارد که داده فقط در حافظه باشد.
    """

    def _boom(*args: Any, **kwargs: Any) -> int:
        raise RuntimeError("شکستِ عمدی در انتقال")

    monkeypatch.setattr(MODULE, "_insert_rows", _boom)
    with (
        pytest.raises(RuntimeError, match="شکستِ عمدی"),
        probe.wrapper.schema_editor(atomic=False) as editor,
    ):
        MODULE._rebuild(editor, _apps().get_model("gallery", "Martyr"))

    # نامِ اصلی سر جایش، ردیف‌ها سالم، جدولِ موقت پاک‌شده.
    assert "order" in _columns(probe.path, "gallery_martyr")
    assert len(_rows(probe.path, "gallery_martyr")) == 1
    assert not any(name.endswith(MODULE.BACKUP_SUFFIX) for name in _tables(probe.path))


def test_rebuild_drops_a_leftover_backup_table(probe: Probe) -> None:
    """پسماندهٔ اجرای ناموفقِ قبلی (جدول `…__legacy_backup`) خودش پاک می‌شود."""
    backup = f"gallery_martyr{MODULE.BACKUP_SUFFIX}"
    with _connect(probe.path) as raw:
        raw.execute(f'CREATE TABLE "{backup}" (id integer)')

    with probe.wrapper.schema_editor(atomic=False) as editor:
        MODULE.align_columns(_apps(), editor)

    assert backup not in _tables(probe.path)
    assert "display_order" in _columns(probe.path, "gallery_martyr")


def test_align_columns_skips_tables_that_do_not_exist(tmp_path: Path) -> None:
    """پایگاه‌دادهٔ خالی: نه استثنا، نه خطا."""
    path = tmp_path / "empty.sqlite3"
    with _connect(path):
        pass

    with Probe(path) as installed, installed.wrapper.schema_editor(atomic=False) as editor:
        MODULE.align_columns(_apps(), editor)

    assert _tables(path) == {"sqlite_sequence"} or _tables(path) == set()

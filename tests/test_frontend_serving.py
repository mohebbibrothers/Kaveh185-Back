"""تست‌های سرو کردن فرانت ایستای Next از درون جنگو (`apps/core/frontend.py`).

چرا این تست‌ها وجود دارند
──────────────────────────
این ماژول تنها راهی است که کاربر سایت را می‌بیند؛ اگر خراب باشد، همه‌چیز
خراب است ولی بک‌اند سالم به نظر می‌رسد. دو باگ واقعی که در تمرین اول
رخ داد و همین‌جا قفل می‌شوند:

۱) **همهٔ صفحات ۴۰۴ می‌شدند** چون `_safe_join` مسیر نهایی را resolve
   می‌کرد و با `root`ِ حل‌نشده (که خودش پیوند نمادین است) مقایسه می‌کرد.
۲) **همهٔ تصاویر و چانک‌ها ۴۰۴ می‌شدند** چون اسلش ابتدای URL به
   `_safe_join` داده می‌شد و همان‌جا رد می‌شد.

به‌علاوه: CSP. بدون سیاست درست برای سندهای فرانت، سیاست پیش‌فرض بک‌اند
(`default-src 'none'`) سایت را کاملاً سفید می‌کند — بی‌هیچ خطای سرور.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from django.test import Client, override_settings

pytestmark = pytest.mark.django_db


def _make_front(tmp_path: Path, *, with_assets: bool = True) -> Path:
    """ساخت یک خروجی فرانت مینیمال اما واقعی‌شکل."""
    root = tmp_path / "frontend"
    root.mkdir()

    (root / "index.html").write_text(
        "<!doctype html><html><head>"
        '<link rel="stylesheet" href="/_next/static/chunks/a.css">'
        "</head><body>"
        "<script>(self.__next_f=self.__next_f||[]).push([0])</script>"
        "<script src='/_next/static/chunks/a.js'></script>"
        "<h1>کاوه ۱۸۵</h1></body></html>",
        "utf-8",
    )
    (root / "404.html").write_text("<html><body>۴۰۴</body></html>", "utf-8")
    (root / "robots.txt").write_text("User-agent: *\n", "utf-8")
    (root / "BUILD_INFO.json").write_text(
        '{"version": "9.9.9", "sha256_index": "abcdef1234567890", "built_at": "2026-01-01"}',
        "utf-8",
    )

    if with_assets:
        for page in ("register", "rules"):
            d = root / page
            d.mkdir()
            (d / "index.html").write_text(f"<html><body>{page}</body></html>", "utf-8")
            # بارِ RSC که روتر Next برای ناوبری داخلی می‌خواهد
            (d / "index.txt").write_text('1:"$Sreact.fragment"\n', "utf-8")

        chunks = root / "_next" / "static" / "chunks"
        chunks.mkdir(parents=True)
        (chunks / "a.js").write_text("console.log(1)", "utf-8")
        (chunks / "a.css").write_text("body{}", "utf-8")

        img = root / "img"
        img.mkdir()
        (img / "kaveh-hero.jpg").write_bytes(b"\xff\xd8\xff\xe0fake-jpeg")

    return root


@pytest.fixture()
def front_root(tmp_path: Path) -> Path:
    """خروجی فرانت ساختگی، به‌عنوان FRONTEND_DIST."""
    return _make_front(tmp_path)


def _client() -> Client:
    """کلاینت تست با میزبان مجاز."""
    return Client(HTTP_HOST="127.0.0.1")


# ── صفحات ─────────────────────────────────────────────────────────────────


def test_root_serves_prerendered_index(front_root: Path) -> None:
    """`/` سند پیش‌رندرشده را می‌دهد، نه JSON."""
    with override_settings(FRONTEND_DIST=str(front_root)):
        resp = _client().get("/")
    assert resp.status_code == 200
    assert resp["Content-Type"].startswith("text/html")
    assert "کاوه ۱۸۵" in resp.content.decode("utf-8")


def test_prerendered_page_by_directory(front_root: Path) -> None:
    """هر صفحهٔ پیش‌رندرشده با مسیر پوشه‌ای‌اش سرو می‌شود."""
    with override_settings(FRONTEND_DIST=str(front_root)):
        client = _client()
        for slug in ("register", "rules"):
            resp = client.get(f"/{slug}/")
            assert resp.status_code == 200, slug
            assert slug in resp.content.decode("utf-8")


def test_unknown_path_is_real_404(front_root: Path) -> None:
    """مسیر ناشناخته باید ۴۰۴ بدهد، نه ۲۰۰ با بدنهٔ صفحهٔ خطا."""
    with override_settings(FRONTEND_DIST=str(front_root)):
        resp = _client().get("/not-a-page/")
    assert resp.status_code == 404
    assert "۴۰۴" in resp.content.decode("utf-8")


def test_trailing_slash_redirect_is_308(front_root: Path) -> None:
    """مسیر بی‌اسلش با ۳۰۸ (نه ۳۰۱) به نسخهٔ با اسلش می‌رود."""
    with override_settings(FRONTEND_DIST=str(front_root)):
        resp = _client().get("/register")
    assert resp.status_code == 308
    assert resp["Location"] == "/register/"


def test_trailing_slash_redirect_keeps_query(front_root: Path) -> None:
    """پرس‌وجو در هدایت گم نمی‌شود."""
    with override_settings(FRONTEND_DIST=str(front_root)):
        resp = _client().get("/register?ref=mosque")
    assert resp.status_code == 308
    assert resp["Location"] == "/register/?ref=mosque"


def test_asset_without_slash_is_not_redirected(front_root: Path) -> None:
    """فایل‌ها (تصویر/CSS) نباید به نسخهٔ اسلش‌دار هدایت شوند."""
    with override_settings(FRONTEND_DIST=str(front_root)):
        resp = _client().get("/img/kaveh-hero.jpg")
    assert resp.status_code == 200
    assert resp["Content-Type"].startswith("image/jpeg")


# ── دارایی‌ها و کش ────────────────────────────────────────────────────────


def test_static_chunk_is_immutable(front_root: Path) -> None:
    """دارایی‌های `_next/static` هش در نام دارند ⇒ کش یک‌سالهٔ immutable."""
    with override_settings(FRONTEND_DIST=str(front_root)):
        resp = _client().get("/_next/static/chunks/a.js")
    assert resp.status_code == 200
    cache = resp["Cache-Control"]
    assert "immutable" in cache
    assert "31536000" in cache


def test_html_is_never_cached(front_root: Path) -> None:
    """سند HTML نباید کش شود؛ وگرنه انتشار جدید به چشم کاربر نمی‌آید."""
    with override_settings(FRONTEND_DIST=str(front_root)):
        resp = _client().get("/")
    assert "no-cache" in resp["Cache-Control"]


def test_rsc_payload_is_served(front_root: Path) -> None:
    """بارِ RSC (`index.txt`) باید سرو شود؛ وگرنه هر کلیک بارگذاری کامل است."""
    with override_settings(FRONTEND_DIST=str(front_root)):
        resp = _client().get("/register/index.txt")
    assert resp.status_code == 200
    assert resp["Content-Type"].startswith("text/plain")
    assert "$Sreact.fragment" in resp.content.decode("utf-8")


def test_build_header_reports_served_version(front_root: Path) -> None:
    """سرآیند نسخه — تنها سنجهٔ بیرونی از کدام نسخه سرو می‌شود."""
    with override_settings(FRONTEND_DIST=str(front_root)):
        resp = _client().get("/")
    assert "9.9.9" in resp["X-Frontend-Build"]
    assert "abcdef123456" in resp["X-Frontend-Build"]


# ── مرز API و بک‌اند ─────────────────────────────────────────────────────


def test_missing_asset_returns_empty_not_html(front_root: Path) -> None:
    """چانک ناموجود نباید بدنهٔ HTML بگیرد (خطای «Unexpected token <» می‌دهد)."""
    with override_settings(FRONTEND_DIST=str(front_root)):
        resp = _client().get("/_next/static/chunks/missing.js")
    assert resp.status_code == 404
    assert resp.content == b""
    assert "text/html" not in resp["Content-Type"]


def test_api_paths_are_never_swallowed(front_root: Path) -> None:
    """مسیرهای API به فرانت نمی‌روند، حتی اگر فایلی با همان نام باشد."""
    with override_settings(FRONTEND_DIST=str(front_root)):
        resp = _client().get("/api/v1/health/live/")
    assert resp.status_code == 200
    assert resp["Content-Type"].startswith("application/json")


def test_missing_api_route_stays_404_json(front_root: Path) -> None:
    """۴۰۴ مسیر API نباید با صفحهٔ HTML فرانت پوشانده شود."""
    with override_settings(FRONTEND_DIST=str(front_root)):
        resp = _client().get("/api/v1/does-not-exist/")
    assert resp.status_code == 404
    assert "text/html" not in resp["Content-Type"]


def test_api_root_discovery_moved_to_v1() -> None:
    """کاتالوگ کشف API در `/api/v1/` است، نه در ریشهٔ دامنه."""
    resp = _client().get("/api/v1/")
    assert resp.status_code == 200
    assert "public_endpoints" in resp.json()["data"]


# ── امنیت مسیر ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "path",
    [
        "/../etc/passwd",
        "/img/../../etc/passwd",
        "/_next/static/chunks/../../../etc/passwd",
        "/%2e%2e/%2e%2e/etc/passwd",
    ],
)
def test_path_traversal_is_rejected(front_root: Path, path: str) -> None:
    """هیچ ترکیبی از `..` نباید از ریشهٔ فرانت بیرون بزند."""
    with override_settings(FRONTEND_DIST=str(front_root)):
        resp = _client().get(path)
    assert resp.status_code in (400, 404)
    assert b"root:" not in resp.content


# ── CSP ───────────────────────────────────────────────────────────────────


def test_html_csp_allows_next_and_hashes_inline_scripts(front_root: Path) -> None:
    """سیاست سند فرانت باید self و هش اسکریپت درون‌خطی را داشته باشد.

    اگر این‌جا `default-src 'none'` بماند، سایت کاملاً سفید می‌شود:
    هیچ CSS، JS، فونت یا تصویری بار نمی‌شود.
    """
    with override_settings(FRONTEND_DIST=str(front_root)):
        resp = _client().get("/")
    csp = resp["Content-Security-Policy"]
    assert "default-src 'self'" in csp
    assert "script-src 'self'" in csp
    assert "sha256-" in csp, "هش اسکریپت درون‌خطی غایب است — سند اجرا نمی‌شود"
    assert "'unsafe-inline'" not in csp.split("style-src")[0].split("script-src")[1]
    assert "frame-ancestors 'none'" in csp
    assert "object-src 'none'" in csp


def test_api_csp_stays_strict() -> None:
    """پاسخ‌های JSON همان سیاست سخت‌گیرانه را نگه می‌دارند."""
    resp = _client().get("/api/v1/health/live/")
    assert resp["Content-Security-Policy"] == (
        "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
    )


# ── حالت‌های مرزی ────────────────────────────────────────────────────────


def test_without_frontend_installed_404_is_kept(tmp_path: Path, monkeypatch) -> None:
    """نبود فرانت، سایت را نمی‌خواباند: رفتار قبلی (۴۰۴) دست‌نخورده می‌ماند."""
    from apps.core import frontend as fe

    # مسیرهای جانشین خالی می‌شوند تا «نصب‌نشده» واقعاً نصب‌نشده باشد؛
    # وگرنه فرانتِ نصب‌شدهٔ همین مخزن پیدا می‌شود و آزمون بی‌معنا می‌شد.
    monkeypatch.setattr(fe, "_FRONTEND_FALLBACKS", ())
    with override_settings(FRONTEND_DIST=str(tmp_path / "does-not-exist")):
        resp = _client().get("/")
    assert resp.status_code == 404


def test_incomplete_frontend_is_treated_as_absent(tmp_path: Path, monkeypatch) -> None:
    """پوشه‌ای که `index.html` ندارد، فرانت نصب‌شده حساب نمی‌شود."""
    from apps.core import frontend as fe

    monkeypatch.setattr(fe, "_FRONTEND_FALLBACKS", ())
    root = tmp_path / "partial"
    root.mkdir()
    (root / "robots.txt").write_text("x", "utf-8")
    with override_settings(FRONTEND_DIST=str(root)):
        resp = _client().get("/")
    assert resp.status_code == 404


def test_post_is_not_answered_by_frontend(front_root: Path) -> None:
    """فرانت فقط GET/HEAD را جواب می‌دهد؛ POST به بک‌اند می‌رسد."""
    with override_settings(FRONTEND_DIST=str(front_root)):
        resp = _client().post("/register/", data={})
    assert resp.status_code in (403, 404, 405)


def test_json_client_does_not_get_html(front_root: Path) -> None:
    """کلاینتی که JSON می‌خواهد نباید ۲۰۰ با بدنهٔ HTML بگیرد."""
    with override_settings(FRONTEND_DIST=str(front_root)):
        resp = _client().get("/register/", HTTP_ACCEPT="application/json")
    assert resp.status_code == 404


class TestAllowedHostsWww:
    """نسخهٔ www باید بی‌ویرایش .env پذیرفته شود."""

    def test_www_variant_added(self) -> None:
        from config.settings.base import _with_www

        assert "www.kaveh185.ir" in _with_www(["kaveh185.ir"])

    def test_wildcards_and_loopback_untouched(self) -> None:
        from config.settings.base import _with_www

        for host in ("*.e2b.app", "localhost", "127.0.0.1", "testserver"):
            assert host in _with_www([host])

    def test_no_double_www(self) -> None:
        from config.settings.base import _with_www

        result = _with_www(["kaveh185.ir", "www.kaveh185.ir"])
        assert result.count("www.kaveh185.ir") == 1
        assert "www.www.kaveh185.ir" not in result


class TestFrontendPathFallback:
    """اگر `.env` به مسیر کهنه اشاره کند، سایت نباید ۵۰۳ بدهد."""

    def test_falls_back_to_base_dir_frontend(self, settings, tmp_path) -> None:
        from apps.core import frontend as fe

        built = Path(settings.BASE_DIR) / "frontend"
        fresh = tmp_path / "new-frontend"
        fresh.mkdir()
        (fresh / "index.html").write_text("<!doctype html><title>x</title>", encoding="utf-8")

        original = getattr(settings, "FRONTEND_DIST", None)
        original_fallbacks = fe._FRONTEND_FALLBACKS
        try:
            settings.FRONTEND_DIST = str(tmp_path / "stale-does-not-exist")
            fe._FRONTEND_FALLBACKS = (fresh,)
            assert fe.frontend_root() == fresh
        finally:
            settings.FRONTEND_DIST = original
            fe._FRONTEND_FALLBACKS = original_fallbacks
            assert built is not None

    def test_env_path_wins_when_valid(self, settings, tmp_path) -> None:
        from apps.core import frontend as fe

        good = tmp_path / "good"
        good.mkdir()
        (good / "index.html").write_text("<!doctype html>", encoding="utf-8")
        fallback = tmp_path / "fallback"
        fallback.mkdir()
        (fallback / "index.html").write_text("<!doctype html>", encoding="utf-8")

        original = getattr(settings, "FRONTEND_DIST", None)
        original_fallbacks = fe._FRONTEND_FALLBACKS
        try:
            settings.FRONTEND_DIST = str(good)
            fe._FRONTEND_FALLBACKS = (fallback,)
            assert fe.frontend_root() == good
        finally:
            settings.FRONTEND_DIST = original
            fe._FRONTEND_FALLBACKS = original_fallbacks

"""سرو کردن فرانت ایستای Next از درون جنگو — یک مبدأ، بی‌Node، بی‌CORS.

چرا این ماژول وجود دارد
────────────────────────
میزبان cPanel این پروژه فرآیند Node دائمی ندارد (سقف فرآیند LVE، نبودِ
systemd). تنها چیزی که همیشه زنده است Passenger + جنگو است. پس فرانت
(`output: "export"`) به HTML/JS/CSS ایستا تبدیل می‌شود و همین میان‌افزار
آن را سرو می‌کند:

    /                    → out/index.html            (پیش‌رندر صفحهٔ اول)
    /register/           → out/register/index.html
    /_next/static/...    → out/_next/static/...      (کش immutable)
    /media/...  /icon-*.png  /og.png ...  → فایل‌های عمومی فرانت
    /api/v1/...          → هرگز به اینجا نمی‌رسد؛ PatternShortCircuitMiddleware
                            آن را پیش‌تر به جنگو می‌سپارد

چند تصمیم که این کد را از یک `static()` ساده جدا می‌کند
───────────────────────────────────────────────────────
۱) **کش صحیح.** دارایی‌های `_next/static` هش محتوا در نام دارند و
   immutable‌اند؛ ولی HTML باید `no-cache` باشد، وگرنه کاربر پس از
   استقرار نسخهٔ جدید، نسخهٔ قدیمی را از کش مرورگر می‌بیند. این تمایز
   مهم‌ترین دلیلِ نوشتنِ این ماژول است، نه خودِ خواندن فایل.
۲) **فشرده‌سازی از پیش.** هنگام استقرار، همزاد `.br` و `.gz` هر فایل
   متنی ساخته می‌شود؛ اگر مرورگر `br` را بپذیرد همان سرو می‌شود (بی‌هزینهٔ
   CPU روی هاست اشتراکی) و وگرنه WhiteNoise یا فایل خام.
۳) **فشرده‌سازی پویا فقط برای HTML.** پاسخ HTML بدون همزاد، در همان
   درخواست gzip می‌شود (۷۷KB ← ~۱۴KB) چون Passenger به‌طور پیش‌فرض
   فشرده نمی‌کند.
۴) **مسیر بی‌اسلش.** `trailingSlash: true` است، پس `/register` به
   `/register/` می‌رود — با ۳۰۸ (برای GET/HEAD؛ بقیهٔ متدها ۳۰۷) تا
   متد و بدنه حفظ شود.
۵) **۴۰۴ واقعی.** مسیر ناشناخته باید وضعیت ۴۰۴ داشته باشد، حتی وقتی
   بدنهٔ آن صفحهٔ ۴۰۴ خودِ فرانت است. سرو کردنش با ۲۰۰، خزنده‌ها را
   فریب می‌دهد و به کاربر می‌گوید آدرس سالم است.
۶) **امنیت مسیر.** نام فایل از URL کاربر می‌آید؛ پس هر مسیر با
   `realpath` حل و با ریشهٔ فرانت مقایسه می‌شود. `..`، مسیر مطلق، و
   پیوند نمادین به بیرون همه رد می‌شوند.
۷) **خرابی فرانت، سایت را نمی‌خواباند.** اگر پوشهٔ فرانت نباشد یا ناقص
   باشد، `/` پاسخِ ۵۰۳ با راهنمای فارسی می‌دهد (نه ۵۰۰ خام و نه
   ریدایرکت به `/admin`). API و ادمین دست‌نخورده کار می‌کنند.

قرارداد استقرار
───────────────
`FRONTEND_DIST` (پیش‌فرض: `<BASE_DIR>/frontend`) پوشه‌ای است که
`out/` فرانت درونش قرار می‌گیرد. هر فایل `BUILD_INFO.json` در همان ریشه
هش SHA-256 و زمان ساخت را می‌دهد و در سرآیند `X-Frontend-Build` برمی‌گردد
— تنها راهی که از بیرون می‌شود فهمید کدام نسخه سرو می‌شود.
"""

from __future__ import annotations

import base64
import gzip
import hashlib
import json
import mimetypes
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from django.conf import settings
from django.http import (
    HttpRequest,
    HttpResponse,
    HttpResponsePermanentRedirect,
)
from django.utils.cache import patch_cache_control

# نوع‌های محتوایی که فشرده‌کردنشان سود دارد (تصویر و ویدیو از پیش فشرده‌اند)
_COMPRESSIBLE = re.compile(
    r"^(text/|application/(javascript|json|xml|manifest\+json)|image/svg\+xml)", re.I
)
_BR_EXT = ".br"
_GZ_EXT = ".gz"

# فایل‌های ریشهٔ خروجی که مستقیماً با نام دقیقشان سرو می‌شوند
_ROOT_FILES = {
    "robots.txt",
    "manifest.webmanifest",
    "og.png",
    "favicon.ico",
    "icon.png",
    "icon-192.png",
    "icon-512.png",
    "icon-maskable-512.png",
}

# پیشوندهایی که قطعاً به دارایی‌های فرانت تعلق دارند.
# ⚠️ `/media/` اینجا نیست: آن مسیر مال `MEDIA_URL` جنگو است (فایل‌های
# آپلودی). تصاویر فرانت در `/img/` هستند تا این دو هرگز با هم برخورد نکنند.
_ASSET_PREFIXES = ("/_next/", "/fonts/", "/img/")

# مسیرهایی که هرگز نباید به فرانت بروند (API، ادمین، مستندات، فایل‌های استاتیک جنگو)
_BACKEND_PREFIXES = (
    "/api/",
    "/admin/",
    "/static/",
    "/media/",
    "/metrics/",
    "/__debug__/",
)

_PAGE_RE = re.compile(r"^[A-Za-z0-9._~\-/]*$")

# اسکریپت‌های درون‌خطی سند — برای ساخت هش CSP. `src=` دارها حساب نمی‌شوند.
_INLINE_SCRIPT_RE = re.compile(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", re.S)


@dataclass(frozen=True)
class _Build:
    """شناسهٔ نسخهٔ فرانتِ سروشده (از `BUILD_INFO.json`)."""

    sha: str = ""
    built_at: str = ""
    version: str = ""
    # شناسهٔ کامیتِ فرانت (از `BUILD_INFO.json`) — اسکریپت استقرار با همین
    # مقدار تطبیق می‌دهد که بستهٔ تازه واقعاً سرو می‌شود یا نه.
    commit: str = ""

    def header(self) -> str:
        """مقدار سرآیند `X-Frontend-Build` — برای عیب‌یابی و راستی‌آزمایی استقرار."""
        if not self.sha:
            return "unknown"
        parts = [self.version] if self.version else []
        if self.commit:
            parts.append(self.commit)
        parts.append(self.sha[:12])
        return " ".join(parts)


#: جای‌هایی که بستهٔ فرانت واقعاً نصب می‌شود، به ترتیب اولویت.
#: چرا چند مسیر؟ چون اسکریپت نصب بسته را در `<BASE_DIR>/frontend` می‌نشاند،
#: ولی `.env` هاست ممکن است از نصب قبلی به مسیر دیگری اشاره کند. اگر فقط
#: به `.env` تکیه کنیم، سایت به‌جای خودش صفحهٔ ۵۰۳ می‌دهد — خطایی که شبیه
#: «نصب نشده» است و آدم را سمت اشتباه می‌فرستد.
_FRONTEND_FALLBACKS = (Path(settings.BASE_DIR) / "frontend",)


def _candidate_roots() -> list[Path]:
    """مسیرهای نامزد، به ترتیب: `.env` اول، بعد پیش‌فرض‌ها."""
    roots: list[Path] = []
    raw = getattr(settings, "FRONTEND_DIST", None)
    if raw:
        roots.append(Path(raw))
    roots.extend(_FRONTEND_FALLBACKS)
    seen: set[str] = set()
    unique: list[Path] = []
    for root in roots:
        key = str(root)
        if key in seen:
            continue
        seen.add(key)
        unique.append(root)
    return unique


def frontend_root() -> Path | None:
    """ریشهٔ خروجی فرانت اگر موجود و معتبر باشد، وگرنه `None`.

    وجود `index.html` معیار است: پوشه‌ای که `index.html` ندارد، فرانتِ
    ساخته‌شده نیست (مثلاً فقط `public/`) و سرو کردنش صفحهٔ سفید می‌دهد.
    """
    for root in _candidate_roots():
        if (root / "index.html").is_file():
            return root
    return None


def _read_build(root: Path) -> _Build:
    """خواندن `BUILD_INFO.json` — نبودش خطا نیست، فقط شناسهٔ ناشناخته."""
    try:
        data = json.loads((root / "BUILD_INFO.json").read_text("utf-8"))
    except (OSError, ValueError):
        return _Build()
    if not isinstance(data, dict):
        return _Build()
    return _Build(
        sha=str(data.get("sha256_index", "")),
        built_at=str(data.get("built_at", "")),
        version=str(data.get("version", "")),
        commit=str(data.get("commit", "")),
    )


def _safe_join(root: Path, relative: str) -> Path | None:
    """پیوست امن مسیر درخواست به ریشهٔ فرانت.

    چرا نه `os.path.join` ساده؟ چون `/img/../../../etc/passwd` می‌تواند
    از ریشه بیرون بزند.

    ⚠️ چرا `resolve()` روی **ریشه** و بررسی مسیر **نسبی**، نه resolve روی
    نتیجهٔ نهایی؟ در استقرار واقعی `root` خودش یک پیوند نمادین است
    (`frontend → current → releases/<id>`). اگر نتیجهٔ نهایی را resolve
    کنیم و با `root`ِ حل‌نشده مقایسه کنیم، مقایسه همیشه شکست می‌خورد و
    **همهٔ صفحات ۴۰۴ می‌شوند** — باگی که در تمرین اول دقیقاً همین رخ داد.
    پس ریشه یک‌بار حل می‌شود و مرز روی مسیر نسبی سنجیده می‌شود؛ هر
    `..` یا مسیر مطلق همان‌جا رد می‌شود.

    پیوندهای نمادینِ *داخل* بسته هم بی‌خطرند: اسکریپت استقرار بسته را
    با `--no-same-owner` باز می‌کند و هر پیوندی که با `..` از ریشه بیرون
    بزند همان‌جا در `_resolve_page` با نبودِ فایل رد می‌شود.
    """
    if relative.startswith("/") or "\\" in relative:
        return None
    base = root.resolve()
    parts = [p for p in relative.split("/") if p not in ("", ".")]
    if any(p == ".." for p in parts):
        return None
    return base.joinpath(*parts)


def _cache_headers(path: Path, response: HttpResponse) -> None:
    """کش مناسب هر نوع فایل — مهم‌ترین بخش این ماژول.

    `_next/static` و `media` هش/نسخه در نام دارند ⇒ یک سال immutable.
    بقیهٔ دارایی‌ها (فونت، آیکون، manifest) با ۷ روز و revalidate.
    خودِ HTML هیچ‌وقت کش نمی‌شود؛ وگرنه انتشار جدید به چشم کاربر نمی‌آید.
    """
    posix = path.as_posix()
    if "/_next/static/" in posix:
        patch_cache_control(response, public=True, max_age=31536000, immutable=True)
    elif path.suffix in {".html", ".txt"}:
        # HTML: همیشه دوباره از سرور. `no-cache` یعنی «بپرس»، نه «کش نکن» — که
        # دقیقاً همان چیزی است که برای سند اصلی می‌خواهیم (با ETag/304 ارزان است).
        patch_cache_control(response, no_cache=True, must_revalidate=True, max_age=0)
    elif path.suffix in {".woff2", ".png", ".jpg", ".jpeg", ".webp", ".avif", ".svg", ".ico"}:
        patch_cache_control(response, public=True, max_age=604800)
    else:
        patch_cache_control(response, public=True, max_age=3600)


def _serve_file(
    request: HttpRequest,
    path: Path,
    *,
    content_type: str | None = None,
    status: int = 200,
    patch: bool = True,
) -> HttpResponse:
    """سرو یک فایل با فشرده‌سازی از پیش (br/gz) و سرآیندهای درست."""
    ctype = content_type or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    compressible = bool(_COMPRESSIBLE.match(ctype))

    accept = request.headers.get("Accept-Encoding", "")
    variant: Path | None = None
    encoding = ""
    if compressible:
        if "br" in accept and path.with_name(path.name + _BR_EXT).is_file():
            variant, encoding = path.with_name(path.name + _BR_EXT), "br"
        elif "gzip" in accept and path.with_name(path.name + _GZ_EXT).is_file():
            variant, encoding = path.with_name(path.name + _GZ_EXT), "gzip"

    # ── چرا `HttpResponse` و نه `FileResponse`؟ ─────────────────────────────
    #
    # `FileResponse` فایل را جریانی و با `Content-Length` می‌فرستد که برای
    # دارایی‌های سنگین (تصویر ۱۷۰KB، فونت) ایده‌آل است. ولی این فایل‌ها
    # روی دیسک هاست کوچک‌اند (کل بسته زیر ۲MB) و در کش صفحهٔ سیستم‌عامل
    # می‌مانند؛ خواندنشان بی‌هزینه است. در عوض `HttpResponse`:
    #   • با `HEAD` درست رفتار می‌کند (بدون خواندن بدنه)،
    #   • در تست‌ها `.content` دارد،
    #   • و خطای «فایل باز ماند» در بازرسیِ منابع پایتست نمی‌سازد.
    # چیزی که واقعاً مهم است — `Content-Length`, `Content-Type`, `Vary`,
    # `Content-Encoding` و `Cache-Control` — در هر دو حالت یکی است.
    target_path = variant if variant is not None else path
    body = target_path.read_bytes()
    compress_inline = False
    if variant is None and compressible and "gzip" in accept:
        # همزاد پیش‌فشرده نداریم ⇒ همین‌جا gzip کن. برای HTML، تنها سندی
        # که همیشه از سرور می‌آید (no-cache)، این هزینه ناچیز است.
        body = gzip.compress(body, compresslevel=6)
        compress_inline = True

    response = HttpResponse(body, content_type=ctype, status=status)
    if variant is not None:
        response["Content-Encoding"] = encoding
    elif compress_inline:
        response["Content-Encoding"] = "gzip"

    # Vary همیشه لازم است، حتی وقتی نسخهٔ خام می‌دهیم: کش مشترک نباید
    # پاسخ gzip را به کلاینتی بدهد که آن را نمی‌فهمد.
    response["Vary"] = "Accept-Encoding"
    if patch:
        _cache_headers(path, response)
    return response


def _wants_html(request: HttpRequest) -> bool:
    """آیا کلاینت واقعاً HTML می‌خواهد؟ (پیش‌بارگذاری RSC و fetch، نه)"""
    if request.method not in ("GET", "HEAD"):
        return False
    rsc = request.headers.get("RSC")
    if rsc in ("1", "true"):
        return False
    purpose = request.headers.get("Sec-Fetch-Purpose") or request.headers.get("Purpose")
    if purpose in ("prefetch", "prefetch-html"):
        return False
    accept = request.headers.get("Accept", "")
    if not accept:
        # curl و ابزارهای ساده: فرض کن HTML می‌خواهند
        return True
    return "text/html" in accept or "*/*" in accept or "application/xhtml+xml" in accept


def _resolve_page(root: Path, url_path: str) -> tuple[Path, int] | None:
    """تبدیل مسیر URL به فایل HTML + وضعیت HTTP.

    ترتیب: فایل دقیق (مثل `/robots.txt`) ← پوشه + index.html ← سند ۴۰۴.
    """
    relative = url_path.strip("/")

    if not _PAGE_RE.match(relative):
        return None

    # ۱) فایل ریشه با نام دقیق
    if "/" not in relative and relative in _ROOT_FILES:
        target = _safe_join(root, relative)
        if target and target.is_file():
            return target, 200
        return None

    # ۲) مسیرهای دارایی (چه با اسلش، چه بی‌اسلش)
    for prefix in _ASSET_PREFIXES:
        if url_path.startswith(prefix):
            # `_safe_join` مسیر **نسبی** می‌خواهد؛ اسلش ابتدای URL اینجا
            # حذف می‌شود وگرنه همان‌جا رد می‌شود و هر تصویر/چانک ۴۰۴ می‌دهد.
            target = _safe_join(root, url_path.lstrip("/"))
            if target and target.is_file():
                return target, 200
            return None

    # ۳) صفحهٔ پیش‌رندرشده: /login/ → login/index.html
    if relative:
        candidate = _safe_join(root, f"{relative}/index.html")
        if candidate and candidate.is_file():
            return candidate, 200

        # فایل‌های خروجی که نام دقیقشان در URL می‌آید:
        #   • `.html` — سند مستقیم
        #   • `.txt`  — ⚠️ بارِ RSC که روتر Next برای ناوبری بدون بارگذاری کامل
        #     صفحه درخواست می‌کند (`/login/index.txt`, `/login/__next._tree.txt`).
        #     اگر این‌ها ۴۰۴ شوند، هر کلیک روی لینک داخلی به بارگذاری کامل
        #     صفحه می‌افتد و prefetch بی‌اثر می‌شود — بی‌هیچ خطای کنسولی.
        #     ۳۲ فایل از این نوع در هر ساخت تولید می‌شود.
        #   • `.json` — در صورت افزودن route handler ایستا
        direct = _safe_join(root, relative)
        if direct and direct.is_file() and direct.suffix in {".html", ".txt", ".json"}:
            return direct, 200

    # ۴) ریشه
    index = _safe_join(root, "index.html")
    if not relative and index and index.is_file():
        return index, 200

    # ۵) صفحهٔ ۴۰۴ خودِ فرانت — با وضعیت واقعی ۴۰۴
    not_found = _safe_join(root, "404.html")
    if not_found and not_found.is_file():
        return not_found, 404
    return None


# ── سیاست امنیت محتوا برای سندهای فرانت ─────────────────────────────────
#
# چرا اینجا و نه در `SecurityHeadersMiddleware`؟ چون سیاست باید **هش
# اسکریپت‌های درون‌خطی همان سند** را بداند. Next در هر صفحه چند
# `<script>` درون‌خطی دارد (بارِ RSC و اسکریپت تم) و هش‌شان با هر ساخت
# عوض می‌شود. سیاست ثابت یا `'unsafe-inline'` می‌خواهد یا صفحه را
# می‌شکند؛ هیچ‌کدام پذیرفتنی نیست، پس هش در همان درخواستی محاسبه
# می‌شود که سند را می‌دهیم (با کش کوچک، چون خروجی ایستاست).
_CSP_CACHE: dict[str, tuple[str, tuple[float, int]]] = {}
_CSP_CACHE_MAX = 64


def _document_csp(path: Path) -> str:
    """ساخت CSP دقیق برای یک سند HTML بر پایهٔ هش اسکریپت‌های درون‌خطی‌اش.

    `'unsafe-inline'` برای **style** لازم است چون Next و Tailwind در
    چند نقطه `style="..."` درون‌خطی می‌گذارند (عرض نوار پیشرفت،
    اندازهٔ آواتار). اسکریپت اما هیچ `'unsafe-inline'` نمی‌گیرد: هش
    دقیق، تا تزریق اسکریپت ممکن نباشد.
    """
    st = path.stat()
    cache_key = path.as_posix()
    cached = _CSP_CACHE.get(cache_key)
    if cached and cached[1] == (st.st_mtime, st.st_size):
        return cached[0]

    html = path.read_text("utf-8", errors="replace")
    hashes = sorted(
        {
            "'sha256-"
            + base64.b64encode(hashlib.sha256(body.encode("utf-8")).digest()).decode("ascii")
            + "'"
            for body in _INLINE_SCRIPT_RE.findall(html)
        }
    )
    script_src = " ".join(["'self'", *hashes])
    policy = (
        "default-src 'self'; "
        f"script-src {script_src}; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "font-src 'self'; "
        "connect-src 'self'; "
        "manifest-src 'self'; "
        "worker-src 'self'; "
        "object-src 'none'; "
        "base-uri 'none'; "
        "form-action 'self'; "
        "frame-ancestors 'none'"
    )
    if len(_CSP_CACHE) >= _CSP_CACHE_MAX:
        _CSP_CACHE.clear()
    _CSP_CACHE[cache_key] = (policy, (st.st_mtime, st.st_size))
    return policy


class FrontendMiddleware:
    """آخرین میان‌افزار: هر درخواستی که جنگو برایش پاسخی **ندارد**، به فرانت می‌رود.

    «آخرین» بودن مهم است: یعنی مسیرهای API، ادمین و استاتیک پیش از این
    میان‌افزار پاسخ گرفته‌اند و اینجا فقط پوستهٔ سایت می‌ماند. اگر فرانت
    نصب نباشد، رفتار دقیقاً مثل قبل از این تغییر است (هیچ مسیری از فرانت
    پاسخ نمی‌گیرد) — پس این میان‌افزار هرگز بک‌اند را از کار نمی‌اندازد.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        """ذخیرهٔ حلقهٔ بعدی میان‌افزار (الگوی استاندارد جنگو)."""
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        """پاسخ جنگو اگر وجود داشته باشد؛ وگرنه پاسخ فرانت."""
        response = self.get_response(request)

        # ۴۰۴ از جنگو = «چنین مسیری در بک‌اند نداریم» → شاید صفحهٔ فرانت باشد.
        # بقیهٔ وضعیت‌ها (۲۰۰، ۳۰۱، ۴۰۳، ۵۰۰…) پاسخ واقعی‌اند و دست نمی‌خورند:
        # اگر جنگو ۵۰۰ داده، پنهان‌کردنش زیر صفحهٔ فرانت، عیب‌یابی را نابود می‌کند.
        if getattr(response, "status_code", None) != 404:
            return response
        if request.method not in ("GET", "HEAD"):
            return response

        root = frontend_root()
        if root is None:
            return response

        front = self._front_response(request, root)
        if front is not None:
            return front

        # دارایی ناموجود (چانک JS، فونت، تصویر) نباید بدنهٔ ۴۰۴ **HTML** بگیرد.
        # مرورگر آن را به‌جای اسکریپت اجرا می‌کند و خطای «Unexpected token '<'»
        # می‌دهد که ریشهٔ واقعی مشکل را پنهان می‌کند. پاسخ خالی با کد ۴۰۴
        # گویاتر است و کنسول هم پیام درست نشان می‌دهد.
        if request.path_info.startswith(_ASSET_PREFIXES):
            empty = HttpResponse("", status=404, content_type="text/plain; charset=utf-8")
            empty["Cache-Control"] = "no-store"
            return empty
        return response

    # ── داخلی ──────────────────────────────────────────────────────────

    def _front_response(self, request: HttpRequest, root: Path) -> HttpResponse | None:
        """انتخاب و ساخت پاسخ فرانت برای یک درخواست GET/HEAD."""
        url_path = request.path_info
        build = _read_build(root)

        # مسیرهای بک‌اند باید ۴۰۴ بمانند؛ فرانت نباید آن‌ها را ببلعد.
        if url_path.startswith(_BACKEND_PREFIXES):
            return None

        # ۱) مسیر صفحه بی‌اسلش ⇒ ۳۰۸ به نسخهٔ با اسلش (trailingSlash: true).
        #
        # چرا این پیش از حل مسیر است؟ چون `/register` و `/register/` هر دو
        # به همان فایل می‌رسند و سرو کردن هر دو با ۲۰۰، دو نشانی برای یک
        # محتوا می‌سازد (مشکل سئو + دو برابر شدن کش). اینجا فقط پوشه‌هایی
        # که `index.html` دارند هدایت می‌شوند؛ فایل‌ها (تصویر، CSS، JS) و
        # مسیر ریشه دست نمی‌خورند.
        #
        # چرا ۳۰۸ و نه ۳۰۱؟ ۳۰۱ را مرورگر برای همیشه کش می‌کند؛ اگر ساختار
        # مسیر فردا عوض شود، کاربر گیر می‌افتد. ۳۰۸ متد و بدنه را حفظ
        # می‌کند و کش نمی‌شود.
        if url_path != "/" and not url_path.endswith("/"):
            relative = url_path.strip("/")
            if _PAGE_RE.match(relative):
                index = _safe_join(root, f"{relative}/index.html")
                if index is not None and index.is_file():
                    query = request.META.get("QUERY_STRING", "")
                    target = f"{url_path}/" + (f"?{query}" if query else "")
                    response = HttpResponsePermanentRedirect(target)
                    # `HttpResponsePermanentRedirect` کلاس ۳۰۱ است؛ وضعیت را
                    # صریح روی ۳۰۸ می‌گذاریم و `Location` را هم می‌سازیم.
                    response.status_code = 308
                    response["X-Frontend-Build"] = build.header()
                    return response

        resolved = _resolve_page(root, url_path)
        if resolved is None:
            return None

        path, status = resolved
        # صفحهٔ HTML فقط وقتی تحویل داده می‌شود که کلاینت واقعاً سند می‌خواهد؛
        # درخواست داده‌ای (Accept: application/json) نباید ۲۰۰ با بدنهٔ HTML
        # بگیرد — وگرنه کلاینت JSON.parse روی HTML خطا می‌دهد و پیام گمراه‌کننده است.
        if path.suffix == ".html" and not _wants_html(request):
            return None

        explicit: str | None = None
        if path.suffix == ".html":
            explicit = "text/html; charset=utf-8"
        elif path.suffix == ".txt":
            # `text/x-component` چیزی است که Next برای RSC می‌فرستد، ولی این
            # فایل‌ها در واقع متن ساده‌اند و جنگو نباید حدس بزند.
            explicit = "text/plain; charset=utf-8"
        elif path.suffix == ".json":
            explicit = "application/json"

        response = _serve_file(
            request,
            path,
            content_type=explicit,
            status=status,
        )
        if path.suffix == ".html":
            # سیاست باید در **همین** پاسخ باشد؛ `setdefault` در
            # `SecurityHeadersMiddleware` دیگر چیزی اضافه نمی‌کند.
            response["Content-Security-Policy"] = _document_csp(path)
        response["X-Frontend-Build"] = build.header()
        return response


def frontend_status() -> dict[str, Any]:
    """خلاصهٔ وضعیت فرانت برای `/health/ready/` و اسکریپت استقرار."""
    root = frontend_root()
    if root is None:
        return {"installed": False, "root": str(getattr(settings, "FRONTEND_DIST", ""))}
    build = _read_build(root)
    return {
        "installed": True,
        "root": str(root),
        "version": build.version,
        "commit": build.commit,
        "built_at": build.built_at,
        "sha": build.sha[:12],
    }


def frontend_503(reason: str) -> HttpResponse:
    """صفحهٔ ۵۰۳ فارسی و خودبسنده برای وقتی فرانت نصب/سالم نیست.

    چرا نه ۵۰۰ خام؟ چون این حالت «خرابی» نیست، «نصب‌نشده» است: اپراتور
    باید بداند چه کند. و چرا نه ریدایرکت به `/admin`؟ چون کاربر عادی را
    به صفحهٔ ورود ادمین می‌فرستد و سردرگم می‌کند.
    """
    body = f"""<!doctype html>
<html lang="fa" dir="rtl"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>کاوه ۱۸۵ — سایت در حال به‌روزرسانی</title>
<style>
  :root{{color-scheme:light}}
  body{{margin:0;min-height:100vh;display:grid;place-items:center;
       font-family:system-ui,"Segoe UI",Tahoma,sans-serif;background:#faf7f0;color:#2a2320}}
  main{{max-width:34rem;padding:2.5rem 1.5rem;text-align:center}}
  h1{{font-size:1.35rem;margin:0 0 .6rem}}
  p{{line-height:2;color:#5b524b;margin:0 0 .5rem;font-size:.92rem}}
  code{{background:#efe7d8;padding:.15rem .4rem;border-radius:.3rem;
        font-size:.85rem;direction:ltr;display:inline-block}}
</style>
<main>
  <h1>سایت لحظه‌ای در دسترس نیست</h1>
  <p>بک‌اند سالم است، ولی نسخهٔ رابط کاربری روی سرور نصب یا کامل نیست.</p>
  <p>اپراتور: خروجی ساخت فرانت را در مسیر <code>FRONTEND_DIST</code> قرار دهید و
     <code>touch tmp/restart.txt</code> بزنید.</p>
  <p style="opacity:.6;font-size:.78rem;margin-top:1.5rem">شناسه: {reason}</p>
</main>
</html>"""
    response = HttpResponse(body, content_type="text/html; charset=utf-8", status=503)
    response["Cache-Control"] = "no-store"
    return response


__all__ = [
    "FrontendMiddleware",
    "frontend_503",
    "frontend_root",
    "frontend_status",
]

"""سرو فایل‌های رسانه — مستقل از `DEBUG`.

── چرا این ماژول لازم شد؟ ───────────────────────────────────────────────
در حالت پیش‌فرض جنگو، `static(settings.MEDIA_URL, …)` فقط با `DEBUG=True`
مسیر می‌دهد. روی هاستِ واقعی `DEBUG=False` است و نتیجه این بود که تصاویر
ادمین (گالری، شهدا) با ۴۰۴ برمی‌گشتند — درحالی‌که آپلود درست انجام شده
بود. این ماژول همان کار را می‌کند، با سه تفاوت مهم:

۱) **فقط تصویر.** `.env`، `.py`، `.sql` و هر چیز دیگر ۴۰۴ می‌شود. یک
   `ImageField` جنگو جلوی آپلود فایل غیرتصویری را می‌گیرد، ولی لایهٔ دوم
   لازم است: اگر روزی کسی مسیر را دستی بنویسد، نباید بتواند فایل
   حساس را از `MEDIA_ROOT` بخواند.
۲) **مسیر امن.** `safe_join` جلوی `../` را می‌گیرد؛ `resolve()` هم
   سیم‌لینک‌هایی را که به بیرون `MEDIA_ROOT` اشاره کنند رد می‌کند.
۳) **کش درست.** تصاویر محتوایی تغییر نام نمی‌دهند، پس یک هفته کش
   عمومی با `immutable` امن است — و اگر ادمین تصویر را عوض کند، نام فایل
   عوض می‌شود (جنگو پسوند تصادفی می‌دهد)، پس کش کهنه نمی‌ماند.

⚠️ چرا `FileResponse` و نه `HttpResponse(open(...).read())`؟ چون فایل را
کامل در حافظه نمی‌خواند؛ روی هاستِ اشتراکیِ کم‌حافظه این تفاوت بین
«کار می‌کند» و «پروسه کشته می‌شود» است.
"""

from __future__ import annotations

import mimetypes
import posixpath
from pathlib import Path

from django.conf import settings
from django.core.exceptions import SuspiciousFileOperation
from django.http import FileResponse, Http404, HttpRequest
from django.utils._os import safe_join

# پسوندهای مجاز — هر چیز دیگری ۴۰۴. تصویر و (برای کتاب مسابقه) PDF.
ALLOWED_SUFFIXES: frozenset[str] = frozenset(
    {".jpg", ".jpeg", ".png", ".webp", ".avif", ".gif", ".svg", ".pdf"}
)

# یک هفته کش عمومی؛ نام فایل با تغییر محتوا عوض می‌شود، پس امن است.
CACHE_CONTROL = "public, max-age=604800, immutable"


def media_root() -> Path:
    """ریشهٔ رسانه، به‌صورت مسیر مطلق."""
    return Path(settings.MEDIA_ROOT).resolve()


def _resolved_target(path: str) -> Path:
    """مسیر فایلِ درخواستی، بعد از اعتبارسنجی کامل.

    ترتیب کارها مهم است: اول `safe_join` (که `..` را رد می‌کند)، بعد
    `resolve()` (که سیم‌لینک را به مقصد واقعی می‌برد)، بعد بررسی اینکه
    مقصد واقعی هنوز داخل `MEDIA_ROOT` است.
    """
    root = media_root()
    try:
        joined = Path(safe_join(str(root), path))
    except (ValueError, SuspiciousFileOperation, OSError):
        raise Http404("مسیر نامعتبر است.") from None

    try:
        real = joined.resolve(strict=True)
    except (OSError, RuntimeError):
        raise Http404("فایل یافت نشد.") from None

    try:
        real.relative_to(root)
    except ValueError:
        # سیم‌لینک به بیرونِ MEDIA_ROOT — همان ۴۰۴، بدون افشای مقصد.
        raise Http404("فایل یافت نشد.") from None

    if not real.is_file():
        raise Http404("فایل یافت نشد.")
    if real.suffix.lower() not in ALLOWED_SUFFIXES:
        raise Http404("این نوع فایل سرو نمی‌شود.")
    return real


def serve_media(request: HttpRequest, path: str) -> FileResponse:
    """سرو یک فایل رسانه با هدرهای درست."""
    del request
    normalized = posixpath.normpath(path).lstrip("/")
    target = _resolved_target(normalized)

    content_type, _ = mimetypes.guess_type(str(target))
    if target.suffix.lower() == ".pdf":
        content_type = "application/pdf"
    elif not content_type or not content_type.startswith("image/"):
        content_type = (
            "application/octet-stream" if target.suffix.lower() == ".pdf" else "image/jpeg"
        )

    response = FileResponse(target.open("rb"), content_type=content_type)
    response["Cache-Control"] = CACHE_CONTROL
    response["X-Content-Type-Options"] = "nosniff"
    # تصویر نباید هرگز به‌عنوان HTML تفسیر شود (حملهٔ XSS از مسیر SVG).
    response["Content-Security-Policy"] = "default-src 'none'; style-src 'unsafe-inline'; sandbox"
    return response

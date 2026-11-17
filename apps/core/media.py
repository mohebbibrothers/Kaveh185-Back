"""سرو امنِ فایل‌های رسانه (`/media/...`) — بدون وابستگی به `DEBUG`.

── چرا این ماژول لازم شد؟ ───────────────────────────────────────────────
در حالت توسعه، جنگو خودش `MEDIA_URL` را سرو می‌کند. روی هاست واقعی با
`DEBUG=False` هیچ‌کس این کار را نمی‌کند و تصاویر ادمین (کلام رهبر، نوار
شهدا) با ۴۰۴ می‌افتادند. سه راه وجود داشت:

  ۱) گذاشتن `DEBUG=True` — غیرقابل قبول؛ صفحهٔ خطای کامل و افشای تنظیمات.
  ۲) سرو با nginx/cPanel — روی این هاست Passenger جلوی اپ است و دسترسی
     به کانفیگ وب‌سرور نداریم.
  ۳) یک نمای کوچک و **سخت‌گیر** در خود اپ. همین.

── چرا «سخت‌گیر»؟ ───────────────────────────────────────────────────────
نمایی که از دیسک فایل می‌خواند، اگر محدود نشود، می‌تواند `.env` یا
`manage.py` را هم بیرون بدهد. پس:

  • **پسوندِ فایل** باید در فهرست سفید باشد (فقط تصویر).
  • مسیر با `safe_join` به پوشهٔ `MEDIA_ROOT` قفل می‌شود (`..` بی‌اثر).
  • فایلِ ناموجود ⇒ ۴۰۴، فایلِ غیرمجاز ⇒ ۴۰۴. هیچ ۵۰۰ و هیچ پیام داخلی.
  • `X-Content-Type-Options: nosniff` تا مرورگر پسوند را «حدس» نزند.
  • کش یک‌هفته‌ای + `immutable`: تصویر گالری با آپلودِ ادمین نام عوض
    می‌کند (جنگو برای نام تکراری پسوند می‌گذارد)، پس کشِ بلند امن است و
    بار سرور اشتراکی را واقعاً کم می‌کند.
"""

from __future__ import annotations

import mimetypes
from pathlib import Path

from django.conf import settings
from django.http import FileResponse, Http404, HttpRequest
from django.utils._os import safe_join

# فقط تصویر. SVG هم عمداً هست: نشان‌ها و الگوهای تزئینی سایت SVG‌اند.
# (SVG می‌تواند اسکریپت داشته باشد؛ چون همین دامنه سرو می‌شود، هدر
# `Content-Security-Policy` سایت آن را مهار می‌کند و فایل‌ها فقط از
# پنل ادمینِ احراز هویت‌شده می‌آیند.)
ALLOWED_SUFFIXES = frozenset({".jpg", ".jpeg", ".png", ".webp", ".avif", ".gif", ".svg"})

# یک هفته. تصویر گالری پس از تغییر، نام تازه می‌گیرد؛ پس invalidation لازم نیست.
CACHE_SECONDS = 60 * 60 * 24 * 7


def serve_media(request: HttpRequest, path: str) -> FileResponse:
    """ارسال یک فایل تصویری از `MEDIA_ROOT`؛ هر چیز دیگری ۴۰۴."""
    suffix = Path(path).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise Http404("نوع فایل مجاز نیست.")

    try:
        absolute = Path(safe_join(str(settings.MEDIA_ROOT), path))
    except Exception:
        # `safe_join` روی «..» استثنا می‌دهد؛ برای کاربر یعنی «پیدا نشد».
        raise Http404("فایل پیدا نشد.") from None

    if not absolute.is_file():
        raise Http404("فایل پیدا نشد.")

    content_type = mimetypes.guess_type(absolute.name)[0] or "application/octet-stream"
    response = FileResponse(absolute.open("rb"), content_type=content_type)
    response["Cache-Control"] = f"public, max-age={CACHE_SECONDS}, immutable"
    response["X-Content-Type-Options"] = "nosniff"
    return response

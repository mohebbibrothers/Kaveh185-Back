"""سروِ فایل‌های رسانه (تصاویر آپلودی ادمین) با سرآیندهای کش درست.

── چرا این ماژول لازم شد؟ ────────────────────────────────────────────────
تا پیش از افزودن گالری، هیچ فایلی در `MEDIA_ROOT` نبود و `/media/` کد
۴۰۴ می‌داد. با آپلود تصویر از پنل ادمین، آدرس تصویر
`/media/gallery/...` می‌شود و **باید** کار کند. سه گزینه بررسی شد:

۱) `static(settings.MEDIA_URL, document_root=...)` در `urls.py` —
   استاندارد است، ولی با `DEBUG=False` روی این میزبان جای دیگری برای
   سرو نیست (Apache/Passenger همه را به جنگو می‌دهد) و تصویر ۴۰۴ می‌شود.
۲) WhiteNoise — فقط `STATIC_ROOT` را سرو می‌کند، نه `MEDIA_ROOT` را؛
   و تصاویر تازه بلافاصله پس از آپلود در `STATIC_ROOT` نیستند (نیاز به
   `collectstatic` دستی داشت ⇒ ادمین تصویر آپلود می‌کرد و چیزی نمی‌دید).
۳) **همین ماژول** — یک نمای نازک روی `django.views.static.serve` که:
   • فقط تصویر سرو می‌کند (`ALLOWED_SUFFIXES`)؛ `/media/*.py` هرگز.
   • `Cache-Control: public, max-age=604800, immutable` می‌گذارد، چون
     نام فایل‌های آپلودی یکتاست (Django در تداخل، پسوند تصادفی می‌افزاید).
   • `X-Content-Type-Options: nosniff` — جلوگیری از تفسیر اشتباه نوع فایل.
   • مسیر را `safe_join` می‌کند، پس `../` کار نمی‌کند (خودِ serve این کار
     را می‌کند، ولی صریح نوشتنش ارزان است و برای ممیزی امنیتی مهم).

بار ترافیکی: چند تصویر گالری، هر کدام یک بار برای هر مرورگر. هزینه‌اش
در برابر «تصویر ۴۰۴ در پنل زنده» ناچیز است.
"""

from __future__ import annotations

from pathlib import PurePosixPath

from django.conf import settings
from django.http import Http404, HttpRequest, HttpResponse
from django.views.static import serve

# فقط این‌ها سرو می‌شوند. اگر روزی PDF یا ویدیو لازم شد، این‌جا اضافه شود.
ALLOWED_SUFFIXES = frozenset({".jpg", ".jpeg", ".png", ".webp", ".avif", ".gif", ".svg"})

# یک هفته کش؛ فایل‌های آپلودی نام یکتا دارند، پس محتوا عوض نمی‌شود.
CACHE_SECONDS = 604_800


def serve_media(request: HttpRequest, path: str) -> HttpResponse:
    """سرو یک فایل رسانه با محدودیت پسوند و سرآیندهای کش."""
    suffix = PurePosixPath(path).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        # پاسخ ۴۰۴ (نه ۴۰۳): وجود یا نبودِ فایل غیرتصویری را افشا نمی‌کنیم.
        raise Http404("فایل مجاز نیست.")

    response = serve(
        request,
        path,
        document_root=str(settings.MEDIA_ROOT),
    )
    response["Cache-Control"] = f"public, max-age={CACHE_SECONDS}, immutable"
    response["X-Content-Type-Options"] = "nosniff"
    return response

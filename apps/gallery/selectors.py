"""استخراج دادهٔ گالری برای API عمومی — با الگوی کشِ خودِ پروژه.

── چرا همین الگوی کش؟ ───────────────────────────────────────────────────
پروژه یک لایهٔ کشِ واحد دارد (`apps.core.cache` + `cache_policy`) با
سیاستِ SWR، قفل ضد هجوم و **ابطال بر اساس دامنه**. اگر گالری کشِ جداگانهٔ
خودش را می‌ساخت، ادمین پس از آپلود تصویر تازه باید هم کش گالری را باطل
می‌کرد هم کش صفحهٔ اول را — و یکی از این دو همیشه فراموش می‌شد (همان
درسی که در `apps/core/cache_invalidation.py` نوشته شده).

پس گالری یک دامنهٔ تازه در همان رجیستری است (‏`gallery`) و ابطالش با
همان `invalidate_domain_cache(domain="gallery")` انجام می‌شود — که در
`save()`/`delete()` مدل‌ها صدا زده می‌شود.
"""

from __future__ import annotations

from typing import Any

from apps.core.cache import cache_get_or_set_swr

from .models import LeaderPortrait, Martyr

# نام دامنه در رجیستری کش (`apps/core/cache_policy.py`).
GALLERY_DOMAIN = "gallery"


def _absolute(request: Any, url: str) -> str:
    """آدرس مطلق فایل رسانه.

    ⚠️ چرا مطلق؟ فرانت روی همان دامنه سرو می‌شود و `/media/...` را جنگو
    می‌دهد؛ آدرس نسبی در `<img>` کار می‌کند، ولی در JSON-LD و
    پیش‌نمایش‌های بیرونی (پیام‌رسان، تلگرام) آدرس مطلق لازم است.
    """
    if not request or not url:
        return url
    try:
        return str(request.build_absolute_uri(url))
    except Exception:  # pragma: no cover - فقط برای محیط‌های غیرمعمول
        return url


def _portrait_payload(row: LeaderPortrait, request: Any = None) -> dict[str, Any]:
    """شکل یک تصویر رهبر برای فرانت (همهٔ رشته‌ها trim‌شده)."""
    caption = (row.caption or "").strip()
    return {
        "id": row.pk,
        "image_url": _absolute(request, row.image.url if row.image else ""),
        "alt": row.alt.strip(),
        "caption": caption,
        # بندها از پیش جدا می‌شوند تا فرانت با split درگیر نشود و بندِ
        # خالیِ ناشی از فاصلهٔ اضافی، به <p> خالی تبدیل نشود.
        "caption_paragraphs": [p.strip() for p in caption.split("\n\n") if p.strip()],
        "source": (row.source or "").strip(),
        "show_in_box": bool(row.show_in_box),
    }


def _martyr_payload(row: Martyr, request: Any = None) -> dict[str, Any]:
    """شکل یک شهید برای نوار بالای فوتر."""
    return {
        "id": row.pk,
        "image_url": _absolute(request, row.image.url if row.image else ""),
        "alt": (row.alt or row.title).strip(),
        "title": row.title.strip(),
        "subtitle": (row.subtitle or "").strip(),
    }


def _load_leader_rows() -> list[dict[str, Any]]:
    """خواندن و تبدیلِ رکوردهای فعالِ رهبر — بدون request (کش‌شدنی)."""
    rows = LeaderPortrait.objects.filter(is_active=True).order_by("order", "id")
    return [_portrait_payload(row) for row in rows]


def _load_martyr_rows() -> list[dict[str, Any]]:
    """خواندن و تبدیلِ رکوردهای فعالِ شهدا — بدون request (کش‌شدنی)."""
    rows = Martyr.objects.filter(is_active=True).order_by("order", "id")
    return [_martyr_payload(row) for row in rows]


def _absolutize(items: list[dict[str, Any]], request: Any) -> list[dict[str, Any]]:
    """جایگزینی آدرس نسبیِ کش‌شده با آدرس مطلقِ همین درخواست.

    کش، `image_url` نسبی نگه می‌دارد تا یک نسخه برای هر دامنه کافی باشد
    (پیش‌نمایش، دامنهٔ اصلی، تست). این‌جا فقط پیشوند اضافه می‌شود.
    """
    out: list[dict[str, Any]] = []
    for item in items:
        copy = dict(item)
        copy["image_url"] = _absolute(request, copy.get("image_url", ""))
        out.append(copy)
    return out


def get_leader_gallery(request: Any = None) -> list[dict[str, Any]]:
    """فهرست تصاویر فعال، مرتب بر اساس `order` (اول = تصویر پیش‌فرض باکس)."""
    items = cache_get_or_set_swr(
        domain=GALLERY_DOMAIN,
        key_suffix="leader",
        producer=_load_leader_rows,
    )
    return _absolutize(items, request)


def get_martyrs(request: Any = None) -> list[dict[str, Any]]:
    """فهرست شهدای فعال، مرتب بر اساس `order`."""
    items = cache_get_or_set_swr(
        domain=GALLERY_DOMAIN,
        key_suffix="martyrs",
        producer=_load_martyr_rows,
    )
    return _absolutize(items, request)

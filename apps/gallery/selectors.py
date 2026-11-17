"""استخراج دادهٔ گالری برای API عمومی — با الگوی کشِ خودِ پروژه.

── چرا همین الگوی کش؟ ───────────────────────────────────────────────────
پروژه یک لایهٔ کشِ واحد دارد (`apps.core.cache` + `cache_policy`) با
سیاستِ SWR، قفل ضد هجوم و **ابطال بر اساس دامنه**. اگر گالری کشِ جداگانهٔ
خودش را می‌ساخت، ادمین پس از آپلود تصویر تازه باید هم کش گالری را باطل
می‌کرد هم کش صفحهٔ اول را — و یکی از این دو همیشه فراموش می‌شد.

پس گالری یک دامنهٔ تازه در همان رجیستری است (`gallery`) و ابطالش با
همان `invalidate_domain_cache(domain="gallery")` انجام می‌شود — که در
سیگنال‌های `models.py` صدا زده می‌شود.
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
        "image_url": _absolute(request, row.image.url if row.image else ""),
        "title": row.title.strip(),
        "subtitle": (row.subtitle or "").strip(),
        "alt": (row.alt or row.title).strip(),
    }


def get_leader_gallery(request: Any = None) -> list[dict[str, Any]]:
    """تصاویر فعال رهبر انقلاب، به ترتیب `order`.

    نکتهٔ کارایی: `request` **داخل** کش نمی‌رود. تبدیل مسیر نسبی به مطلق
    پس از خواندن کش انجام می‌شود، وگرنه آدرس‌ها به میزبانِ اولین درخواست
    قفل می‌شدند (باگ کلاسیک وقتی سایت روی دو دامنه سرو شود).
    """

    def _produce() -> list[dict[str, Any]]:
        rows = LeaderPortrait.objects.filter(is_active=True).order_by("order", "-created_at", "-id")
        return [
            {
                "image_path": row.image.url if row.image else "",
                "alt": row.alt.strip(),
                "caption": (row.caption or "").strip(),
                "source": (row.source or "").strip(),
                "show_in_box": bool(row.show_in_box),
                "order": row.order,
            }
            for row in rows
        ]

    cached = cache_get_or_set_swr(
        domain=GALLERY_DOMAIN,
        key_suffix="leader",
        producer=_produce,
    )
    payload: list[dict[str, Any]] = []
    for row in cached:
        caption = row["caption"]
        payload.append(
            {
                "image_url": _absolute(request, row["image_path"]),
                "alt": row["alt"],
                "caption": caption,
                "caption_paragraphs": [p.strip() for p in caption.split("\n\n") if p.strip()],
                "source": row["source"],
                "show_in_box": row["show_in_box"],
                "order": row["order"],
            }
        )
    return payload


def get_martyrs(request: Any = None) -> list[dict[str, Any]]:
    """شهدای نوار بالای فوتر، به ترتیب `order`."""

    def _produce() -> list[dict[str, Any]]:
        rows = Martyr.objects.filter(is_active=True).order_by("order", "-created_at", "-id")
        return [
            {
                "image_path": row.image.url if row.image else "",
                "title": row.title.strip(),
                "subtitle": (row.subtitle or "").strip(),
                "alt": (row.alt or row.title).strip(),
            }
            for row in rows
        ]

    cached = cache_get_or_set_swr(
        domain=GALLERY_DOMAIN,
        key_suffix="martyrs",
        producer=_produce,
    )
    return [
        {
            "image_url": _absolute(request, row["image_path"]),
            "title": row["title"],
            "subtitle": row["subtitle"],
            "alt": row["alt"],
        }
        for row in cached
    ]

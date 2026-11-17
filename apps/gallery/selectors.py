"""خواندنِ گالری برای API — بدون هیچ نوشتنی، بدون هیچ کشِ دستیِ بی‌قاعده."""

from __future__ import annotations

from typing import Any

from django.http import HttpRequest

from apps.core.cache import cache_get_or_set_swr

from .models import LeaderPortrait, Martyr


def _absolute(request: HttpRequest | None, url: str) -> str:
    """آدرس مطلق تصویر.

    ⚠️ چرا مطلق و نه نسبی؟ فرانت در دامنهٔ دیگری (یا همان دامنه ولی مسیر
    دیگر) اجرا می‌شود و همین داده در پیش‌نمایش پیام‌رسان‌ها (بله/تلگرام) هم
    مصرف می‌شود. آدرس نسبی آن‌جا یعنی تصویرِ شکسته.

    اگر `request` نبود (مثلاً در پوستهٔ مدیریتی یا تستِ مستقیم)، به `MEDIA_URL`
    برمی‌گردیم — هرگز خطا نمی‌دهیم.
    """
    if not url:
        return ""
    if request is not None:
        return str(request.build_absolute_uri(url))
    return str(url)


def _leader_payload(item: LeaderPortrait, request: HttpRequest | None) -> dict[str, Any]:
    """یک قلم تصویر رهبر، آماده برای JSON."""
    return {
        "id": item.pk,
        "image_url": _absolute(request, item.image.url if item.image else ""),
        "alt": item.effective_alt(),
        "caption": str(item.caption or "").strip(),
        "caption_paragraphs": item.paragraphs(),
        "source": str(item.source or "").strip(),
        "show_in_box": bool(item.show_in_box),
        "order": int(item.display_order),
    }


def _martyr_payload(item: Martyr, request: HttpRequest | None) -> dict[str, Any]:
    """یک قلم شهید، آماده برای JSON."""
    return {
        "id": item.pk,
        "image_url": _absolute(request, item.image.url if item.image else ""),
        "title": str(item.title or "").strip(),
        "subtitle": str(item.subtitle or "").strip(),
        "alt": item.effective_alt(),
        "order": int(item.display_order),
    }


def _produce_leader(request: HttpRequest | None) -> list[dict[str, Any]]:
    """تولید فهرست تصاویر رهبر از پایگاه‌داده."""
    items = LeaderPortrait.all_objects.filter(is_active=True).order_by(
        "display_order", "created_at"
    )
    return [_leader_payload(item, request) for item in items]


def _produce_martyrs(request: HttpRequest | None) -> list[dict[str, Any]]:
    """تولید فهرست شهدا از پایگاه‌داده."""
    items = Martyr.all_objects.filter(is_active=True).order_by("display_order", "created_at")
    return [_martyr_payload(item, request) for item in items]


def get_leader_gallery(request: HttpRequest | None = None) -> list[dict[str, Any]]:
    """فهرست فعالِ تصاویر رهبر، مرتب، با آدرس مطلق.

    ⚠️ چرا از کش استفاده می‌کنیم ولی `request` را در کلید نمی‌گذاریم؟
    چون کلید کش نباید به هدر میزبان وابسته باشد (وگرنه هر میزبان یک
    نسخهٔ جدا می‌سازد و کش بی‌فایده می‌شود). به‌جایش فهرستِ «خام» کش
    می‌شود و آدرسِ مطلق در لحظهٔ پاسخ ساخته می‌شود. این کار هم کش را
    تک‌نسخه‌ای نگه می‌دارد، هم آدرس‌ها را درست.
    """
    raw = cache_get_or_set_swr(
        domain="gallery",
        key_suffix="leader",
        producer=lambda: _produce_leader(None),
    )
    return _with_absolute_urls(raw, request, media_field="image_url")


def get_martyrs(request: HttpRequest | None = None) -> list[dict[str, Any]]:
    """فهرست فعالِ شهدا، مرتب، با آدرس مطلق."""
    raw = cache_get_or_set_swr(
        domain="gallery",
        key_suffix="martyrs",
        producer=lambda: _produce_martyrs(None),
    )
    return _with_absolute_urls(raw, request, media_field="image_url")


def _with_absolute_urls(
    items: list[dict[str, Any]],
    request: HttpRequest | None,
    *,
    media_field: str,
) -> list[dict[str, Any]]:
    """جایگزینی آدرس‌های نسبیِ کش‌شده با آدرس‌های مطلقِ همین درخواست."""
    if request is None:
        return items
    out: list[dict[str, Any]] = []
    for item in items:
        clone = dict(item)
        clone[media_field] = _absolute(request, str(item.get(media_field) or ""))
        out.append(clone)
    return out


def get_gallery_box(request: HttpRequest | None = None) -> list[dict[str, Any]]:
    """فقط تصاویری که ادمین اجازهٔ نمایش در باکس صفحهٔ اول را داده است."""
    return [item for item in get_leader_gallery(request) if item.get("show_in_box")]

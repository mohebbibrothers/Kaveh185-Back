"""سرویس‌های نوشتن + ابطال کش گالری."""

from __future__ import annotations

from typing import Any

from apps.core.cache_invalidation import invalidate_domain_cache

GALLERY_DOMAIN = "gallery"


def invalidate_gallery(reason: str) -> None:
    """باطل‌کردن کش گالری با دلیلِ خوانا در لاگ."""
    invalidate_domain_cache(GALLERY_DOMAIN, reason=reason)


def move_item(*, item: Any, position: int, request: Any = None) -> Any:
    """جابه‌جایی یک قلم (تصویر رهبر یا شهید) و ابطال کش.

    تابع برای هر دو مدل کار می‌کند چون هر دو از `OrderedItem` ارث می‌برند؛
    یک نقطهٔ حقیقت برای ترتیب، یک نقطهٔ ابطال کش.
    """
    del request  # در نسخهٔ فعلی لاگ حسابرسی برای جابه‌جایی نگه نمی‌داریم
    item.move_to(int(position))
    invalidate_gallery(f"gallery.moved:{item.__class__.__name__}:{item.pk}")
    return item

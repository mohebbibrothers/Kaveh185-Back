"""سرویس جابه‌جایی ترتیب — برای دکمه‌های ↑/↓ در پنل ادمین.

── چرا سرویس و نه منطق در ویو؟ ──────────────────────────────────────────
جابه‌جاییِ ترتیب در دو مدل لازم است و منطقش دقیقاً یکی است. اگر در ویو
می‌نوشتیم، دو نسخهٔ کمی‌متفاوت می‌داشتیم که یکی از آن‌ها روزی `order` را
دوطبقه می‌کرد. این‌جا یک تابع، دو مصرف‌کننده.

── چرا بازنویسیِ کامل ترتیب و نه فقط swap دو عدد؟ ───────────────────────
چون دادهٔ موجود ممکن است `order`های تکراری داشته باشد (وقتی همه ۰ باشند،
هیچ جابه‌جایی‌ای معنا ندارد). با نرمال‌سازیِ کامل (۰،۱،۲،۳…) ترتیب همیشه
صریح و پایدار می‌شود — همان چیزی که ادمین انتظار دارد.
"""

from __future__ import annotations

from django.db import transaction

from .models import LeaderPortrait, Martyr, _invalidate_gallery

ITEM_TYPE = type[LeaderPortrait] | type[Martyr]


def move_item(model: ITEM_TYPE, pk: int, direction: str) -> bool:
    """جابه‌جایی ردیف به بالا/پایین و نرمال‌سازی کامل ترتیب.

    برگشت `False` یعنی جابه‌جایی ممکن نبود (ردیف اول/آخر یا شناسهٔ نامعتبر).
    """
    if direction not in ("up", "down"):
        return False

    with transaction.atomic():
        rows = list(model.objects.order_by("order", "created_at", "id"))
        index = next((i for i, row in enumerate(rows) if row.pk == pk), None)
        if index is None:
            return False
        target = index - 1 if direction == "up" else index + 1
        if target < 0 or target >= len(rows):
            return False

        rows[index], rows[target] = rows[target], rows[index]
        updates = [model(pk=row.pk, order=position) for position, row in enumerate(rows)]
        model.objects.bulk_update(updates, ["order"])

    # ⚠️ `bulk_update` سیگنال `post_save` نمی‌فرستد. بدونِ این فراخوانی،
    # کش گالری تا انقضای خودش ترتیب قدیمی را برمی‌گرداند و ادمین فکر
    # می‌کند «دکمه کار نکرد» — همان باگ کلاسیکی که فقط در محیط واقعی
    # دیده می‌شود، نه در تست.
    _invalidate_gallery()
    return True

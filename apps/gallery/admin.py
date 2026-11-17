"""پیکربندی پنل ادمین برای گالری — آپلود تصویرِ رهبر و شهدا.

── چرا `admin.py` این‌قدر «تزئین» دارد؟ ──────────────────────────────────
کاربر نهایی این پنل، ادمینِ حوزه است، نه برنامه‌نویس. سه چیز در پنل جنگو
معمولاً دردسر می‌سازد و این‌جا حل شده‌اند:

۱) **پیش‌نمایش تصویر.** بدون آن، ادمین بعد از آپلود نمی‌داند چه چیزی
   آپلود کرده و مجبور است سایت را رفرش کند. `image_preview` تصویر را
   در همان فرم نشان می‌دهد.
۲) **ستون‌های مفید در فهرست.** به‌جای `__str__`، تصویر بندانگشتی، ترتیب و
   وضعیت فعال — تا ادمین در یک نگاه بفهمد چه چیزی کجاست.
۳) **ویرایش دسته‌ای ترتیب.** `list_editable` روی `order` و `is_active`،
   تا برای جابه‌جایی ده شهید لازم نباشد ده فرم باز کند.
"""

from __future__ import annotations

from django.contrib import admin
from django.utils.html import format_html

from .models import LeaderPortrait, Martyr


@admin.register(LeaderPortrait)
class LeaderPortraitAdmin(admin.ModelAdmin):
    """مدیریت تصاویر رهبر انقلاب که در باکس «کتاب و کلام» نمایش داده می‌شوند."""

    list_display = ("thumb", "alt", "order", "show_in_box", "is_active", "created_at")
    list_display_links = ("thumb", "alt")
    list_editable = ("order", "show_in_box", "is_active")
    list_filter = ("is_active", "show_in_box")
    search_fields = ("alt", "caption", "source")
    readonly_fields = ("created_at", "updated_at", "image_preview")
    fieldsets = (
        ("تصویر", {"fields": ("image", "image_preview", "alt")}),
        ("متن", {"fields": ("caption", "source")}),
        ("نمایش", {"fields": ("order", "show_in_box", "is_active")}),
        ("زمان‌ها", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    @admin.display(description="پیش‌نمایش")
    def thumb(self, obj: LeaderPortrait) -> str:
        """بندانگشتی کوچک در فهرست."""
        if not obj.image:
            return "—"
        return format_html(
            '<img src="{}" alt="" style="height:42px;width:34px;object-fit:cover;'
            'border-radius:6px;box-shadow:0 1px 4px rgb(0 0 0/.25)" />',
            obj.image.url,
        )

    @admin.display(description="پیش‌نمایش تصویر")
    def image_preview(self, obj: LeaderPortrait) -> str:
        """پیش‌نمایش بزرگ‌تر در فرم ویرایش."""
        if not obj.image:
            return "پس از ذخیره، پیش‌نمایش این‌جا دیده می‌شود."
        return format_html(
            '<img src="{}" alt="" style="max-height:260px;border-radius:12px;'
            'box-shadow:0 6px 22px rgb(0 0 0/.22)" />',
            obj.image.url,
        )


@admin.register(Martyr)
class MartyrAdmin(admin.ModelAdmin):
    """مدیریت نوار شهدای بالای فوتر."""

    list_display = ("thumb", "title", "subtitle", "order", "is_active", "created_at")
    list_display_links = ("thumb", "title")
    list_editable = ("order", "is_active")
    list_filter = ("is_active",)
    search_fields = ("title", "subtitle", "alt")
    readonly_fields = ("created_at", "updated_at", "image_preview")
    fieldsets = (
        ("تصویر", {"fields": ("image", "image_preview", "alt")}),
        ("متن", {"fields": ("title", "subtitle")}),
        ("نمایش", {"fields": ("order", "is_active")}),
        ("زمان‌ها", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    @admin.display(description="پیش‌نمایش")
    def thumb(self, obj: Martyr) -> str:
        """بندانگشتی گِرد در فهرست."""
        if not obj.image:
            return "—"
        return format_html(
            '<img src="{}" alt="" style="height:40px;width:40px;object-fit:cover;'
            'border-radius:999px;box-shadow:0 1px 4px rgb(0 0 0/.25)" />',
            obj.image.url,
        )

    @admin.display(description="پیش‌نمایش تصویر")
    def image_preview(self, obj: Martyr) -> str:
        """پیش‌نمایش گِرد در فرم ویرایش."""
        if not obj.image:
            return "پس از ذخیره، پیش‌نمایش این‌جا دیده می‌شود."
        return format_html(
            '<img src="{}" alt="" style="height:150px;width:150px;object-fit:cover;'
            'border-radius:999px;box-shadow:0 6px 22px rgb(0 0 0/.22)" />',
            obj.image.url,
        )

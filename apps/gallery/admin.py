"""پیکربندی پنل ادمین گالری.

── اصل طراحی: ادمین نباید کد یا نسبت تصویر بداند ─────────────────────────
فرم فقط چیزی را می‌پرسد که واقعاً از ادمین می‌آید (تصویر، عنوان، کلام).
«ترتیب» عدد نیست که ادمین حدس بزند: با دو دکمهٔ بالا/پایین جابه‌جا می‌شود.
پیش‌نمایش تصویر داخل خود فهرست می‌آید تا ادمین ناچار نباشد برای دیدن
نتیجه، سایت را باز کند.
"""

from __future__ import annotations

from typing import Any

from django.contrib import admin, messages
from django.http import HttpRequest, HttpResponseRedirect
from django.urls import path, reverse
from django.utils.html import format_html

from .models import LeaderPortrait, Martyr
from .services import move_item


class OrderedThumbMixin(admin.ModelAdmin):  # type: ignore[type-arg]
    """پیش‌نمایش تصویر + دو دکمهٔ جابه‌جایی ترتیب — مشترک بین دو مدل."""

    list_per_page = 40
    readonly_fields = ("preview", "created_at", "updated_at")

    @admin.display(description="پیش‌نمایش")
    def preview(self, obj: LeaderPortrait | Martyr) -> str:
        """تصویر کوچک با نسبت درست — بدون باز کردن صفحهٔ ویرایش."""
        if not obj.image:
            return "—"
        radius = "50%" if isinstance(obj, Martyr) else "10px"
        return format_html(
            '<img src="{}" alt="" style="height:64px;width:{};object-fit:cover;'
            'border-radius:{};border:1px solid #d7dbe4" />',
            obj.image.url,
            "64px" if isinstance(obj, Martyr) else "52px",
            radius,
        )

    def get_urls(self) -> list[Any]:
        """دو مسیر کوچک برای جابه‌جایی؛ بدون جاوااسکریپت و بدون POST دستی."""
        info = self.model._meta.app_label, self.model._meta.model_name
        custom = [
            path(
                "<int:pk>/move/<str:direction>/",
                self.admin_site.admin_view(self._move_view),
                name=f"{info[0]}_{info[1]}_move",
            ),
        ]
        return custom + super().get_urls()

    def _move_view(self, request: HttpRequest, pk: int, direction: str) -> HttpResponseRedirect:
        """جابه‌جایی یک ردیف و بازگشت به همان فهرست."""
        moved = move_item(self.model, pk, direction)
        if moved:
            self.message_user(request, "ترتیب نمایش به‌روزرسانی شد.", messages.SUCCESS)
        else:
            self.message_user(request, "جابه‌جایی ممکن نشد.", messages.WARNING)
        return HttpResponseRedirect(
            reverse(f"admin:{self.model._meta.app_label}_{self.model._meta.model_name}_changelist")
        )


class LeaderPortraitAdmin(OrderedThumbMixin):
    """تصاویر رهبر انقلاب — با کلام و برچسب منبع."""

    list_display = ("preview", "alt", "order", "show_in_box", "is_active", "move_buttons")
    list_display_links = ("alt",)
    list_editable = ("is_active", "show_in_box")
    list_filter = ("is_active", "show_in_box")
    search_fields = ("alt", "caption", "source")
    fieldsets = (
        ("تصویر", {"fields": ("image", "preview", "alt")}),
        (
            "کلام همراه",
            {
                "fields": ("caption", "source"),
                "description": "برای جدا کردن بندها یک خط خالی بین دو بند بگذارید. "
                "اگر خالی بماند، کلامِ پیش‌فرضِ سایت نمایش داده می‌شود.",
            },
        ),
        ("نمایش", {"fields": ("order", "show_in_box", "is_active")}),
        ("زمان", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    @admin.display(description="ترتیب")
    def move_buttons(self, obj: LeaderPortrait) -> str:
        """دو دکمهٔ بالا/پایین در همان سطر فهرست."""
        return _move_buttons_html(self.model, obj.pk)


class MartyrAdmin(OrderedThumbMixin):
    """نوار شهدای بالای فوتر."""

    list_display = ("preview", "title", "subtitle", "order", "is_active", "move_buttons")
    list_display_links = ("title",)
    list_editable = ("is_active",)
    list_filter = ("is_active",)
    search_fields = ("title", "subtitle")
    fieldsets = (
        ("تصویر و عنوان", {"fields": ("image", "preview", "title", "subtitle", "alt")}),
        ("نمایش", {"fields": ("order", "is_active")}),
        ("زمان", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    @admin.display(description="ترتیب")
    def move_buttons(self, obj: Martyr) -> str:
        """دو دکمهٔ بالا/پایین در همان سطر فهرست."""
        return _move_buttons_html(self.model, obj.pk)


def _move_buttons_html(model: type[LeaderPortrait] | type[Martyr], pk: int) -> str:
    """HTML دو دکمهٔ ↑/↓ — مسیرها با `reverse` ساخته می‌شوند، نه رشتهٔ دستی."""
    info = model._meta.app_label, model._meta.model_name
    up = reverse(f"admin:{info[0]}_{info[1]}_move", args=[pk, "up"])
    down = reverse(f"admin:{info[0]}_{info[1]}_move", args=[pk, "down"])
    style = (
        "display:inline-flex;align-items:center;justify-content:center;"
        "height:22px;width:22px;border-radius:6px;border:1px solid #c9cedb;"
        "background:#fff;color:#334;text-decoration:none;font-size:12px"
    )
    return format_html(
        '<span style="display:inline-flex;gap:4px">'
        '<a href="{}" style="{}" title="بالا">▲</a>'
        '<a href="{}" style="{}" title="پایین">▼</a></span>',
        up,
        style,
        down,
        style,
    )


admin.site.register(LeaderPortrait, LeaderPortraitAdmin)
admin.site.register(Martyr, MartyrAdmin)

"""پنل ادمین گالری محتوایی — دو بخش، هر کدام سه کار: دیدن، ترتیب‌دادن، افزودن.

طراحی فرم بر پایهٔ یک قاعده: **ادمین نباید هیچ عددی تایپ کند.** ترتیب با
دو دکمهٔ ▲▼ عوض می‌شود؛ بقیهٔ فیلدها یا خودکارند یا اختیاری و در بخش
تاشو جمع شده‌اند. تصویر در فهرست، پیش‌نمایش گرد دارد تا ادمین بی‌درنگ
ببیند چه چیزی روی سایت می‌رود.
"""

from __future__ import annotations

from typing import Any

from django.contrib import admin, messages
from django.db.models import QuerySet
from django.http import HttpRequest, HttpResponseRedirect
from django.urls import path, reverse
from django.utils.html import format_html

from .models import LeaderPortrait, Martyr
from .services import invalidate_gallery, move_item


class OrderedAdminMixin(admin.ModelAdmin):
    """رفتار مشترک دو بخش: ▲▼، پیش‌نمایش، و ابطال کش پس از هر تغییر."""

    list_per_page = 60

    # ── ستون‌های مشترک ─────────────────────────────────────────────────────
    @admin.display(description="ترتیب")
    def order_badge(self, obj: Any) -> str:
        """نمایش ترتیب به‌صورت نشانِ کوچک."""
        return format_html(
            '<span style="display:inline-block;min-width:2em;text-align:center;'
            'font-variant-numeric:tabular-nums;font-weight:700;color:#475569">{}</span>',
            obj.display_order,
        )

    @admin.display(description="جابه‌جایی")
    def move_buttons(self, obj: Any) -> str:
        """دو دکمهٔ ▲▼ بدون رفرش صفحهٔ فهرست."""
        up = reverse(
            f"admin:{obj._meta.app_label}_{obj._meta.model_name}_move", args=[obj.pk, "up"]
        )
        down = reverse(
            f"admin:{obj._meta.app_label}_{obj._meta.model_name}_move", args=[obj.pk, "down"]
        )
        return format_html(
            '<span style="display:inline-flex;gap:4px">'
            '<a href="{}" title="بالا" style="{}">▲</a>'
            '<a href="{}" title="پایین" style="{}">▼</a>'
            "</span>",
            up,
            _BTN,
            down,
            _BTN,
        )

    # ── مسیرهای اختصاصی ────────────────────────────────────────────────────
    def get_urls(self) -> list[Any]:
        """افزودن مسیر جابه‌جایی به مسیرهای پیش‌فرض ادمین."""
        custom = [
            path(
                "<int:pk>/move/<str:direction>/",
                self.admin_site.admin_view(self.move_view),
                name=f"{self.model._meta.app_label}_{self.model._meta.model_name}_move",
            )
        ]
        return custom + super().get_urls()

    def move_view(self, request: HttpRequest, pk: int, direction: str) -> HttpResponseRedirect:
        """جابه‌جایی یک قلم یک پله بالا یا پایین و بازگشت به همان فهرست."""
        obj = self.model.all_objects.get(pk=pk)
        delta = -1 if direction == "up" else 1
        move_item(item=obj, position=max(1, int(obj.display_order) + delta), request=request)
        self.message_user(request, "ترتیب نمایش به‌روزرسانی شد.", messages.SUCCESS)
        return HttpResponseRedirect(
            reverse(f"admin:{self.model._meta.app_label}_{self.model._meta.model_name}_changelist")
        )

    def save_model(self, request: HttpRequest, obj: Any, form: Any, change: bool) -> None:
        """ذخیره + ابطال کش (تا ادمین بلافاصله نتیجه را روی سایت ببیند)."""
        super().save_model(request, obj, form, change)
        invalidate_gallery(f"gallery.saved:{obj._meta.model_name}:{obj.pk}")

    def delete_model(self, request: HttpRequest, obj: Any) -> None:
        """حذف + ابطال کش."""
        super().delete_model(request, obj)
        invalidate_gallery(f"gallery.deleted:{obj._meta.model_name}:{obj.pk}")

    def delete_queryset(self, request: HttpRequest, queryset: QuerySet[Any]) -> None:
        """حذف گروهی + ابطال کش."""
        super().delete_queryset(request, queryset)
        invalidate_gallery("gallery.bulk_deleted")


_BTN = (
    "display:inline-grid;place-items:center;width:26px;height:26px;border-radius:6px;"
    "border:1px solid #cbd5e1;background:#f8fafc;color:#0f172a;text-decoration:none;"
    "font-size:11px;line-height:1"
)


@admin.register(LeaderPortrait)
class LeaderPortraitAdmin(OrderedAdminMixin):
    """مدیریت تصاویر رهبر انقلاب در پنل ادمین."""

    list_display = (
        "thumb",
        "preview_caption",
        "source_cell",
        "show_in_box",
        "is_active",
        "order_badge",
        "move_buttons",
    )
    # عرض ستون‌ها: بدون این، متنِ کلام ستونِ «منبع» را می‌بلعد و فهرست
    # ناخوانا می‌شود (در بازبینیِ واقعیِ پنل دیده شد).
    list_display_links = ("thumb", "preview_caption")
    list_editable = ("is_active",)
    list_filter = ("is_active", "show_in_box")
    search_fields = ("caption", "alt", "source")
    readonly_fields = ("thumb_large", "order_badge")

    fieldsets = (
        (
            "تصویر و کلام",
            {
                "fields": ("image", "thumb_large", "caption", "source"),
                "description": (
                    "این متن دقیقاً کنار همین تصویر در باکس «کتاب و کلام» صفحهٔ اول "
                    "نمایش داده می‌شود. اگر چند پاراگراف می‌خواهید، بین‌شان یک خط خالی بگذارید."
                ),
            },
        ),
        (
            "نمایش",
            {
                "fields": ("alt", "show_in_box", "is_active"),
                "description": (
                    "اگر «متن جانشین» را خالی بگذارید، از ابتدای کلام ساخته می‌شود. "
                    "با خاموش‌کردن «در باکس دیده شود»، تصویر در گالری می‌ماند ولی صفحهٔ اول نشانش نمی‌دهد."
                ),
            },
        ),
        ("ترتیب", {"fields": ("order_badge",), "classes": ("collapse",)}),
    )

    @admin.display(description="تصویر")
    def thumb(self, obj: LeaderPortrait) -> str:
        """پیش‌نمایش کوچک و گرد در فهرست."""
        if not obj.image:
            return "—"
        return format_html(
            '<img src="{}" alt="" style="width:42px;height:42px;object-fit:cover;'
            'border-radius:9999px;border:1px solid #e2e8f0" />',
            obj.image.url,
        )

    @admin.display(description="پیش‌نمایش در فرم")
    def thumb_large(self, obj: LeaderPortrait) -> str:
        """پیش‌نمایش بزرگ در فرم ویرایش (تا ادمین ببیند چه گذاشته)."""
        if not obj or not getattr(obj, "image", None):
            return "پس از ذخیره، پیش‌نمایش این‌جا دیده می‌شود."
        return format_html(
            '<img src="{}" alt="" style="max-width:220px;border-radius:14px;'
            'border:1px solid #e2e8f0" />',
            obj.image.url,
        )

    @admin.display(description="کلام")
    def preview_caption(self, obj: LeaderPortrait) -> str:
        """۴۵ کاراکتر اول کلام — کوتاه، با کوتاه‌کردنِ امن در قالب."""
        text = str(obj.caption or "").strip().replace("\n", " ")
        short = (text[:45] + "…") if len(text) > 45 else (text or "—")
        return format_html('<span style="display:inline-block;max-width:236px">{}</span>', short)

    @admin.display(description="منبع")
    def source_cell(self, obj: LeaderPortrait) -> str:
        """منبع، کوتاه‌شده."""
        text = str(obj.source or "").strip()
        short = (text[:34] + "…") if len(text) > 34 else (text or "—")
        return format_html('<span style="display:inline-block;max-width:170px">{}</span>', short)


@admin.register(Martyr)
class MartyrAdmin(OrderedAdminMixin):
    """مدیریت شهدای نوار گردان بالای فوتر."""

    list_display = ("thumb", "title", "subtitle", "is_active", "order_badge", "move_buttons")
    list_display_links = ("thumb", "title")
    list_editable = ("is_active",)
    list_filter = ("is_active",)
    search_fields = ("title", "subtitle", "alt")
    readonly_fields = ("thumb_large", "order_badge")

    fieldsets = (
        (
            "شهید",
            {
                "fields": ("image", "thumb_large", "title", "subtitle"),
                "description": (
                    "تصویر مربع (حداقل ۳۲۰×۳۲۰) و چهره در مرکز. عنوان زیر تصویرِ گرد "
                    "نمایش داده می‌شود؛ کوتاه بماند. با ۶ شهید یا بیشتر، نوار خودش می‌گردد."
                ),
            },
        ),
        (
            "نمایش",
            {
                "fields": ("alt", "is_active"),
                "description": "متن جانشین خالی ⇒ از عنوان ساخته می‌شود.",
            },
        ),
        ("ترتیب", {"fields": ("order_badge",), "classes": ("collapse",)}),
    )

    @admin.display(description="تصویر")
    def thumb(self, obj: Martyr) -> str:
        """پیش‌نمایش گردِ کوچک."""
        if not obj.image:
            return "—"
        return format_html(
            '<img src="{}" alt="" style="width:42px;height:42px;object-fit:cover;'
            'border-radius:9999px;border:1px solid #e2e8f0" />',
            obj.image.url,
        )

    @admin.display(description="پیش‌نمایش در فرم")
    def thumb_large(self, obj: Martyr) -> str:
        """پیش‌نمایش بزرگِ گرد در فرم."""
        if not obj or not getattr(obj, "image", None):
            return "پس از ذخیره، پیش‌نمایش این‌جا دیده می‌شود."
        return format_html(
            '<img src="{}" alt="" style="width:140px;height:140px;object-fit:cover;'
            'border-radius:9999px;border:3px solid #e2e8f0" />',
            obj.image.url,
        )

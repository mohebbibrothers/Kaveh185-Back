"""پیکربندی پنل ادمین جنگو برای مدیریت مساجد حوزه ۱۸۵ شهید کاوه.

چرا این فایل این‌قدر «سخت‌گیر» است؟ چون پنل ادمین تنها راه ورود دادهٔ
واقعی به سامانه است و هر فیلد اضافی، یک بار تصمیم‌گیری روی دوش ادمین
می‌گذارد. فرم این‌جا فقط چیزی را می‌پرسد که واقعاً از ادمین می‌آید:

  • **کد مسجد** خودکار ساخته می‌شود (`MSQ-18`) — قابل ویرایش ولی اختیاری.
  • **تعداد ثبت‌نام‌کنندگان و آزمون‌دهندگان** شمارنده‌اند، نه ورودی. از
    ثبت‌نام‌ها و کارنامه‌ها شمرده می‌شوند و `editable=False` هستند تا
    هیچ‌وقت دستی نوشته نشوند.
  • **ترتیب نمایش** خودکار پر می‌شود و با دو دکمهٔ «بالا/پایین» جابه‌جا
    می‌شود — بدون تایپ عدد.
  • **محله، نشانی، امام جماعت، فرمانده، تلفن، هدف‌گذاری** همه اختیاری‌اند
    و در بخش تاشوی «اطلاعات تکمیلی» جمع شده‌اند تا فرم اول شلوغ نباشد.
"""

from __future__ import annotations

from typing import Any

from django.contrib import admin, messages
from django.db.models import QuerySet
from django.http import HttpRequest, HttpResponseRedirect
from django.urls import path, reverse
from django.utils.html import format_html

from .models import Mosque
from .services import move_mosque


@admin.register(Mosque)
class MosqueAdmin(admin.ModelAdmin):
    """مدیریت مساجد در پنل ادمین جنگو."""

    list_display = (
        "order_badge",
        "code",
        "name",
        "stats_cell",
        "is_active",
        "move_buttons",
    )
    list_display_links = ("code", "name")
    list_editable = ("is_active",)
    list_filter = ("is_active",)
    search_fields = ("code", "name", "neighborhood", "imam_name", "commander_name")
    ordering = ("display_order", "id")
    readonly_fields = ("code_display", "stats_display", "created_at_display")
    actions = ("action_move_up", "action_move_down", "action_activate", "action_deactivate")

    # ── فرم ویرایش ────────────────────────────────────────────────────────
    fieldsets = (
        (
            "مسجد",
            {
                "fields": ("name", "is_active"),
                "description": "فقط نام مسجد لازم است. بقیهٔ فیلدها اختیاری‌اند.",
            },
        ),
        (
            "شناسه و ترتیب",
            {
                "fields": ("code", "code_display", "display_order"),
                "description": (
                    "کد و ترتیب خودکار پر می‌شوند؛ اگر خالی بگذارید سامانه "
                    "خودش می‌سازد. برای جابه‌جایی سریع، از دکمه‌های ↑ ↓ در "
                    "فهرست مساجد استفاده کنید."
                ),
            },
        ),
        (
            "اطلاعات تکمیلی (اختیاری)",
            {
                "fields": (
                    "neighborhood",
                    "address",
                    "imam_name",
                    "commander_name",
                    "contact_phone",
                    "target_participants",
                ),
                "classes": ("collapse",),
                "description": "این بخش برای گزارش‌های داخلی است و در صفحهٔ عمومی سایت نمایش داده نمی‌شود.",
            },
        ),
        (
            "آمار (فقط خواندنی)",
            {
                "fields": ("stats_display", "created_at_display"),
                "description": (
                    "این اعداد از ثبت‌نام‌ها و کارنامه‌های واقعی شمرده می‌شوند و "
                    "قابل ویرایش دستی نیستند."
                ),
            },
        ),
    )

    # ── نمایش ────────────────────────────────────────────────────────────
    @admin.display(description="ترتیب", ordering="display_order")
    def order_badge(self, obj: Mosque) -> str:
        """نشان ترتیب نمایش — عدد کوچک و خوانا در ابتدای ردیف."""
        return format_html(
            '<span style="display:inline-grid;place-items:center;min-width:26px;height:24px;'
            "padding:0 6px;border-radius:7px;background:#f1ede4;color:#5a5142;"
            'font-weight:700;font-variant-numeric:tabular-nums">{}</span>',
            obj.display_order,
        )

    @admin.display(description="مشارکت / ثبت‌نام")
    def stats_cell(self, obj: Mosque) -> str:
        """دو شمارندهٔ واقعی در یک سلول خوانا."""
        return format_html(
            '<span style="font-variant-numeric:tabular-nums">{} <span style="opacity:.55">/</span> {}</span>',
            obj.completed_exam_count,
            obj.registered_count,
        )

    @admin.display(description="کد فعلی")
    def code_display(self, obj: Mosque) -> str:
        """کد فعلی مسجد؛ برای مسجد تازه‌ساخته‌نشده راهنما نشان می‌دهد."""
        if obj is None or not obj.pk:
            return "پس از ذخیره، خودکار ساخته می‌شود."
        return obj.code

    @admin.display(description="آمار")
    def stats_display(self, obj: Mosque) -> str:
        """خلاصهٔ آمار واقعی مسجد."""
        if obj is None or not obj.pk:
            return "—"
        return format_html(
            "ثبت‌نام: <b>{}</b> · تکمیل آزمون: <b>{}</b> · هدف: <b>{}</b>",
            obj.registered_count,
            obj.completed_exam_count,
            obj.target_participants,
        )

    @admin.display(description="تاریخ ایجاد")
    def created_at_display(self, obj: Mosque) -> str:
        """تاریخ ایجاد مسجد."""
        if obj is None or not obj.pk:
            return "—"
        return obj.created_at.strftime("%Y-%m-%d %H:%M")

    # ── جابه‌جایی سریع ───────────────────────────────────────────────────
    @admin.display(description="جابه‌جایی")
    def move_buttons(self, obj: Mosque) -> str:
        """دو دکمهٔ کوچک بالا/پایین برای تغییر ترتیب بدون تایپ عدد."""
        if obj is None or not obj.pk:
            return "—"
        up_url = reverse("admin:mosques_mosque_move", args=[obj.pk, "up"])
        down_url = reverse("admin:mosques_mosque_move", args=[obj.pk, "down"])
        base = (
            "display:inline-grid;place-items:center;width:26px;height:24px;"
            "border-radius:7px;border:1px solid #d8d2c4;background:#fff;"
            "color:#4a4438;text-decoration:none;font-weight:700;line-height:1"
        )
        return format_html(
            '<span style="display:inline-flex;gap:4px">'
            '<a href="{}" style="{}" title="بالا">&uarr;</a>'
            '<a href="{}" style="{}" title="پایین">&darr;</a>'
            "</span>",
            up_url,
            base,
            down_url,
            base,
        )

    # ── مسیر جابه‌جایی ───────────────────────────────────────────────────
    def get_urls(self) -> list[Any]:
        """افزودن مسیر `<id>/move/<up|down>/` زیر همان قفل ادمین."""
        custom = [
            path(
                "<int:mosque_id>/move/<str:direction>/",
                self.admin_site.admin_view(self.move_view),
                name="mosques_mosque_move",
            )
        ]
        return custom + super().get_urls()

    def move_view(
        self, request: HttpRequest, mosque_id: int, direction: str
    ) -> HttpResponseRedirect:
        """جابه‌جایی یک مسجد از روی دکمه‌های ↑ ↓ در فهرست."""
        mosque = Mosque.all_objects.filter(pk=mosque_id).first()
        if mosque is not None and direction in ("up", "down"):
            delta = -1 if direction == "up" else 1
            move_mosque(
                mosque=mosque,
                position=max(1, mosque.display_order + delta),
                request=request,
            )
        return HttpResponseRedirect(reverse("admin:mosques_mosque_changelist"))

    # ── اقدام‌های گروهی ──────────────────────────────────────────────────
    @admin.action(description="▲ یک پله بالا")
    def action_move_up(self, request: HttpRequest, queryset: QuerySet[Mosque]) -> None:
        """جابه‌جایی مساجد انتخاب‌شده یک پله به بالا."""
        for mosque in queryset.order_by("display_order"):
            move_mosque(mosque=mosque, position=max(1, mosque.display_order - 1), request=request)
        self.message_user(request, "ترتیب مساجد به‌روز شد.", messages.SUCCESS)

    @admin.action(description="▼ یک پله پایین")
    def action_move_down(self, request: HttpRequest, queryset: QuerySet[Mosque]) -> None:
        """جابه‌جایی مساجد انتخاب‌شده یک پله به پایین."""
        for mosque in queryset.order_by("-display_order"):
            move_mosque(mosque=mosque, position=mosque.display_order + 1, request=request)
        self.message_user(request, "ترتیب مساجد به‌روز شد.", messages.SUCCESS)

    @admin.action(description="فعال کردن")
    def action_activate(self, request: HttpRequest, queryset: QuerySet[Mosque]) -> None:
        """فعال کردن مساجد انتخاب‌شده."""
        count = queryset.update(is_active=True)
        self.message_user(request, f"{count} مسجد فعال شد.", messages.SUCCESS)

    @admin.action(description="غیرفعال کردن")
    def action_deactivate(self, request: HttpRequest, queryset: QuerySet[Mosque]) -> None:
        """غیرفعال کردن مساجد انتخاب‌شده."""
        count = queryset.update(is_active=False)
        self.message_user(request, f"{count} مسجد غیرفعال شد.", messages.SUCCESS)

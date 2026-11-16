"""مدل دادهٔ مساجد تحت پوشش حوزه مقاومت بسیج ۱۸۵ شهید کاوه."""

from __future__ import annotations

from typing import Any

from django.db import models

from apps.core.models import BaseModel


class Mosque(BaseModel):
    """مدل مسجد برای انتخاب در ثبت‌نام و رتبه‌بندی لحظه‌ای مشارکت در آزمون."""

    code = models.CharField(
        max_length=32,
        unique=True,
        db_index=True,
        blank=True,
        verbose_name="کد مسجد",
        help_text="خودکار ساخته می‌شود (مثل MSQ-18). فقط اگر لازم است می‌توانید عوضش کنید.",
    )
    name = models.CharField(
        max_length=160,
        unique=True,
        db_index=True,
        verbose_name="نام مسجد",
    )
    neighborhood = models.CharField(
        max_length=160,
        blank=True,
        default="",
        verbose_name="محله / محدوده (اختیاری)",
    )
    address = models.CharField(
        max_length=300,
        blank=True,
        default="",
        verbose_name="نشانی",
    )
    imam_name = models.CharField(
        max_length=120,
        blank=True,
        default="",
        verbose_name="نام امام جماعت",
    )
    commander_name = models.CharField(
        max_length=120,
        blank=True,
        default="",
        verbose_name="نام فرمانده پایگاه بسیج",
    )
    contact_phone = models.CharField(
        max_length=24,
        blank=True,
        default="",
        verbose_name="تلفن هماهنگی",
    )
    target_participants = models.PositiveIntegerField(
        default=500,
        verbose_name="هدف‌گذاری تعداد مشارکت (اختیاری)",
    )
    display_order = models.PositiveIntegerField(
        default=0,
        db_index=True,
        verbose_name="ترتیب نمایش",
        help_text="اگر صفر بماند، خودکار بر اساس ترتیب افزودن پر می‌شود.",
    )
    registered_count = models.PositiveIntegerField(
        default=0,
        db_index=True,
        editable=False,
        verbose_name="تعداد ثبت‌نام‌کنندگان",
        help_text="از روی ثبت‌نام‌ها شمارش می‌شود؛ دستی قابل تغییر نیست.",
    )
    completed_exam_count = models.PositiveIntegerField(
        default=0,
        db_index=True,
        editable=False,
        verbose_name="تعداد تکمیل‌کنندگان آزمون",
        help_text="از روی کارنامه‌ها شمارش می‌شود؛ دستی قابل تغییر نیست.",
    )

    class Meta:
        verbose_name = "مسجد"
        verbose_name_plural = "مساجد"
        ordering = ["display_order", "name"]
        indexes = [
            models.Index(
                fields=["is_active", "-completed_exam_count", "display_order"],
                name="mosque_leaderboard_idx",
            ),
        ]

    def __str__(self) -> str:
        """نمایش خوانای نام و کد مسجد."""
        return f"{self.name} ({self.code})" if self.code else str(self.name)

    # ── خودکارسازی ────────────────────────────────────────────────────────
    def save(self, *args: Any, **kwargs: Any) -> None:
        """کد و ترتیب نمایش را در صورت خالی بودن، خودکار پر می‌کند.

        چرا در `save` و نه در فرم ادمین؟ چون دو راه ورود داده داریم: پنل
        جنگو و API مدیریتی. اگر منطق فقط در فرم باشد، درج از API کد خالی
        می‌گذارد و یکتایی می‌شکند. این‌جا یک نقطهٔ حقیقت است.

        `display_order = 0` یعنی «من خودم ترتیب را نگفتم». در این حالت
        مسجد به انتهای فهرست می‌رود (`max + 1`)، که همان ترتیب طبیعی
        افزودن است. ادمین هر زمان می‌تواند دستی جابه‌جا کند.
        """
        if not self.code:
            self.code = self._next_code()
        if not self.display_order:
            self.display_order = self._next_display_order()
        super().save(*args, **kwargs)

    @classmethod
    def _next_code(cls) -> str:
        """کد بعدی به شکل `MSQ-NN`، بر پایهٔ بیشترین عدد موجود."""
        biggest = 0
        for existing in cls.all_objects.values_list("code", flat=True):
            suffix = str(existing).rpartition("-")[2]
            if suffix.isdigit():
                biggest = max(biggest, int(suffix))
        # حلقهٔ ایمنی: اگر کد ساخته‌شده به هر دلیل گرفته بود، جلو برو.
        candidate = biggest + 1
        while cls.all_objects.filter(code=f"MSQ-{candidate:02d}").exists():
            candidate += 1
        return f"MSQ-{candidate:02d}"

    @classmethod
    def _next_display_order(cls) -> int:
        """ترتیب بعدی = بیشترین ترتیب فعلی + ۱."""
        biggest = cls.all_objects.aggregate(models.Max("display_order"))["display_order__max"]
        return int(biggest or 0) + 1

    def move_to(self, position: int) -> None:
        """جابه‌جایی دستی این مسجد به یک جایگاه مشخص و بازچینش بقیه.

        چرا بازچینش؟ اگر فقط عدد یک مسجد عوض شود، اعداد تکراری می‌شوند و
        ترتیب صفحه به ترتیب تصادفی دیتابیس می‌افتد. بعد از هر جابه‌جایی،
        کل فهرست از ۱ تا n بازنویسی می‌شود تا همیشه یک ترتیب تمیز و بی‌شکاف
        داشته باشیم.
        """
        ordered = list(Mosque.all_objects.order_by("display_order", "id"))
        ordered = [m for m in ordered if m.pk != self.pk]
        target = max(0, min(position - 1, len(ordered)))
        ordered.insert(target, self)
        for index, mosque in enumerate(ordered, start=1):
            if mosque.display_order != index:
                Mosque.all_objects.filter(pk=mosque.pk).update(display_order=index)
        self.display_order = target + 1

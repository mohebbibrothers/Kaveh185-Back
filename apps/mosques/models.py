"""مدل دادهٔ مساجد تحت پوشش حوزه مقاومت بسیج ۱۸۵ شهید کاوه."""

from __future__ import annotations

from django.db import models

from apps.core.models import BaseModel


class Mosque(BaseModel):
    """مدل مسجد برای انتخاب در ثبت‌نام و رتبه‌بندی لحظه‌ای مشارکت در آزمون."""

    code = models.CharField(
        max_length=32,
        unique=True,
        db_index=True,
        verbose_name="کد مسجد",
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
        verbose_name="محله / محدوده",
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
        verbose_name="هدف‌گذاری تعداد مشارکت",
    )
    display_order = models.PositiveSmallIntegerField(
        default=1,
        db_index=True,
        verbose_name="ترتیب نمایش",
    )
    registered_count = models.PositiveIntegerField(
        default=0,
        db_index=True,
        verbose_name="تعداد ثبت‌نام‌کنندگان",
    )
    completed_exam_count = models.PositiveIntegerField(
        default=0,
        db_index=True,
        verbose_name="تعداد تکمیل‌کنندگان آزمون",
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
        return f"{self.name} ({self.code})"

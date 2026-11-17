"""مدل‌های گالری محتوایی کاوه ۱۸۵."""

from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.text import slugify

from apps.core.models import BaseModel


class OrderedItem(BaseModel):
    """پایهٔ مشترک اقلامِ مرتب — یک نقطهٔ حقیقت برای «ترتیب».

    چرا کلاس پایه؟ چون هم تصاویر رهبر و هم شهدا به «جابه‌جایی بی‌شکاف»
    نیاز دارند و اگر منطق در دو جا تکرار شود، دیر یا زود یکی از دیگری
    عقب می‌ماند (همان اتفاقی که در نسخهٔ اول اپ مساجد افتاد).

    قاعده: `display_order = 0` یعنی «من ترتیب را نگفتم» → انتهای فهرست.
    هرگز `0` به‌عنوان ترتیبِ واقعی ذخیره نمی‌شود.
    """

    display_order = models.PositiveIntegerField(
        default=0,
        db_index=True,
        verbose_name="ترتیب نمایش",
        help_text="خودکار پر می‌شود. برای جابه‌جایی از دکمه‌های ▲▼ در فهرست استفاده کنید.",
    )
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        verbose_name="فعال",
        help_text="اگر خاموش شود، در سایت دیده نمی‌شود ولی داده حفظ می‌شود.",
    )

    class Meta:
        abstract = True
        ordering = ["display_order", "created_at"]

    # ── ترتیب ──────────────────────────────────────────────────────────────
    @classmethod
    def _next_display_order(cls) -> int:
        """ترتیب بعدی = بیشترین ترتیب موجود + ۱."""
        biggest = cls.all_objects.aggregate(models.Max("display_order"))["display_order__max"]
        return int(biggest or 0) + 1

    def save(self, *args: Any, **kwargs: Any) -> None:
        """پرکردن خودکار ترتیب در صورت خالی بودن."""
        if not self.display_order:
            self.display_order = self._next_display_order()
        super().save(*args, **kwargs)

    def move_to(self, position: int) -> None:
        """جابه‌جایی به موقعیت دلخواه با بازچینش بی‌شکاف بقیهٔ اقلام."""
        siblings = list(type(self).all_objects.order_by("display_order", "created_at"))
        me = next((s for s in siblings if s.pk == self.pk), None)
        if me is None:
            return
        siblings.remove(me)
        index = max(0, min(len(siblings), int(position) - 1))
        siblings.insert(index, me)
        for i, item in enumerate(siblings, start=1):
            if item.display_order != i:
                # `update` مستقیم: بدون سیگنال، بدون بازنویسی `updated_at`ِ
                # بقیه. سیگنال‌های کش هم دستی صدا زده می‌شوند تا یک
                # جابه‌جایی، دو بار کش را باطل نکند.
                type(self).all_objects.filter(pk=item.pk).update(display_order=i)
        self.refresh_from_db()


class LeaderPortrait(OrderedItem):
    """یک تصویر از رهبر انقلاب، همراه با کلامِ همان تصویر.

    ⚠️ `caption` و `caption_paragraphs` هر دو وجود دارند و این تکرار نیست:
    `caption` میدانِ سادهٔ فرمِ ادمین است (یک جمله) و `caption_paragraphs`
    همان متن، شکسته‌شده به پاراگراف، برای خروجی API. اگر ادمین چند
    پاراگراف بنویسد (با خط خالی بین‌شان)، هر دو پر می‌شوند؛ اگر یک خط
    بنویسد، فقط یک پاراگراف داریم. این تفکیک، فرم ادمین را ساده نگه
    می‌دارد و API را بدون تغییر شکل می‌دهد.
    """

    image = models.ImageField(
        upload_to="gallery/leader/",
        verbose_name="تصویر",
        help_text="نسبت پیشنهادی ۴:۵ (عمودی) یا ۱:۱. عرض پیشنهادی ۹۰۰ پیکسل.",
    )
    alt = models.CharField(
        max_length=180,
        blank=True,
        default="",
        verbose_name="متن جانشین تصویر",
        help_text="برای صفحه‌خوان. اگر خالی بماند از عنوان ساخته می‌شود.",
    )
    caption = models.TextField(
        blank=True,
        default="",
        verbose_name="کلام همراه تصویر",
        help_text="می‌توانید چند پاراگراف بنویسید (بین پاراگراف‌ها یک خط خالی).",
    )
    source = models.CharField(
        max_length=200,
        blank=True,
        default="",
        verbose_name="منبع / انتساب",
        help_text="مثل: از بیانات رهبر انقلاب اسلامی دربارهٔ کتاب و کتاب‌خوانی",
    )
    show_in_box = models.BooleanField(
        default=True,
        verbose_name="در باکس «کتاب و کلام» صفحهٔ اول دیده شود",
        help_text="اگر خاموش شود، تصویر در گالری هست ولی صفحهٔ اول آن را نشان نمی‌دهد.",
    )

    class Meta(OrderedItem.Meta):
        verbose_name = "تصویر رهبر انقلاب"
        verbose_name_plural = "تصاویر رهبر انقلاب"

    def __str__(self) -> str:
        """نمایش کوتاه و خوانا در فهرست ادمین."""
        head = (self.alt or self.caption or "").strip().splitlines()
        first = head[0][:60] if head else ""
        return first or f"تصویر #{self.pk}"

    # ── کمکی‌ها ───────────────────────────────────────────────────────────
    def paragraphs(self) -> list[str]:
        """کلام، شکسته به پاراگراف‌های غیرخالی."""
        return [p.strip() for p in str(self.caption or "").split("\n") if p.strip()]

    def effective_alt(self) -> str:
        """متن جانشین: اگر ادمین نداده، از ابتدای کلام ساخته می‌شود."""
        if self.alt.strip():
            return self.alt.strip()
        first = self.paragraphs()[:1]
        return first[0][:140] if first else "تصویر رهبر انقلاب اسلامی در حال مطالعهٔ کتاب"

    def clean(self) -> None:
        """اعتبارسنجی: تصویر اجباری است و باید تصویر باشد."""
        super().clean()
        if not self.image:
            raise ValidationError({"image": "تصویر الزامی است."})
        name = str(getattr(self.image, "name", "") or "")
        if name and not _is_allowed_image(name):
            raise ValidationError({"image": "فقط فایل تصویری (jpg، png، webp) مجاز است."})


class Martyr(OrderedItem):
    """یک شهید برای نوار گردان بالای فوتر.

    ⚠️ چرا «عنوان کوتاه» جدا از زیرنویس است؟ طراحی نوار، عنوان را زیر
    تصویرِ گرد و در یک خط نشان می‌دهد. اگر عنوان بلند باشد، نوار می‌شکند.
    پس عنوان `max_length=48` است و متنِ بلندتر به `subtitle` می‌رود.
    """

    image = models.ImageField(
        upload_to="gallery/martyrs/",
        verbose_name="تصویر (مربع)",
        help_text="مربع، حداقل ۳۲۰×۳۲۰. تصویر گرد نمایش داده می‌شود؛ چهره را در مرکز بگذارید.",
    )
    title = models.CharField(
        max_length=48,
        verbose_name="عنوان کوتاه",
        help_text="زیر تصویر نمایش داده می‌شود؛ کوتاه بماند (مثل: سیدشهدای مقاومت).",
    )
    subtitle = models.CharField(
        max_length=90,
        blank=True,
        default="",
        verbose_name="زیرنویس (اختیاری)",
        help_text="مثل: شهید محمود کاوه — فرماندهٔ لشکر ویژهٔ ۱۵۵ شهدا",
    )
    alt = models.CharField(
        max_length=180,
        blank=True,
        default="",
        verbose_name="متن جانشین تصویر",
        help_text="اگر خالی بماند از عنوان ساخته می‌شود.",
    )

    class Meta(OrderedItem.Meta):
        verbose_name = "شهید (نوار گردان)"
        verbose_name_plural = "شهدا (نوار گردان)"

    def __str__(self) -> str:
        """نمایش عنوان در فهرست ادمین."""
        return str(self.title)

    def effective_alt(self) -> str:
        """متن جانشین: عنوان، و اگر زیرنویس بود، با آن."""
        if self.alt.strip():
            return self.alt.strip()
        return f"{self.title} — {self.subtitle}" if self.subtitle else str(self.title)

    def clean(self) -> None:
        """اعتبارسنجی: تصویر اجباری است و باید تصویر باشد."""
        super().clean()
        if not self.image:
            raise ValidationError({"image": "تصویر الزامی است."})
        name = str(getattr(self.image, "name", "") or "")
        if name and not _is_allowed_image(name):
            raise ValidationError({"image": "فقط فایل تصویری (jpg، png، webp) مجاز است."})


ALLOWED_IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png", ".webp", ".avif")


def _is_allowed_image(name: str) -> bool:
    """آیا پسوند فایل تصویریِ مجاز است؟"""
    return str(name).lower().endswith(ALLOWED_IMAGE_SUFFIXES)


def safe_filename(name: str) -> str:
    """نام فایل امن برای مسیر رسانه (فقط برای تست‌ها و ابزارهای مهاجرت)."""
    return slugify(name) or "image"

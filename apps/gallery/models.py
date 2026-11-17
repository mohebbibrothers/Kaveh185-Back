"""مدل‌های گالری محتوایی — دو چیز که ادمین باید بتواند از پنل عوض کند.

── چرا این دو مدل و نه یک مدل با «نوع»؟ ─────────────────────────────────
دو کاربرد، دو شکل دادهٔ متفاوت دارند و در دو جای متفاوت صفحه دیده می‌شوند:

۱) **`LeaderPortrait`** — تصاویر رهبر انقلاب در باکسِ «کتاب و کلام».
   هر رکورد یک تصویر + یک **کلام** است؛ چون در همان باکس، کنار تصویر
   متنِ روایت هم می‌آید و ادمین باید بتواند متن هر تصویر را جدا تعریف
   کند. صفحهٔ اول یک تصویر را نشان می‌دهد و بقیه را در گالریِ همان باکس
   (چرخش خودکار + انتخاب دستی). پس به `order` نیاز دارد، نه به تاریخ.

۲) **`Martyr`** — نوار شهدای بالای فوتر: تصویر گِرد + عنوان کوتاه.
   اینجا فقط دو فیلد محتوایی لازم است: تصویر و عنوان. ترتیب اهمیت دارد
   (مثلاً «سیدشهدای مقاومت» اول) پس `order` دارد.

── اصل صداقت ─────────────────────────────────────────────────────────────
اگر ادمین هیچ رکوردی نسازد، API فهرست خالی می‌دهد و فرانت **بخش را
نمایش نمی‌دهد** — نه اینکه با تصاویر ساختگی پرش کند. یعنی صفحه هرگز
«گالریِ خالی» یا «شهیدِ جعلی» نشان نمی‌دهد.
"""

from __future__ import annotations

import logging

from django.db import models
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from apps.core.cache_invalidation import invalidate_domain_cache
from apps.core.models import BaseModel

logger = logging.getLogger("apps.gallery")


def _invalidate_gallery() -> None:
    """باطل‌کردن کش گالری پس از هر تغییر.

    ⚠️ چرا اینجا و نه در `admin.save_model`؟ چون رکورد ممکن است از
    shell، از یک دستور مدیریتی، یا از پنل ادمین عوض شود. سیگنالِ مدل
    **همهٔ** مسیرها را می‌گیرد؛ ادمین فقط یکی از آن‌هاست.
    """
    try:
        invalidate_domain_cache(domain="gallery", reason="تغییر گالری از پنل ادمین")
    except Exception:  # pragma: no cover - ابطال نباید ذخیره را بشکند
        # ابطال کش یک کار جانبی است؛ اگر شکست بخورد، ذخیرهٔ ادمین نباید
        # با خطای ۵۰۰ به کاربر برگردد. ولی سکوتِ کامل هم خطرناک است، پس
        # لاگ می‌شود تا در پایش دیده شود.
        logger.warning("ابطال کش گالری شکست خورد", exc_info=True)


def _upload_to_portrait(instance: LeaderPortrait, filename: str) -> str:
    """مسیر آپلودِ تصاویر رهبر: `gallery/leader/<filename>`."""
    del instance
    return f"gallery/leader/{filename}"


def _upload_to_martyr(instance: Martyr, filename: str) -> str:
    """مسیر آپلودِ تصاویر شهدا: `gallery/martyrs/<filename>`."""
    del instance
    return f"gallery/martyrs/{filename}"


class LeaderPortrait(BaseModel):
    """یک تصویر از رهبر انقلاب همراه با کلامِ منتسب و برچسب منبع.

    `caption` = کلامی که کنار تصویر خوانده می‌شود (می‌تواند چند بند باشد،
    بندها با خطِ خالی جدا می‌شوند). `source` = برچسب انتساب؛ ادمین آن را
    دقیق وارد می‌کند تا هیچ متنی بی‌سند روی سایت نرود.
    """

    image = models.ImageField(
        upload_to=_upload_to_portrait,
        verbose_name="تصویر",
        help_text="نسبت پیشنهادی ۴:۵ (عمودی). قاب سایت تصویر را با object-cover می‌بُرد؛ "
        "پس چهره را در مرکز/بالا نگه دارید. حداکثر ۴ مگابایت.",
    )
    alt = models.CharField(
        max_length=180,
        verbose_name="متن جانشین تصویر (alt)",
        help_text="برای صفحه‌خوان‌ها و وقتی تصویر بارگذاری نمی‌شود. "
        "مثال: «آیت‌الله خامنه‌ای در حال مطالعهٔ کتاب».",
    )
    caption = models.TextField(
        blank=True,
        verbose_name="کلام / متنِ همراه",
        help_text="اگر خالی باشد، کلامِ پیش‌فرضِ سایت نشان داده می‌شود. "
        "برای جدا کردن بندها یک خط خالی بگذارید.",
    )
    source = models.CharField(
        max_length=180,
        blank=True,
        verbose_name="برچسب منبع",
        help_text="مثال: «از بیانات رهبر انقلاب اسلامی دربارهٔ کتاب و کتاب‌خوانی».",
    )
    order = models.PositiveSmallIntegerField(
        default=0,
        db_index=True,
        verbose_name="ترتیب نمایش",
        help_text="عدد کمتر = جلوتر. تصویر اول، تصویرِ پیش‌فرضِ باکس است.",
    )
    show_in_box = models.BooleanField(
        default=True,
        verbose_name="در باکس صفحهٔ اول دیده شود",
        help_text="اگر خاموش باشد، این تصویر فقط در گالری داخل باکس می‌آید، نه به‌عنوان تصویرِ نخست.",
    )

    class Meta:
        verbose_name = "تصویر رهبر انقلاب"
        verbose_name_plural = "تصاویر رهبر انقلاب"
        ordering = ["order", "-created_at", "-id"]

    def __str__(self) -> str:
        return self.alt or f"تصویر #{self.pk}"


class Martyr(BaseModel):
    """یک شهید برای نوار بالای فوتر: تصویر گِرد + عنوان کوتاه."""

    image = models.ImageField(
        upload_to=_upload_to_martyr,
        verbose_name="تصویر",
        help_text="نسبت مربع (۱:۱) بهترین نتیجه را می‌دهد؛ تصویر در نوار گِرد می‌شود.",
    )
    title = models.CharField(
        max_length=80,
        verbose_name="عنوان کوتاه",
        help_text="مثال: «سیدشهدای مقاومت». حداکثر ۸۰ نویسه تا در نوار جا شود.",
    )
    subtitle = models.CharField(
        max_length=120,
        blank=True,
        verbose_name="زیرنویس (اختیاری)",
        help_text="مثال: «شهید قاسم سلیمانی». اگر خالی بماند، فقط عنوان دیده می‌شود.",
    )
    alt = models.CharField(
        max_length=180,
        blank=True,
        verbose_name="متن جانشین تصویر (alt)",
        help_text="اگر خالی بماند، از عنوان ساخته می‌شود.",
    )
    order = models.PositiveSmallIntegerField(
        default=0,
        db_index=True,
        verbose_name="ترتیب نمایش",
        help_text="عدد کمتر = جلوتر.",
    )

    class Meta:
        verbose_name = "شهید (نوار بالای فوتر)"
        verbose_name_plural = "نوار شهدا"
        ordering = ["order", "-created_at", "-id"]

    def __str__(self) -> str:
        return self.title

    def save(self, *args: object, **kwargs: object) -> None:
        """اگر `alt` خالی بماند، از عنوان پر می‌شود تا تصویر بی‌متن نماند."""
        if not self.alt:
            self.alt = self.title
        super().save(*args, **kwargs)  # type: ignore[arg-type]


# ── سیگنال‌ها ────────────────────────────────────────────────────────────
# `dispatch_uid` صریح است تا اگر ماژول دو بار import شود (که در تست‌ها و
# autoreload اتفاق می‌افتد) سیگنال دوبار وصل نشود و ابطال دوبار اجرا نشود.
#
# ⚠️ چرا `sender=` اجباری است:
# سیگنالِ بدون `sender` برای **هر** مدلی در کل پروژه اجرا می‌شود — از جمله
# در میانهٔ `migrate`، وقتی جدولِ رخدادِ ابطال هنوز ساخته نشده. نتیجه: خطای
# «no such table» در تست‌ها. با `sender`، گیرنده فقط برای گالری بیدار می‌شود.
@receiver(post_save, sender=LeaderPortrait, dispatch_uid="gallery_leader_saved")
def _on_leader_saved(sender: object, **kwargs: object) -> None:
    """ابطال کش پس از ذخیرهٔ تصویر رهبر."""
    del sender, kwargs
    _invalidate_gallery()


@receiver(post_delete, sender=LeaderPortrait, dispatch_uid="gallery_leader_deleted")
def _on_leader_deleted(sender: object, **kwargs: object) -> None:
    """ابطال کش پس از حذف تصویر رهبر."""
    del sender, kwargs
    _invalidate_gallery()


@receiver(post_save, sender=Martyr, dispatch_uid="gallery_martyr_saved")
def _on_martyr_saved(sender: object, **kwargs: object) -> None:
    """ابطال کش پس از ذخیرهٔ شهید."""
    del sender, kwargs
    _invalidate_gallery()


@receiver(post_delete, sender=Martyr, dispatch_uid="gallery_martyr_deleted")
def _on_martyr_deleted(sender: object, **kwargs: object) -> None:
    """ابطال کش پس از حذف شهید."""
    del sender, kwargs
    _invalidate_gallery()

"""مدل لاگ ارسال پیامک‌های سامانه کاوه ۱۸۵."""

from __future__ import annotations

from django.db import models

from apps.core.models import BaseModel

from .choices import SMSCategory, SMSDeliveryStatus


class SMSDeliveryLog(BaseModel):
    """رکورد ممیزی و وضعیت ارسال هر پیامک در سامانه."""

    recipient_phone = models.CharField(
        max_length=15,
        db_index=True,
        verbose_name="شماره موبایل گیرنده",
    )
    category = models.CharField(
        max_length=24,
        choices=SMSCategory.choices,
        default=SMSCategory.THANK_YOU,
        db_index=True,
        verbose_name="نوع پیامک",
    )
    provider = models.CharField(
        max_length=32,
        default="console",
        verbose_name="درگاه پیامکی",
    )
    message_text = models.TextField(verbose_name="متن پیامک")
    status = models.CharField(
        max_length=16,
        choices=SMSDeliveryStatus.choices,
        default=SMSDeliveryStatus.SENT,
        db_index=True,
        verbose_name="وضعیت ارسال",
    )
    provider_message_id = models.CharField(
        max_length=120,
        blank=True,
        default="",
        verbose_name="شناسه رهگیری درگاه",
    )
    error_message = models.TextField(
        blank=True,
        default="",
        verbose_name="پیام خطا",
    )

    class Meta:
        verbose_name = "لاگ ارسال پیامک"
        verbose_name_plural = "لاگ‌های ارسال پیامک"
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        """نمایش خوانای لاگ پیامک."""
        return f"SMS[{self.category}] -> {self.recipient_phone} ({self.status})"


class BaleSubscriber(BaseModel):
    """کاربری که رباتِ بله را «شروع» کرده و شماره‌اش را به ربات داده است.

    ── چرا لازم است؟ ──────────────────────────────────────────────────────
    بله برای ارسالِ پیام به یک شخص، `chat_id` می‌خواهد و `chat_id` را فقط
    وقتی می‌دهد که **خودِ کاربر** با ربات شروع کرده باشد. ما شمارهٔ همراه را
    از فرمِ ثبت‌نام داریم، ولی این پل را نداریم. این جدول همان پل است:
    کاربر یک‌بار «شروع» و شماره‌اش را در ربات می‌فرستد، و از آن پس هر کدِ
    تأییدی که برای آن شماره بخواهیم، از بله می‌رود — بدونِ پیامک و بدونِ
    هیچ هزینه‌ای.

    ── نکتهٔ امنیتی ───────────────────────────────────────────────────────
    هر شماره فقط یک رکورد دارد (تغییرِ `chat_id` یعنی کاربر با حسابِ بلهٔ
    دیگری آمده و رکورد به‌روز می‌شود، نه تکراری). خودِ کدِ تأیید هیچ‌جا
    ذخیره نمی‌شود؛ فقط این «نشانی» نگه داشته می‌شود.
    """

    phone_number = models.CharField(
        max_length=15,
        unique=True,
        db_index=True,
        verbose_name="شماره همراه",
    )
    chat_id = models.BigIntegerField(db_index=True, verbose_name="شناسه گفتگو در بله")
    bale_first_name = models.CharField(
        max_length=80, blank=True, default="", verbose_name="نام در بله"
    )
    bale_username = models.CharField(
        max_length=80, blank=True, default="", verbose_name="نام کاربری بله"
    )
    is_active = models.BooleanField(default=True, db_index=True, verbose_name="فعال")

    class Meta:
        verbose_name = "مشترک ربات بله"
        verbose_name_plural = "مشترکان ربات بله"
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        """نمایش خوانا."""
        return f"{self.phone_number} → chat {self.chat_id}"


class BaleLinkCode(BaseModel):
    """کدِ کوتاهِ اتصالِ شماره به گفتگوی بله (فقط هش نگه داشته می‌شود).

    چرا؟ کاربر شماره‌اش را به ربات نمی‌فرستد و ما راهی نداریم بفهمیم یک
    `chat_id` مالِ کدام شماره است. کدِ یک‌بارمصرف این پل را می‌سازد: سامانه کد
    را به کاربری می‌دهد که شماره‌اش را از قبل می‌داند؛ کاربر کد را به ربات
    می‌فرستد؛ ربات با دیدنِ کد می‌فهمد «این گفتگو = آن شماره».

    ⚠️ کدِ خام هرگز ذخیره نمی‌شود (فقط `code_hash` با `SECRET_KEY`)، عمرش
    کوتاه است و بعد از استفاده می‌سوزد. تعدادِ تلاشِ هر کد هم محدود است.
    """

    phone_number = models.CharField(max_length=15, db_index=True, verbose_name="شماره همراه")
    code_hash = models.CharField(max_length=64, db_index=True, verbose_name="هش کد")
    #: شناسهٔ کوتاهِ عمومیِ همین رکورد — در پیوندِ عمیق می‌رود
    #: (`ble.ir/<bot>?start=<intent>`). چون قابلِ حدس نیست و فقط برای وصل‌کردن
    #: به‌کار می‌رود، خودش راز نیست؛ در عوض شماره هرگز در نشانی نمی‌رود.
    intent = models.CharField(
        max_length=12, blank=True, default="", db_index=True, verbose_name="شناسهٔ نیّتِ پیوند"
    )
    attempts = models.PositiveSmallIntegerField(default=0, verbose_name="تلاش‌ها")
    expires_at = models.DateTimeField(db_index=True, verbose_name="انقضا")
    consumed_at = models.DateTimeField(null=True, blank=True, verbose_name="زمان مصرف")

    class Meta:
        verbose_name = "کد اتصال بله"
        verbose_name_plural = "کدهای اتصال بله"
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["code_hash", "consumed_at"])]

    def __str__(self) -> str:
        """نمایش خوانا (بدونِ خودِ کد)."""
        return f"{self.phone_number} · {'مصرف‌شده' if self.consumed_at else 'فعال'}"


class BaleDeliveryLog(BaseModel):
    """دفترِ تحویلِ آپدیت‌های بله — «آیا بله اصلاً چیزی فرستاد؟»

    چرا این جدول لازم شد؟ در آزمونِ واقعی، صفِ بله صفر بود و هیچ راهی نبود
    بفهمیم بله آپدیت را تحویل داده و ما پاسخ داده‌ایم، یا اصلاً چیزی نرسیده.
    `getWebhookInfo` فقط «آخرین خطا» و «صف» را می‌گوید؛ چیزی که **رسید** را
    ثبت کند ندارد. این جدول همان شاهد است: هر تحویل (وب‌هوک یا polling) یک
    سطر، با نتیجهٔ پردازش و اینکه پاسخ در بله **واقعاً ارسال شد یا نه**.

    ⚠️ هیچ متنِ پیام یا شماره‌ای این‌جا ذخیره نمی‌شود؛ فقط نوعِ پردازش،
    شناسهٔ گفتگو (برای پیگیری)، و نتیجه. `note` هم فقط دستهٔ خطاست، نه متنِ آن.
    """

    class Source(models.TextChoices):
        WEBHOOK = "webhook", "وب‌هوک"
        POLLING = "polling", "کران (polling)"

    source = models.CharField(
        max_length=16,
        choices=Source.choices,
        default=Source.WEBHOOK,
        db_index=True,
        verbose_name="مسیرِ تحویل",
    )
    chat_id = models.BigIntegerField(db_index=True, verbose_name="شناسهٔ گفتگو")
    handled = models.CharField(max_length=32, verbose_name="نوعِ پردازش")
    replied = models.BooleanField(default=False, verbose_name="پاسخ ارسال شد؟")
    note = models.CharField(max_length=180, blank=True, default="", verbose_name="یادداشت")

    class Meta:
        verbose_name = "تحویلِ بله"
        verbose_name_plural = "دفترِ تحویلِ بله"
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["-created_at"], name="notif_baledel_created_idx")]

    def __str__(self) -> str:
        return f"{self.get_source_display()} · chat={self.chat_id} · {self.handled}"

"""ثبت/بازرسی/حذفِ وب‌هوکِ رباتِ بله — یک دستور، بدونِ ساختنِ URL دستی.

چرا این دستور؟ برای تنظیمِ وب‌هوک باید نشانیِ درست، توکن و کلیدِ امن را در یک
درخواست کنارِ هم گذاشت؛ انجامش با `curl` روی سرور یعنی توکن در تاریخچهٔ شل و
در چند جای دیگر تکرار می‌شود. این‌جا همه‌چیز از `.env` خوانده می‌شود و هیچ
مقدارِ حساسی چاپ نمی‌شود.

    python manage.py bale_webhook                 # ثبت (پیش‌فرض: api.kaveh185.ir)
    python manage.py bale_webhook --show          # وب‌هوکِ فعلی چه می‌گوید؟
    python manage.py bale_webhook --delete        # برداشتن (برگشت به کران)
    python manage.py bale_webhook --url https://… # نشانیِ دلخواه (مثلاً دامنهٔ دیگر)
    python manage.py bale_webhook --print-url     # فقط نشانیِ ساخته‌شده را نشان بده
"""

from __future__ import annotations

import secrets
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError, CommandParser

from apps.notifications import probe
from apps.notifications.bale import BaleError, bale_is_configured


def _call(method: str, payload: dict[str, object] | None = None) -> dict:
    """تماس با بله از راهِ خودِ ماژولِ کلاینت.

    چرا غیرمستقیم؟ اگر `_api` را مستقیم import کنیم، در تست‌ها جای‌گزینیِ
    ماژولِ کلاینت اثری ندارد و تست به شبکهٔ واقعی می‌خورد. این یک خط،
    آزمون‌پذیریِ دستور را بدونِ تغییرِ رفتار حفظ می‌کند.
    """
    from apps.notifications import bale as bale_module

    return bale_module._api(method, payload)


WEBHOOK_PATH = "/api/v1/notifications/bale/webhook/"


class Command(BaseCommand):
    """مدیریتِ وب‌هوکِ ربات در بله (setWebhook / getWebhookInfo / deleteWebhook)."""

    help = "ثبت، بازرسی یا حذفِ وب‌هوکِ ربات بله"

    def add_arguments(self, parser: CommandParser) -> None:
        """گزینه‌های عمل، نشانی و آزمون."""
        parser.add_argument("--show", action="store_true", help="فقط وضعیتِ وب‌هوک را نشان بده")
        parser.add_argument("--delete", action="store_true", help="وب‌هوک را بردار")
        parser.add_argument(
            "--url", default="", help="نشانیِ کاملِ وب‌هوک (پیش‌فرض: BALE_WEBHOOK_URL یا دامنهٔ API)"
        )
        parser.add_argument("--print-url", action="store_true", help="فقط نشانیِ پیشنهادی را چاپ کن")
        parser.add_argument(
            "--new-secret",
            action="store_true",
            help="اگر کلید خالی است، یک کلیدِ تصادفی بساز و همان را چاپ کن (در .env بگذار)",
        )
        parser.add_argument(
            "--probe",
            action="store_true",
            help=(
                "آزمونِ حلقه‌ای: همان POSTای که بله می‌فرستد (با هدرِ کلید) به خودِ وب‌هوک بزن، "
                "بی‌آنکه به هیچ گفتگویی پیام برود."
            ),
        )
        parser.add_argument(
            "--skip-self-test",
            action="store_true",
            help="آزمونِ دسترس‌پذیری از بیرون را رد کن (اگر سرور نتواند دامنهٔ خودش را باز کند).",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        """اجرای عملِ خواسته‌شده."""
        del args
        url = self._resolve_url(str(options["url"]))

        if options["print_url"]:
            self.stdout.write(url)
            return

        if not bale_is_configured():
            raise CommandError("BALE_BOT_TOKEN تنظیم نشده است؛ اول ربات را در `.env` بگذارید.")

        if options.get("probe"):
            self._loopback_test(url)
            return

        if options["show"]:
            self._show()
            return
        if options["delete"]:
            self._delete()
            return

        secret = str(getattr(settings, "BALE_WEBHOOK_SECRET", "") or "").strip()
        if not secret and options["new_secret"]:
            secret = secrets.token_hex(24)
            self.stdout.write(
                self.style.WARNING(
                    "کلیدِ تازه ساخته شد. این خط را در `.env` سرور بگذارید و بعد دوباره اجرا کنید:\n"
                    f"  BALE_WEBHOOK_SECRET={secret}"
                )
            )
            return
        if not secret:
            self.stdout.write(
                self.style.WARNING(
                    "⚠️ BALE_WEBHOOK_SECRET خالی است. بدونِ کلید، هر کسی می‌تواند آپدیتِ "
                    "جعلی بفرستد و شمارهٔ دلخواه را به گفتگویی بچسباند.\n"
                    "  یک‌بار `manage.py bale_webhook --new-secret` را بزنید."
                )
            )

        payload: dict[str, object] = {"url": url, "max_connections": 40}
        if secret:
            payload["secret_token"] = secret
        try:
            res = _call("setWebhook", payload)
        except BaleError as exc:
            raise CommandError(str(exc)) from exc

        if not res.get("ok"):
            raise CommandError(f"بله ثبتِ وب‌هوک را نپذیرفت: {res.get('description', '')}")
        self.stdout.write(self.style.SUCCESS(f"✓ وب‌هوک ثبت شد: {url}"))
        healthy = True if options.get("skip_self_test") else self._self_test(url)
        self._show()
        if not healthy:
            self.stdout.write("")
            self.stdout.write(
                self.style.ERROR(
                    "این نشانی از بیرون به اپلیکیشن نمی‌رسد؛ بله آپدیت‌ها را تحویل نمی‌دهد و "
                    "کاربر «شروع» می‌زند و هیچ پاسخی نمی‌گیرد.\n"
                    "  دو انتخاب:\n"
                    "   ۱) نشانیِ درست را بدهید:  --url https://api.<domain>/…\n"
                    "   ۲) وب‌هوک را بردارید و کران را فعال کنید:  bale_webhook --delete\n\n"
                    "  نکته: این آزمون از روی خودِ سرور اجرا می‌شود. اگر نشانی را در مرورگر "
                    "باز کردید و پاسخِ سلامت آمد، این خطا مربوط به شبکهٔ سرور است (هاست "
                    "نمی‌تواند دامنهٔ خودش را از داخل باز کند) و می‌توانید با "
                    "`--skip-self-test` ثبت را بدونِ آزمون انجام دهید."
                )
            )

    # ── کمکی‌ها ────────────────────────────────────────────────────────────
    def _loopback_test(self, url: str) -> None:
        """آزمونِ حلقه‌ای: همان درخواستی که بله می‌فرستد، از خودمان به خودمان.

        چرا؟ GETِ سلامت فقط می‌گوید «مسیر باز است». آنچه واقعاً باید کار کند
        این است: یک POST با هدرِ کلید که ۲۰۰ و `ok: true` برگرداند. اگر کلید
        جابه‌جا باشد یا middleware درخواست را رد کند، همین‌جا لو می‌رود — نه
        وقتی کاربر واقعی `/start` می‌زند و هیچ پاسخی نمی‌گیرد.
        """
        secret = str(getattr(settings, "BALE_WEBHOOK_SECRET", "") or "")
        ok, message = probe.loopback(url, secret)
        self._line(ok, f"آزمونِ حلقه‌ای: {message}")

    def _self_test(self, url: str) -> bool:
        """آیا این نشانی از بیرون واقعاً خودِ اپلیکیشنِ ما است؟

        `setWebhook` همیشه «ثبت شد» می‌گوید؛ ولی اگر نشانی ۴۰۴ بدهد یا صفحهٔ
        دیگری ۲۰۰ بدهد، بله آپدیت‌ها را تحویل نمی‌دهد و خطا را فقط در
        `getWebhookInfo` نگه می‌دارد — یعنی کاربر «شروع» می‌زند و هیچ نمی‌شود.
        """
        ok, message = probe.health(url)
        self._line(ok, message)
        return ok

    def _line(self, ok: bool, text: str) -> None:
        """یک سطرِ گزارش."""
        mark = "✓" if ok else "✗"
        style = self.style.SUCCESS if ok else self.style.WARNING
        self.stdout.write(style(f"  {mark} {text}"))

    def _resolve_url(self, given: str) -> str:
        """نشانیِ وب‌هوک: `--url`، بعد `BALE_WEBHOOK_URL`، بعد دامنهٔ تنظیمات."""
        if given:
            return given
        pinned = str(getattr(settings, "BALE_WEBHOOK_URL", "") or "").strip()
        if pinned:
            return pinned
        # ⚠️ ترتیبِ ALLOWED_HOSTS روی این هاست `www` را اول می‌آورد و بله آپدیت‌ها
        # را به آن می‌فرستد؛ حالا که هر دو به یک اپ می‌رسند کار می‌کند، ولی
        # `api.` معنای درست‌تری دارد و اگر روزی سایت و API جدا شوند، `www`
        # بی‌صدا وب‌هوک را می‌شکند. پس صریحاً `api.` ترجیح دارد.
        host = ""
        candidates = [str(c).strip() for c in (getattr(settings, "ALLOWED_HOSTS", []) or [])]
        for prefer in ("api.", "www."):
            host = next((c for c in candidates if c.startswith(prefer)), "")
            if host:
                break
        if not host:
            for candidate in getattr(settings, "ALLOWED_HOSTS", []) or []:
                text = str(candidate).strip()
                if text and not text.startswith(".") and text != "*":
                    host = text
                    break
        if not host:
            raise CommandError(
                "دامنه‌ای در ALLOWED_HOSTS پیدا نشد؛ نشانی را دستی بدهید: "
                "--url https://api.example.ir" + WEBHOOK_PATH
            )
        # بله فقط https می‌پذیرد؛ استثنا فقط محیطِ توسعهٔ محلی است.
        scheme = "http" if host.startswith(("localhost", "127.0.0.1", "[::1]")) else "https"
        return f"{scheme}://{host}{WEBHOOK_PATH}"

    def _show(self) -> None:
        """وضعیتِ وب‌هوک را از خودِ بله می‌خواند."""
        try:
            info = _call("getWebhookInfo").get("result") or {}
        except BaleError as exc:
            raise CommandError(str(exc)) from exc
        url = str(info.get("url") or "")
        if not url:
            self.stdout.write(
                self.style.WARNING("هیچ وب‌هوکی ثبت نیست ⇒ باید کرانِ `bale_inbox` را اجرا کنید.")
            )
            return
        self.stdout.write(f"  نشانی: {url}")
        self.stdout.write(f"  آپدیتِ در انتظار: {info.get('pending_update_count', 0)}")
        if info.get("last_error_message"):
            self.stdout.write(
                self.style.ERROR(
                    "  آخرین خطای تحویل: "
                    f"{info.get('last_error_message')} "
                    f"(کد {info.get('last_error_code', '?')})"
                )
            )
            self.stdout.write(
                "  ⇒ اگر کد ۴۰۳/۴۰۴ است، نشانیِ وب‌هوک به اپلیکیشنِ Django وصل نیست؛ "
                "وب‌هوک را بردارید و از کران استفاده کنید."
            )

    def _delete(self) -> None:
        """وب‌هوک را برمی‌دارد (بله از آن پس آپدیت‌ها را در getUpdates نگه می‌دارد)."""
        try:
            res = _call("deleteWebhook")
        except BaleError as exc:
            raise CommandError(str(exc)) from exc
        if res.get("ok"):
            self.stdout.write(self.style.SUCCESS("✓ وب‌هوک برداشته شد؛ حالا کران صندوق را بخواند."))
        else:
            raise CommandError(f"حذف انجام نشد: {res.get('description', '')}")

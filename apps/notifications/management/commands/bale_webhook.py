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
        """گزینه‌های عمل و نشانی."""
        parser.add_argument("--show", action="store_true", help="فقط وضعیتِ وب‌هوک را نشان بده")
        parser.add_argument("--delete", action="store_true", help="وب‌هوک را بردار")
        parser.add_argument(
            "--url", default="", help="نشانیِ کاملِ وب‌هوک (پیش‌فرض: دامنهٔ API + مسیرِ استاندارد)"
        )
        parser.add_argument("--print-url", action="store_true", help="فقط نشانیِ پیشنهادی را چاپ کن")
        parser.add_argument(
            "--new-secret",
            action="store_true",
            help="اگر کلید خالی است، یک کلیدِ تصادفی بساز و همان را چاپ کن (در .env بگذار)",
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
        healthy = self._self_test(url)
        self._show()
        if not healthy:
            self.stdout.write("")
            self.stdout.write(
                self.style.ERROR(
                    "این نشانی از بیرون به اپلیکیشن نمی‌رسد؛ بله آپدیت‌ها را تحویل نمی‌دهد و "
                    "کاربر «شروع» می‌زند و هیچ پاسخی نمی‌گیرد.\n"
                    "  دو انتخاب:\n"
                    "   ۱) نشانیِ درست را بدهید:  --url https://api.<domain>/…\n"
                    "   ۲) وب‌هوک را بردارید و کران را فعال کنید:  bale_webhook --delete"
                )
            )

    # ── کمکی‌ها ────────────────────────────────────────────────────────────
    def _self_test(self, url: str) -> bool:
        """آزمونِ خودکارِ وب‌هوک: آیا نشانی از بیرون واقعاً پاسخ می‌دهد؟

        چرا لازم است؟ `setWebhook` می‌گوید «ثبت شد» حتی وقتی آن نشانی ۴۰۴
        می‌دهد؛ بله خطا را فقط در `getWebhookInfo` نگه می‌دارد و آپدیت‌ها صف
        می‌شوند. آزمونِ زیر همان چیزی است که مرورگر می‌بیند: یک GET ساده به
        مسیرِ سلامت. اگر پاسخِ خودِ اپلیکیشن نیامد، **همین حالا** هشدار می‌دهد،
        نه فردا که کدها نرسیده‌اند.
        """
        import json
        import urllib.error
        import urllib.request

        probe = url.rstrip("/") + "/"
        try:
            with urllib.request.urlopen(probe, timeout=8) as resp:  # noqa: S310
                body = resp.read(400).decode("utf-8", errors="replace")
                status = resp.status
        except urllib.error.HTTPError as exc:
            self._line(False, f"نشانیِ وب‌هوک از بیرون پاسخ {exc.code} داد: {probe}")
            return False
        except Exception as exc:  # pragma: no cover - شبکهٔ بیرونی
            self._line(False, f"نشانیِ وب‌هوک از بیرون در دسترس نیست ({type(exc).__name__}).")
            return False

        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            payload = {}
        if status == 200 and payload.get("service") == "kaveh185-bale-webhook":
            self._line(True, "نشانی از بیرون سالم است (پاسخِ سلامت دریافت شد).")
            return True
        self._line(False, f"نشانی پاسخ داد ولی این اپلیکیشن نبود ({status}): {body[:80]}")
        return False

    def _line(self, ok: bool, text: str) -> None:
        """یک سطرِ گزارش."""
        mark = "✓" if ok else "✗"
        style = self.style.SUCCESS if ok else self.style.WARNING
        self.stdout.write(style(f"  {mark} {text}"))

    def _resolve_url(self, given: str) -> str:
        """نشانیِ وب‌هوک: مقدارِ داده‌شده، وگرنه از دامنهٔ امنِ تنظیمات."""
        if given:
            return given
        host = ""
        for candidate in getattr(settings, "ALLOWED_HOSTS", []) or []:
            text = str(candidate).strip()
            if text.startswith("api.") or text.startswith("www."):
                host = text
                break
        if not host:
            for candidate in getattr(settings, "ALLOWED_HOSTS", []) or []:
                text = str(candidate).strip()
                if text and not text.startswith(".") and text not in {"*", "localhost"}:
                    host = text
                    break
        if not host:
            raise CommandError(
                "دامنه‌ای در ALLOWED_HOSTS پیدا نشد؛ نشانی را دستی بدهید: "
                "--url https://api.example.ir" + WEBHOOK_PATH
            )
        return f"https://{host}{WEBHOOK_PATH}"

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

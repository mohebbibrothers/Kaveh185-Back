"""تشخیصِ کاملِ کانالِ بله — یک دستور، هفت لایه، یک حکمِ صریح.

چرا این دستور؟ چون «ربات جواب نمی‌دهد» می‌تواند از هفت جای مختلف بیاید و
هر کدام نشانهٔ متفاوتی دارد: توکن، کلیدِ امن، نشانی، ثبتِ وب‌هوک، دسترس‌پذیری
از بیرون، پاسخِ خودِ اپلیکیشن، و تحویلِ واقعیِ بله. عیب‌یابیِ دستیِ این هفت
لایه روی هاستِ اشتراکی (بدونِ لاگِ زنده) ساعت‌ها وقت می‌برد و آخرش هم حدس
است. این دستور همه را پشتِ سرِ هم می‌سنجد و **می‌گوید کدام لایه شکسته و
دقیقاً چه کاری لازم است** — نه یک فهرستِ سبز/قرمز بی‌حکم.

    python manage.py bale_doctor               # یک‌بار: همه‌ی سنجه‌ها + حکم
    python manage.py bale_doctor --watch 120   # زنده: در بله /start بدهید و ببینید چه می‌شود
"""

from __future__ import annotations

import time
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandParser
from django.utils import timezone

from apps.notifications import probe
from apps.notifications.bale import BaleError, bale_is_configured

WEBHOOK_PATH = "/api/v1/notifications/bale/webhook/"


def _fingerprint(secret: str) -> str:
    """۶ کاراکترِ اولِ SHA-256ِ کلید؛ خودِ راز هیچ‌جا چاپ نمی‌شود."""
    import hashlib

    if not secret:
        return ""
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()[:6]


class Command(BaseCommand):
    """سنجشِ هفت‌لایه و حکمِ نهاییِ «آماده/شکسته»."""

    help = "تشخیصِ کاملِ کانالِ بله: از توکن تا تحویلِ واقعی، با حکمِ صریح"

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--watch",
            type=int,
            default=0,
            help="چند ثانیه وب‌هوک را زنده بپا (۵ ثانیه یک‌بار)؛ در این فاصله در بله /start بدهید.",
        )
        parser.add_argument(
            "--url", default="", help="نشانیِ دلخواه برای آزمون (پیش‌فرض: BALE_WEBHOOK_URL)"
        )
        parser.add_argument(
            "--fix",
            action="store_true",
            help="پیش از سنجش، وب‌هوک را با همین تنظیمات بازثبت کن (بدونِ دورریختنِ صف).",
        )
        parser.add_argument(
            "--nudge",
            action="store_true",
            help=(
                "از سمتِ خودِ بله یک آپدیتِ واقعی به وب‌هوک بفرست (deleteWebhook + setWebhook) "
                "تا معلوم شود بله اصلاً تحویل می‌دهد یا نه — بدونِ دخالتِ کاربر."
            ),
        )
        parser.add_argument(
            "--deliveries",
            type=int,
            default=0,
            metavar="N",
            help="N تحویلِ آخرِ بله را نشان بده (چه رسید، چه شد، پاسخ رفت یا نه).",
        )
        parser.add_argument(
            "--report",
            action="store_true",
            help="در پایان یک بلوکِ گزارشِ بی‌راز چاپ کن که می‌شود آن را کپی و فرستاد.",
        )

    # ── اجرا ────────────────────────────────────────────────────────────────
    def handle(self, *args: Any, **options: Any) -> None:
        del args
        url = self._url(str(options["url"]))
        verdicts: list[str] = []
        info: dict = {}

        if options.get("nudge"):
            self._nudge(url)
            return

        if options.get("deliveries"):
            self._deliveries(int(options["deliveries"]))
            return

        if options.get("fix"):
            self._title("۰) بازثبتِ وب‌هوک (--fix)")
            self._reregister(url)
            info = {}
            verdicts.append("وب‌هوک بازثبت شد؛ برای شاهدِ نهایی یک /start تازه بفرستید.")

        self._title("۱) توکنِ ربات")
        token_ok = self._token()

        self._title("۲) کلیدِ امنِ وب‌هوک")
        secret_ok = self._secret(verdicts)

        self._title("۳) نشانیِ وب‌هوک")
        self._url_report(url, verdicts)

        self._title("۴) ثبت در بله")
        info = self._registration(url, verdicts) or info

        self._title("۵) دسترس‌پذیری از بیرون (GET)")
        get_ok = self._reachable(url, verdicts)

        self._title("۶) پاسخِ خودِ اپلیکیشن (POST با کلید)")
        post_ok = self._loopback(url, verdicts)

        self._title("۷) تحویلِ واقعیِ بله")
        self._delivery(info, verdicts)

        self._verdict(
            verdicts, token_ok=token_ok, secret_ok=secret_ok, get_ok=get_ok, post_ok=post_ok
        )

        if options["report"]:
            self._report(url, info)

        if options["watch"]:
            self._watch(int(options["watch"]))

    def _nudge(self, url: str) -> None:
        """بله را وادار می‌کند همین حالا یک آپدیت به وب‌هوکِ ما تحویل بدهد.

        چرا این کلیدِ تشخیص است؟ تا وقتی بدانیم بله **هیچ** تحویلی نمی‌کند،
        نمی‌توان بین «کاربر پیام نفرستاده» و «بله تحویل نمی‌دهد» فرق گذاشت.
        `deleteWebhook` سپس `setWebhook` (بدونِ دورریختنِ صف) همان کاری است که
        کلاینت‌های رسمی برای بیدارکردن انجام می‌دهند؛ اگر پس از آن هم دفتر خالی
        بماند، مشکل قطعاً سمتِ بله/کاربر است نه کدِ ما.
        """
        from apps.notifications.models import BaleDeliveryLog

        self._title("بیدارکردنِ وب‌هوک از سمتِ بله (--nudge)")
        before = BaleDeliveryLog.objects.count()
        self._reregister(url)
        deadline = time.monotonic() + 60
        self.stdout.write("  تا ۶۰ ثانیه منتظرِ رسیدنِ آپدیت از بله می‌مانیم…")
        while time.monotonic() < deadline:
            if BaleDeliveryLog.objects.count() > before:
                last = BaleDeliveryLog.objects.all()[0]
                self._line(
                    True, f"بله تحویل داد! {last.handled} · پاسخ={'✓' if last.replied else '✗'}"
                )
                self.stdout.write("")
                self.stdout.write(self.style.SUCCESS("حکم: زنجیرهٔ بله کامل است."))
                return
            time.sleep(5)
        self._line(
            False,
            "بله در این ۶۰ ثانیه هیچ آپدیتی نفرستاد — یعنی ممکن است آپدیتِ معلقی "
            "در صف نبوده باشد. یک پیامِ تازه در بله بفرستید و `--watch 120` بزنید.",
        )

    def _deliveries(self, limit: int) -> None:
        """فهرستِ آخرین تحویل‌ها — «آیا بله اصلاً چیزی فرستاد؟»"""
        from apps.notifications.models import BaleDeliveryLog

        self._title(f"آخرین {limit} تحویلِ بله")
        rows = list(BaleDeliveryLog.objects.all()[:limit])
        if not rows:
            self._line(False, "دفتر خالی است ⇒ هیچ آپدیتی از بله به این اپ نرسیده.")
            return
        for row in rows:
            when = timezone.localtime(row.created_at).strftime("%m-%d %H:%M:%S")
            self._line(
                row.replied,
                f"{when} · {row.get_source_display()} · chat={row.chat_id} · "
                f"{row.handled} · پاسخ={'✓' if row.replied else '✗'}"
                + (f" · {row.note}" if row.note else ""),
            )

    def _reregister(self, url: str) -> None:
        """وب‌هوک را با همین تنظیمات بازثبت می‌کند، بی‌آنکه صف را دور بریزد."""
        from apps.notifications.bale import BaleError, _api

        secret = str(getattr(settings, "BALE_WEBHOOK_SECRET", "") or "").strip()
        payload: dict[str, object] = {"url": url}
        if secret:
            payload["secret_token"] = secret
        try:
            _api("deleteWebhook", {"drop_pending_updates": False})
            _api("setWebhook", payload)
        except BaleError as exc:
            self._line(False, f"بازثبت ناموفق: {exc}")
            return
        self._line(True, f"ثبت شد: {url}")

    def _report(self, url: str, info: dict) -> None:
        """بلوکِ گزارشِ بی‌راز — برای فرستادن به پشتیبانی/همکار."""
        secret = str(getattr(settings, "BALE_WEBHOOK_SECRET", "") or "")
        lines = [
            "──── گزارشِ کانالِ بله (بی‌راز) ────",
            f"app_webhook_url = {url}",
            f"bale_webhook_url = {info.get('url') or '—'}",
            f"secret_fingerprint = {_fingerprint(secret)}  (len={len(secret)})",
            f"pending_update_count = {info.get('pending_update_count', '—')}",
            f"last_error_message = {info.get('last_error_message') or '—'}",
            "──── پایان ────",
        ]
        self.stdout.write("")
        self.stdout.write("\n".join(lines))

    # ── لایه‌ها ─────────────────────────────────────────────────────────────
    def _token(self) -> bool:
        if not bale_is_configured():
            self._line(False, "BALE_BOT_TOKEN تنظیم نشده است.")
            return False
        from apps.notifications.bale import get_me

        try:
            me = get_me()
        except BaleError as exc:
            self._line(False, f"بله توکن را نپذیرفت: {exc}")
            return False
        self._line(True, f"ربات: @{me.get('username', '?')} ({me.get('name', '?')})")
        return True

    def _secret(self, verdicts: list[str]) -> bool:
        secret = str(getattr(settings, "BALE_WEBHOOK_SECRET", "") or "")
        if not secret:
            self._line(
                True, "کلید تنظیم نشده؛ وب‌هوک بدونِ کلید کار می‌کند ولی هر کسی می‌تواند آپدیت بفرستد."
            )
            verdicts.append(
                "کلیدِ وب‌هوک خالی است؛ برای امنیت `BALE_WEBHOOK_SECRET` را در `.env` بگذارید "
                "و بعد `manage.py bale_webhook` را دوباره بزنید."
            )
            return True
        if secret != secret.strip():
            # تلهٔ واقعیِ `.env` روی cPanel: فایل در ویندوز ویرایش شده و کلید
            # `\r` یا فاصلهٔ انتهایی دارد. بله آن را «کلیدِ دیگر» می‌بیند و ۴۰۳
            # می‌دهد، در حالی که با چشمِ انسان یکسان به نظر می‌رسد.
            self._line(False, "کلید فاصله یا \\r در ابتدا/انتها دارد ⇒ همهٔ تحویل‌ها ۴۰۳ می‌شوند.")
            verdicts.append("کلید را از `.env` پاک‌سازی کنید (بدونِ فاصله و \\r) و `--fix` را بزنید.")
        self._line(
            True, f"کلید تنظیم است ({len(secret)} کاراکتر؛ اثرِ انگشت: {_fingerprint(secret)})."
        )
        return True

    def _url_report(self, url: str, verdicts: list[str]) -> None:
        pinned = str(getattr(settings, "BALE_WEBHOOK_URL", "") or "").strip()
        if pinned:
            self._line(True, f"از `BALE_WEBHOOK_URL` خوانده شد: {url}")
        else:
            self._line(
                True,
                f"از `ALLOWED_HOSTS` ساخته شد: {url} — برای پرهیز از حدس، آن را در `.env` pin کنید.",
            )
        if not url.startswith("https://"):
            self._line(False, "بله فقط نشانیِ https می‌پذیرد.")
            verdicts.append("نشانی https نیست؛ `BALE_WEBHOOK_URL` را با https بگذارید.")

    def _registration(self, url: str, verdicts: list[str]) -> dict:
        from apps.notifications.bale import _api

        try:
            info = _api("getWebhookInfo").get("result") or {}
        except BaleError as exc:
            self._line(False, f"getWebhookInfo ناموفق: {exc}")
            return {}
        if not isinstance(info, dict):
            return {}
        registered = str(info.get("url") or "")
        if not registered:
            self._line(False, "هیچ وب‌هوکی ثبت نیست.")
            verdicts.append("وب‌هوک ثبت نیست: `manage.py bale_webhook` را بزنید.")
            return info
        if registered != url:
            self._line(False, f"نشانیِ ثبت‌شده با نشانیِ فعلی یکی نیست: {registered}")
            verdicts.append(
                "نشانیِ ثبت‌شده با `.env` یکی نیست؛ `manage.py bale_webhook` را یک‌بار دیگر بزنید."
            )
        else:
            self._line(True, f"ثبت‌شده روی: {registered}")
        pending = info.get("pending_update_count", 0)
        self._line(
            not pending,
            f"آپدیتِ در انتظار: {pending}"
            + ("" if not pending else " ← بله تحویل نمی‌دهد یا پاسخِ ما را نمی‌پذیرد"),
        )
        error = str(info.get("last_error_message") or "")
        if error:
            self._line(False, f"آخرین خطای تحویل: {error}")
            verdicts.append(self._error_hint(error))
        else:
            self._line(True, "بله هیچ خطای تحویلی گزارش نمی‌کند.")
        return info

    @staticmethod
    def _error_hint(error: str) -> str:
        """از متنِ خطای بله، کارِ درست را استخراج می‌کند."""
        if "403" in error or "Forbidden" in error:
            return "بله ۴۰۳ گرفت ⇒ کلیدِ `.env` با آنچه ثبت شده یکی نیست؛ `bale_webhook` را دوباره بزنید."
        if "404" in error:
            return "بله ۴۰۴ گرفت ⇒ نشانی به اپلیکیشن نمی‌رسد؛ `--url` را با دامنهٔ درست بدهید."
        if "400" in error:
            return (
                "بله ۴۰۰ گرفت ⇒ معمولاً `ALLOWED_HOSTS` دامنهٔ وب‌هوک را نمی‌پذیرد یا ��ی‌اس‌جی‌آی "
                "پاسخِ ناقص می‌دهد؛ دامنه را به `ALLOWED_HOSTS` اضافه کنید."
            )
        if "500" in error or "502" in error or "503" in error:
            return "بله ۵xx گرفت ⇒ خودِ اپلیکیشن هنگامِ پردازش خطا می‌دهد؛ لاگِ Django را ببینید."
        if "SSL" in error or "certificate" in error:
            return "خطای گواهی ⇒ گواهیِ دامنه برای بله معتبر نیست؛ دامنهٔ دیگر یا گواهیِ تازه."
        if "timeout" in error.lower():
            return "بله مهلتِ پاسخ را از دست داد (۵ ثانیه) ⇒ پاسخِ وب‌هوک کند است."
        return f"خطای تحویل: {error}"

    def _reachable(self, url: str, verdicts: list[str]) -> bool:
        ok, message = probe.health(url)
        self._line(ok, message)
        if not ok:
            verdicts.append(
                "مسیرِ سلامت پاسخِ اپلیکیشن نمی‌دهد؛ اگر در مرورگر باز می‌شود، شبکهٔ سرور "
                "نمی‌تواند دامنهٔ خودش را باز کند (hairpin) و این طبیعی است."
            )
        return ok

    def _loopback(self, url: str, verdicts: list[str]) -> bool:
        secret = str(getattr(settings, "BALE_WEBHOOK_SECRET", "") or "")
        ok, message = probe.loopback(url, secret)
        self._line(ok, message)
        if not ok:
            verdicts.append(message)
        return ok

    def _delivery(self, info: dict, verdicts: list[str]) -> None:
        """شاهدِ واقعی: آیا بله تا حالا چیزی را تحویل داده و ما پاسخ داده‌ایم؟

        «صف=۰ و بدونِ خطا» فقط می‌گوید بله **خطا نداشته**؛ نه اینکه چیزی رسیده
        باشد. روی همین سرور دقیقاً همین ابهام ماند: معلوم نبود بله تحویل داده و
        ما پاسخ داده‌ایم، یا کاربر هیچ پیامی نفرستاده. حالا دفترِ تحویل
        (`BaleDeliveryLog`) این را قطعی می‌کند.
        """
        from apps.notifications.models import BaleDeliveryLog

        if not info.get("url"):
            self._line(False, "تا وقتی وب‌هوک ثبت نشود، تحویلی هم نیست.")
            return
        if info.get("pending_update_count") or info.get("last_error_message"):
            self._line(False, "تحویلِ واقعی هنوز سالم نیست (صف/خطای بالا).")
            return

        recent = list(BaleDeliveryLog.objects.all()[:3])
        if not recent:
            self._line(
                False,
                "هیچ تحویلی در دفتر ثبت نیست ⇒ بله تا حالا چیزی به این اپ نفرستاده. "
                "در بله `/start` تازه بفرستید و همین دستور را دوباره بزنید.",
            )
            verdicts.append("هنوز هیچ تحویلی ثبت نشده؛ آزمونِ نهایی با یک /start تازه.")
            return
        last = recent[0]
        when = timezone.localtime(last.created_at).strftime("%H:%M:%S")
        self._line(
            last.replied,
            f"آخرین تحویل: {when} · {last.get_source_display()} · {last.handled} · "
            f"پاسخ {'ارسال شد' if last.replied else 'ارسال نشد'}",
        )
        if last.replied:
            self._line(True, f"شاهدِ قطعی: بله تحویل داد و پاسخ به گفتگوی {last.chat_id} رفت.")
        else:
            verdicts.append(
                "بله تحویل داد ولی ارسالِ پاسخ ناموفق بود (توکن/دسترسی ربات به آن گفتگو)."
            )

    def _verdict(
        self,
        verdicts: list[str],
        *,
        token_ok: bool,
        secret_ok: bool,
        get_ok: bool,
        post_ok: bool,
    ) -> None:
        self.stdout.write("")
        if token_ok and secret_ok and post_ok:
            self.stdout.write(self.style.SUCCESS("حکم: کانالِ بله آماده است."))
        elif token_ok and get_ok:
            self.stdout.write(
                self.style.WARNING(
                    "حکم: مسیر از بیرون باز است ولی زنجیره کامل نیست (بندهای بالا را ببینید)."
                )
            )
        else:
            self.stdout.write(self.style.ERROR("حکم: کانالِ بله آماده نیست."))
        for item in dict.fromkeys(verdicts):
            self.stdout.write(f"  → {item}")
        if not verdicts:
            self.stdout.write("  → کاری لازم نیست.")

    def _watch(self, seconds: int) -> None:
        """پایشِ زنده: کاربر `/start` می‌فرستد و تغییرِ وضعیت را همان لحظه می‌بیند."""
        from apps.notifications.bale import _api

        self.stdout.write("")
        self._title(f"پایشِ زنده به مدت {seconds} ثانیه — همین حالا در بله /start بدهید")
        deadline = time.monotonic() + seconds
        seen: tuple[int, str] = (-1, "")
        while time.monotonic() < deadline:
            try:
                info = _api("getWebhookInfo").get("result") or {}
            except BaleError:
                info = {}
            state = (
                int(info.get("pending_update_count", 0)),
                str(info.get("last_error_message") or ""),
            )
            if state != seen:
                seen = state
                self.stdout.write(
                    f"  · صف={state[0]} · خطا={state[1] or '—'} · {time.strftime('%H:%M:%S')}"
                )
            time.sleep(5)
        self.stdout.write("  پایانِ پایش.")

    # ── نمایش ───────────────────────────────────────────────────────────────
    def _title(self, text: str) -> None:
        self.stdout.write(self.style.MIGRATE_HEADING(text))

    def _line(self, ok: bool, text: str) -> None:
        mark = "✓" if ok else "✗"
        style = self.style.SUCCESS if ok else self.style.ERROR
        self.stdout.write(f"  {style(f'{mark} {text}')}")

    @staticmethod
    def _url(given: str) -> str:
        """نشانی: `--url`، بعد `BALE_WEBHOOK_URL`، بعد دامنهٔ `api.` از `ALLOWED_HOSTS`."""
        if given:
            return given
        pinned = str(getattr(settings, "BALE_WEBHOOK_URL", "") or "").strip()
        if pinned:
            return pinned
        hosts = [
            str(h).strip() for h in (getattr(settings, "ALLOWED_HOSTS", []) or []) if str(h).strip()
        ]
        chosen = next(
            (h for h in hosts if h.startswith("api.")), hosts[0] if hosts else "localhost"
        )
        scheme = "https" if not chosen.startswith(("localhost", "127.0.0.1")) else "http"
        return f"{scheme}://{chosen}{WEBHOOK_PATH}"

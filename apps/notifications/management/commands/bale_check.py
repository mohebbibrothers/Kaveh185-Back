"""بازرسیِ یک‌شاتِ کانالِ بله — «آیا از امشب می‌توانیم کد بفرستیم؟»

چرا لازم است؟ راه‌اندازیِ ربات چهار تکه دارد (توکن، نام کاربری، وب‌هوک/کران،
و اتصالِ کاربر) و اگر یکی جا بیفتد، همه‌چیز شبیه «کار می‌کند» به نظر می‌رسد
تا لحظه‌ای که کاربر واقعی ثبت‌نام می‌کند و کدش نمی‌آید. این دستور همان
لحظه را جلو می‌آورد: همهٔ چهار تکه را می‌سنجد و در یک گزارشِ کوتاه می‌گوید
چه چیزی کم است.

اجرا روی سرور (نه روی محیطِ توسعه):

    python manage.py bale_check
    python manage.py bale_check --send-to 09121234567   # ارسالِ پیامِ آزمایشی
"""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError, CommandParser

from apps.notifications.bale import BaleError, bale_is_configured, send_bale_message
from apps.notifications.models import BaleLinkCode, BaleSubscriber
from apps.notifications.services import bale_chat_for_phone, normalize_bale_phone


class Command(BaseCommand):
    """گزارشِ آمادگیِ کانالِ بله برای ارسالِ کدِ تأیید."""

    help = "بازرسیِ توکن، نام کاربری، وب‌هوک و اتصالِ کاربرانِ رباتِ بله"

    def add_arguments(self, parser: CommandParser) -> None:
        """گزینهٔ ارسالِ پیامِ آزمایشی به یک شمارهٔ وصل‌شده."""
        parser.add_argument(
            "--send-to",
            default="",
            help="شماره‌ای که به ربات وصل است؛ یک پیامِ آزمایشی برایش بفرست.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        """چهار سنجه را می‌سنجد و در پایان یک خط جمع‌بندی می‌دهد."""
        del args
        problems: list[str] = []

        # ۱) توکن
        if not bale_is_configured():
            raise CommandError(
                "BALE_BOT_TOKEN تنظیم نشده است. توکن را از @BotFather بگیر و در `.env` بگذار."
            )
        self._line(True, "توکنِ ربات تنظیم است.")

        # ۲) تماسِ واقعی با بله
        live_name = ""
        try:
            me = self._get_me()
        except BaleError as exc:
            self._line(False, f"تماس با بله برقرار نشد: {exc}")
            problems.append("ارتباط با tapi.bale.ai (فایروال/اینترنتِ سرور را بررسی کن).")
        else:
            live_name = me.get("username", "")
            self._line(True, f"ربات پاسخ داد: @{live_name} ({me.get('name', '')})")
            configured_name = str(getattr(settings, "BALE_BOT_USERNAME", "") or "").lstrip("@")
            if configured_name and live_name and configured_name != live_name:
                self._line(
                    False,
                    f"BALE_BOT_USERNAME «{configured_name}» با نامِ واقعیِ ربات «{live_name}» "
                    "یکی نیست؛ پیوندِ بله در فرمِ ثبت‌نام اشتباه نشان داده می‌شود.",
                )
                problems.append("BALE_BOT_USERNAME را با نامِ واقعیِ ربات هم‌سان کن.")

        # ۳) وب‌هوک / کران
        webhook_url = self._webhook_url()
        secret = str(getattr(settings, "BALE_WEBHOOK_SECRET", "") or "")
        if webhook_url:
            self._line(True, f"وب‌هوک روی بله تنظیم است: {webhook_url}")
        else:
            self._line(
                False,
                "وب‌هوک تنظیم نشده — پس باید cron خطِ `bale_inbox` را هر دقیقه اجرا کند.",
            )
        if not secret:
            self._line(
                False,
                "BALE_WEBHOOK_SECRET خالی است؛ وب‌هوک بدونِ کلید پذیرفته می‌شود "
                "(کسی می‌تواند پیامِ جعلی بفرستد و شمارهٔ دلخواه را به گفتگویی بچسباند).",
            )
            problems.append("یک BALE_WEBHOOK_SECRET تصادفی بگذار و در setWebhook هم همان را بده.")

        # ۴) اتصالِ کاربران
        linked = BaleSubscriber.objects.filter(is_active=True).count()
        pending = BaleLinkCode.objects.filter(consumed_at__isnull=True).count()
        self.stdout.write(f"  • کاربرانِ وصل‌شده: {linked} · کدِ اتصالِ صادرشدهٔ مصرف‌نشده: {pending}")
        if linked == 0:
            problems.append("هنوز هیچ کاربری ربات را شروع نکرده؛ یک ثبت‌نامِ آزمایشی بزن.")

        # ۵) پیامِ آزمایشی (اختیاری)
        target = normalize_bale_phone(str(options["send_to"] or ""))
        if target:
            chat_id = bale_chat_for_phone(target)
            if chat_id is None:
                self._line(False, f"شمارهٔ {target} به ربات وصل نیست؛ اول در بله /start بزن.")
                problems.append("برای پیامِ آزمایشی، اول همان شماره ربات را شروع کند.")
            else:
                res = send_bale_message(
                    chat_id, "پیامِ آزمایشی ✅ کانالِ بله برای کدِ تأیید آماده است."
                )
                self._line(res.ok, "پیامِ آزمایشی رفت." if res.ok else f"ارسال نشد: {res.detail}")

        self.stdout.write("")
        if problems:
            self.stdout.write(self.style.WARNING("هنوز آماده نیست — این‌ها را انجام بده:"))
            for i, item in enumerate(problems, 1):
                self.stdout.write(self.style.WARNING(f"  {i}) {item}"))
        else:
            self.stdout.write(self.style.SUCCESS("همه‌چیز آماده است؛ کدِ تأیید از بله می‌رود."))

    @staticmethod
    def _api_call(method: str, payload: dict[str, object] | None = None) -> dict[str, Any]:
        """تماسِ خام با بله (از راهِ خودِ ماژول، تا در تست جایگزین‌شدنی باشد)."""
        from apps.notifications import bale as bale_module

        return bale_module._api(method, payload)

    def _line(self, ok: bool, text: str) -> None:
        """یک سطرِ گزارش با علامتِ درست/نادرست."""
        mark = "✓" if ok else "✗"
        style = self.style.SUCCESS if ok else self.style.ERROR
        self.stdout.write(style(f"  {mark} {text}"))

    @staticmethod
    def _get_me() -> dict[str, Any]:
        """اطلاعاتِ ربات از خودِ ماژولِ کلاینت (تا در تست هم قابلِ جایگزینی باشد)."""
        from apps.notifications import bale as bale_module

        return bale_module.get_me()

    def _webhook_url(self) -> str:
        """نشانیِ وب‌هوکِ ثبت‌شده در بله (اگر بود)."""
        try:
            info = self._api_call("getWebhookInfo").get("result") or {}
        except BaleError:
            return ""
        return str(info.get("url") or "")

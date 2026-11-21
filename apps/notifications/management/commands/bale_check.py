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
        parser.add_argument(
            "--ping-webhook",
            action="store_true",
            help="به بله بگو یک آپدیتِ آزمایشی به وب‌هوک بفرستد و ببین پاسخ می‌گیرد یا نه.",
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
        webhook_url, webhook_info = self._webhook_state()
        secret = str(getattr(settings, "BALE_WEBHOOK_SECRET", "") or "")
        if webhook_url:
            self._line(True, f"وب‌هوک روی بله تنظیم است: {webhook_url}")
            # ⚠️ «ثبت شد» با «کار می‌کند» یکی نیست: بله اگر به نشانی نرسد، خطا را
            # فقط در getWebhookInfo نگه می‌دارد و آپدیت‌ها صف می‌شوند. اگر این را
            # نگوییم، کاربر «شروع» می‌زند و هیچ پاسخی نمی‌گیرد — بی‌صدا.
            last_error = str(webhook_info.get("last_error_message") or "")
            pending = int(webhook_info.get("pending_update_count") or 0)
            if last_error:
                self._line(False, f"بله نتوانسته به وب‌هوک برسد: {last_error}")
                problems.append(
                    "نشانیِ وب‌هوک به اپلیکیشنِ Django نمی‌رسد؛ `bale_webhook --delete` و "
                    "استفاده از کرانِ `bale_inbox`."
                )
            if pending:
                self._line(
                    False,
                    f"{pending} آپدیت در صفِ بله مانده (یعنی وب‌هوک پاسخ نداده).",
                )
                if not last_error:
                    problems.append("آپدیت‌های صف‌شده را با `bale_inbox` بخوان.")
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
            self.stdout.write(
                "    ↳ طبیعی است: هر کاربر اولین بار در صفحهٔ ثبت‌نام «کدِ اتصال» می‌گیرد "
                "و با فرستادنش در بله وصل می‌شود. برای آزمونِ خودتان همین حالا یک "
                "ثبت‌نامِ آزمایشی بزنید."
            )

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

        if options["ping_webhook"]:
            self._ping_webhook(problems)

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

    def _ping_webhook(self, problems: list[str]) -> None:
        """وب‌هوک را زنده می‌آزماید.

        راهِ استانداردِ بله: `setWebhook` با `drop_pending_updates` نه — بلکه
        یک `getWebhookInfo` کافی نیست. این‌جا از `sendMessage` استفاده نمی‌کنیم
        (کاربرِ واقعی لازم دارد)؛ در عوض `getWebhookInfo` را با یک آپدیتِ
        آزمایشیِ ساختگی نمی‌توان تحریک کرد. پس تنها راهِ صادقانه این است که
        بگوییم چه چیزی را باید دید: کافی است کاربر در بله `/start` بزند و
        `last_error_message` خالی بماند.
        """
        del problems
        self.stdout.write("")
        self.stdout.write(
            "  آزمونِ زندهٔ وب‌هوک: در بله به @kaveh185_bot پیام `/start` بدهید، "
            "بعد همین دستور را با `--ping-webhook` دوباره بزنید."
        )
        _, info = self._webhook_state()
        pending = int(info.get("pending_update_count") or 0)
        last_error = str(info.get("last_error_message") or "")
        if info.get("url") and not last_error and pending == 0:
            self._line(True, "بله آپدیتی در صف ندارد؛ وب‌هوک سالم به نظر می‌رسد.")
        elif last_error:
            self._line(False, f"آخرین خطای تحویل: {last_error}")
        else:
            self._line(False, f"{pending} آپدیت در صف مانده — یعنی پاسخ نگرفته است.")

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

    def _webhook_state(self) -> tuple[str, dict[str, Any]]:
        """نشانی و جزئیاتِ وب‌هوک از خودِ بله (نه از تنظیماتِ ما)."""
        try:
            info = self._api_call("getWebhookInfo").get("result") or {}
        except BaleError:
            return "", {}
        if not isinstance(info, dict):
            return "", {}
        return str(info.get("url") or ""), info

    def _webhook_url(self) -> str:
        """نشانیِ وب‌هوکِ ثبت‌شده در بله (اگر بود)."""
        try:
            info = self._api_call("getWebhookInfo").get("result") or {}
        except BaleError:
            return ""
        return str(info.get("url") or "")

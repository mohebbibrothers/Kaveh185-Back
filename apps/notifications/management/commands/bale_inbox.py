"""خواندنِ پیام‌های رباتِ بله و ثبتِ شمارهٔ کاربران — «دریافت‌کنندهٔ» کد تأیید.

چرا این دستور لازم است؟ بله برای ارسالِ پیام به یک نفر، `chat_id` می‌خواهد و
`chat_id` را فقط وقتی می‌دهد که خودِ کاربر با ربات شروع کرده باشد. پس سامانه
باید پیام‌های ورودی را بخواند و بفهمد «این chat_id مالِ کدام شماره است».

الگوی اجرا: هر ۳۰ ثانیه یک‌بار در cron (روی هاست اشتراکی هیچ سرورِ همیشه‌روشن
نداریم). هر اجرا فقط پیام‌های تازه را می‌خواند (`offset` در فایلِ کوچکی نگه
داشته می‌شود) و برای هر پیام:

  • اگر متن شمارهٔ همراه بود ⇒ همان را ثبت می‌کند و پیامِ تأیید می‌فرستد.
  • اگر `/start` بود ⇒ راهنمای کوتاه می‌فرستد.
  • هر چیز دیگر ⇒ یک راهنمای کوتاه (کاربر گم نشود).

⚠️ هیچ کدِ تأییدی این‌جا تولید نمی‌شود؛ این دستور فقط «نشانی» می‌سازد. کد
هنوز همان مسیرِ امنِ همیشگی را دارد (`create_and_send_otp`).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from apps.notifications.bale import BaleError, _api, bale_is_configured, send_bale_message
from apps.notifications.services import normalize_bale_phone, remember_bale_chat

OFFSET_FILE = Path("tmp") / "bale-offset.json"

WELCOME = (
    "سلام 👋\n"
    "به رباتِ مسابقهٔ کتاب‌خوانی هفتهٔ بسیج (حوزهٔ ۱۸۵ شهید کاوه) خوش آمدید.\n\n"
    "برای دریافتِ کدِ تأیید در سامانه، شمارهٔ همراه خود را همین‌جا بفرستید — "
    "مثلاً: 09121234567"
)
THANKS = (
    "ثبت شد ✅\n"
    "از این پس کدِ تأییدِ شما همین‌جا در بله ارسال می‌شود. "
    "حالا به سامانه برگردید و کد را وارد کنید."
)
NOT_A_PHONE = (
    "شمارهٔ همراه را به شکلِ 09121234567 بفرستید (بدونِ فاصله). "
    "اگر مطمئنید درست فرستاده‌اید، با پشتیبانیِ حوزه تماس بگیرید."
)


class Command(BaseCommand):
    """دریافتِ پیام‌های بله و ثبتِ شماره (یک‌بار در cron)."""

    help = "خواندنِ پیام‌های تازهٔ رباتِ بله و ثبتِ شمارهٔ کاربران"

    def add_arguments(self, parser: CommandParser) -> None:
        """گزینه‌ها: فقط نمایشِ لاگ، و بازنشانیِ offset."""
        parser.add_argument("--dry-run", action="store_true", help="فقط نشان بده، چیزی نفرست")
        parser.add_argument(
            "--reset-offset",
            action="store_true",
            help="offset را پاک کن (بار بعد از ابتدای صف می‌خواند).",
        )
        parser.add_argument(
            "--verbose",
            action="store_true",
            help="هر پیامِ دریافتی را چاپ کن.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        """اجرای یک دورِ خواندنِ صندوقِ ورودی."""
        del args
        if not bale_is_configured():
            raise CommandError(
                "BALE_BOT_TOKEN تنظیم نشده است. توکنِ ربات را از @BotFather بله بگیر "
                "و در .env بگذار."
            )

        OFFSET_FILE.parent.mkdir(parents=True, exist_ok=True)
        offset = 0 if options["reset_offset"] else self._read_offset()

        try:
            res = _api("getUpdates", {"offset": offset, "limit": 100, "timeout": 0})
        except BaleError as exc:
            raise CommandError(str(exc)) from exc

        updates = res.get("result") or []
        if not updates:
            if options["verbose"]:
                self.stdout.write("پیامِ تازه‌ای نبود.")
            return

        handled = 0
        for update in updates:
            message = (update.get("message") or {}) if isinstance(update, dict) else {}
            chat = message.get("chat") or {}
            chat_id = chat.get("id")
            text = str(message.get("text") or "").strip()
            sender = message.get("from") or {}
            last_update_id = int(update.get("update_id") or 0)

            if chat_id is None:
                continue

            phone = normalize_bale_phone(text)
            if options["verbose"]:
                self.stdout.write(f"update={last_update_id} chat={chat_id} text={text[:40]!r}")

            if phone:
                remember_bale_chat(
                    chat_id=int(chat_id),
                    phone_number=phone,
                    first_name=str(sender.get("first_name") or ""),
                    username=str(sender.get("username") or ""),
                )
                reply = THANKS
                handled += 1
            elif text.startswith("/start"):
                reply = WELCOME
            else:
                reply = NOT_A_PHONE

            if not options["dry_run"]:
                send_bale_message(int(chat_id), reply)

            if last_update_id:
                offset = max(offset, last_update_id + 1)

        if not options["dry_run"]:
            self._write_offset(offset)

        self.stdout.write(
            self.style.SUCCESS(f"{len(updates)} پیام خوانده شد · {handled} شمارهٔ تازه ثبت شد.")
        )
        if options["dry_run"]:
            self.stdout.write(self.style.WARNING("حالتِ آزمایشی: هیچ پاسخی ارسال نشد."))

    @staticmethod
    def _read_offset() -> int:
        """offset ذخیره‌شده را می‌خواند (اگر نبود، صفر)."""
        try:
            return int(json.loads(OFFSET_FILE.read_text("utf-8")).get("offset") or 0)
        except (FileNotFoundError, ValueError, json.JSONDecodeError):
            return 0

    @staticmethod
    def _write_offset(value: int) -> None:
        """offset تازه را ذخیره می‌کند تا پیامِ تکراری خوانده نشود."""
        OFFSET_FILE.parent.mkdir(parents=True, exist_ok=True)
        OFFSET_FILE.write_text(json.dumps({"offset": value}), encoding="utf-8")

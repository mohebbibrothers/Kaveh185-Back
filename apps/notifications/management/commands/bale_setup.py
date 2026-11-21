"""راه‌اندازیِ یک‌مرحله‌ایِ رباتِ بله — نوشتن در `.env`، تستِ تماس، و ثبتِ وب‌هوک.

چرا این دستور؟ تجربهٔ واقعیِ استقرار نشان داد سه جای اشتباه رخ می‌دهد و هر
سه تا بی‌صدا هستند:

  ۱) توکن در `.env` گذاشته نمی‌شود (یا در فایلِ اشتباهی) ⇒ «تنظیم نشده است».
  ۲) توکن در `.env` هست ولی **پروسهٔ در حال اجرا** آن را نخوانده ⇒ همان خطا
     با اینکه مقدار وجود دارد. (Passenger فقط با restart دوباره می‌خواند.)
  ۳) همه‌چیز درست است ولی وب‌هوک ثبت نشده ⇒ کاربر «شروع» می‌زند و هیچ
     پاسخی نمی‌گیرد، بدونِ هیچ خطایی.

این دستور هر سه را با یک اجرا می‌بندد. هیچ‌جا توکن چاپ نمی‌شود.

    python manage.py bale_setup --token 123456:ABC… [--secret auto] [--no-webhook]
    python manage.py bale_setup --status     # فقط بگو اکنون چه چیزی تنظیم است
"""

from __future__ import annotations

import contextlib
import os
import re
import secrets
import sys
from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError, CommandParser

ENV_KEYS = ("BALE_BOT_TOKEN", "BALE_BOT_USERNAME", "BALE_API_BASE", "BALE_WEBHOOK_SECRET")
WEBHOOK_PATH = "/api/v1/notifications/bale/webhook/"
TOKEN_PATTERN = re.compile(r"^\d{6,}:[A-Za-z0-9_-]{20,}$")

BLOCK_HEADER = "# ── رباتِ بله (کانالِ ارسالِ کدِ تأیید) ──"


class Command(BaseCommand):
    """نوشتنِ تنظیماتِ بله در `.env` و ثبتِ وب‌هوک، در یک مرحله."""

    help = "راه‌اندازیِ رباتِ بله: نوشتن در .env، تستِ تماس، ثبتِ وب‌هوک"

    def add_arguments(self, parser: CommandParser) -> None:
        """گزینه‌های توکن، کلید، و رفتار."""
        parser.add_argument("--token", default="", help="توکنِ ربات از @BotFather (پیشنهاد می‌شود)")
        parser.add_argument("--username", default="", help="نامِ کاربریِ ربات (اختیاری؛ از getMe)")
        parser.add_argument(
            "--secret",
            default="",
            help="کلیدِ وب‌هوک؛ `auto` یعنی خودت بساز (پیش‌فرض: auto)",
        )
        parser.add_argument("--no-webhook", action="store_true", help="وب‌هوک را ثبت نکن")
        parser.add_argument("--status", action="store_true", help="فقط وضعیتِ فعلی را نشان بده")
        parser.add_argument("--env-file", default="", help="مسیرِ .env (پیش‌فرض: کنارِ manage.py)")
        parser.add_argument(
            "--from-stdin",
            action="store_true",
            help="توکن را از ورودیِ استاندارد بخوان (تا در تاریخچهٔ شل نماند)",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        """اجرای راه‌اندازی."""
        del args
        env_path = Path(
            options["env_file"] or str(Path(getattr(settings, "BASE_DIR", ".")) / ".env")
        ).expanduser()

        if options["status"]:
            self._status(env_path)
            return

        token = str(options["token"] or "").strip()
        if options["from_stdin"] and not token:
            token = sys.stdin.readline().strip()
        if not token:
            raise CommandError(
                "توکن را بدهید: `--token <TOKEN>` یا `--from-stdin`.\n"
                "  نمونه: python manage.py bale_setup --from-stdin < token.txt"
            )

        # ── اعتبارسنجیِ شکلِ توکن پیش از هر کاری ─────────────────────────────
        if token.startswith("bot"):
            token = token[3:]
        if not TOKEN_PATTERN.match(token):
            raise CommandError(
                "شکلِ توکن درست نیست. باید شبیهِ «123456789:AAE…» باشد (عدد، دو نقطه، "
                "رشتهٔ بلندِ حروف/خط‌تیره). اگر از پنجرهٔ BotFather کپی کرده‌اید، "
                "احتمالاً برچسبِ اضافه هم کپی شده است."
            )

        # ── ۱) کلیدِ وب‌هوک ─────────────────────────────────────────────────
        secret = str(options["secret"] or "auto").strip()
        if secret == "auto":
            secret = secrets.token_hex(24)

        # ── ۲) نوشتن در .env (بدونِ چاپِ توکن) ───────────────────────────────
        self._write_env(env_path, token=token, secret=secret, username=str(options["username"]))

        # ── ۳) فعال‌سازی در همین پروسه تا تستِ زیر واقعی باشد ────────────────
        settings.BALE_BOT_TOKEN = token
        settings.BALE_WEBHOOK_SECRET = secret
        if options["username"]:
            settings.BALE_BOT_USERNAME = str(options["username"]).lstrip("@")
        os.environ.setdefault("BALE_BOT_TOKEN", token)

        # ── ۴) تستِ واقعیِ تماس با بله ───────────────────────────────────────
        from apps.notifications import bale as bale_module

        try:
            me = bale_module.get_me()
        except bale_module.BaleError as exc:
            raise CommandError(
                f"توکن در `.env` نوشته شد، ولی بله پاسخ نداد: {exc}\n"
                "  • اگر خطای شبکه است: فایروال/اینترنتِ سرور را بررسی کنید.\n"
                "  • اگر «unauthorized» بود: توکن باطل شده؛ از @BotFather توکنِ تازه بگیرید."
            ) from exc

        live_user = str(me.get("username") or "")
        self._ok(f"ربات پاسخ داد: @{live_user} ({me.get('name', '')})")

        if not options["username"] and live_user:
            self._write_env(env_path, token=token, secret=secret, username=live_user)
            self.stdout.write(f"  نامِ کاربری از خودِ بله نوشته شد: {live_user}")

        # ── ۵) ثبتِ وب‌هوک ──────────────────────────────────────────────────
        if options["no_webhook"]:
            self.stdout.write(
                "  وب‌هوک ثبت نشد (به‌خواستِ شما) ⇒ کرانِ `bale_inbox` را هر دقیقه اجرا کنید."
            )
        else:
            self._set_webhook()

        # ── ۶) یادآوریِ restart ─────────────────────────────────────────────
        self.stdout.write("")
        self.stdout.write(
            self.style.WARNING(
                "⚠️ پروسهٔ در حال اجرای سایت هنوز توکنِ قبلی را دارد. در cPanel از\n"
                "  Setup Python App → Restart (یا Passenger: touch tmp/restart.txt)\n"
                "  استفاده کنید تا کدِ تأیید برای کاربرانِ واقعی کار کند."
            )
        )
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("✓ راه‌اندازیِ بله تمام شد."))
        self.stdout.write(f"  کلیدِ وب‌هوک در `.env`: {env_path}")
        self.stdout.write("  اکنون `python manage.py bale_check` را بزنید تا همه‌چیز تأیید شود.")

    # ── کمکی‌ها ────────────────────────────────────────────────────────────
    def _ok(self, text: str) -> None:
        """سطرِ موفق."""
        self.stdout.write(self.style.SUCCESS(f"  ✓ {text}"))

    def _write_env(self, path: Path, *, token: str, secret: str, username: str) -> None:
        """نوشتن/به‌روزرسانیِ کلیدهای بله در `.env` بدونِ دست‌زدن به بقیهٔ خطوط."""
        if not path.exists():
            raise CommandError(
                f"فایلِ `{path}` پیدا نشد. اول `.env` را از نمونه بسازید:\n"
                f"  cp {path.with_suffix('.example')} {path}"
            )
        original = path.read_text(encoding="utf-8")
        lines = [ln for ln in original.splitlines() if not ln.startswith((*ENV_KEYS, BLOCK_HEADER))]

        values = {
            "BALE_BOT_TOKEN": token,
            "BALE_BOT_USERNAME": username,
            "BALE_API_BASE": str(getattr(settings, "BALE_API_BASE", "") or "https://tapi.bale.ai"),
            "BALE_WEBHOOK_SECRET": secret,
        }
        block = [BLOCK_HEADER] + [f"{k}={v}" for k, v in values.items() if v]
        new_text = "\n".join([ln for ln in lines if ln.strip()] + [""] + block) + "\n"

        # ⚠️ پشتیبان: اگر یک اشتباه در نوشتن رخ دهد، کاربر نباید تنظیماتِ قبلی را
        # از دست بدهد (این فایل رمزِ دیتابیس و کلیدهای امنیتی هم دارد).
        backup = path.with_name(path.name + ".bak")
        backup.write_text(original, encoding="utf-8")
        path.write_text(new_text, encoding="utf-8")
        with contextlib.suppress(OSError):  # روی فایل‌سیستم‌های بدونِ chmod
            path.chmod(0o600)
        self._ok(f"`.env` به‌روز شد (پشتیبان: {backup.name}) — توکن چاپ نمی‌شود.")

    def _set_webhook(self) -> None:
        """ثبتِ وب‌هوک با کلیدِ امن؛ خطاها ترجمه می‌شوند."""
        from apps.notifications import bale as bale_module

        url = self._webhook_url()
        payload = {
            "url": url,
            "max_connections": 40,
            "secret_token": str(getattr(settings, "BALE_WEBHOOK_SECRET", "") or ""),
        }
        try:
            res = bale_module._api("setWebhook", payload)
        except bale_module.BaleError as exc:
            self.stdout.write(
                self.style.WARNING(f"  وب‌هوک ثبت نشد ({exc}) ⇒ از کرانِ `bale_inbox` استفاده کنید.")
            )
            return

        if res.get("ok"):
            self._ok(f"وب‌هوک ثبت شد: {url}")
            return
        self.stdout.write(
            self.style.WARNING(
                f"  بله ثبتِ وب‌هوک را نپذیرفت: {res.get('description', '')} "
                "⇒ از کرانِ `bale_inbox` استفاده کنید."
            )
        )

    def _webhook_url(self) -> str:
        """نشانی از `BALE_WEBHOOK_URL`، وگرنه از دامنهٔ `api.` در `ALLOWED_HOSTS`."""
        explicit = str(getattr(settings, "BALE_WEBHOOK_URL", "") or "").strip()
        if explicit:
            return explicit
        hosts = [str(h).strip() for h in (getattr(settings, "ALLOWED_HOSTS", []) or [])]
        preferred = next((h for h in hosts if h.startswith("api.")), "")
        host = preferred or next(
            (h for h in hosts if h and not h.startswith(".") and h not in {"*", "localhost"}), ""
        )
        if not host:
            raise CommandError(
                "دامنه‌ای در ALLOWED_HOSTS نیست؛ نشانیِ وب‌هوک را در `.env` با "
                "`BALE_WEBHOOK_URL` بدهید."
            )
        return f"https://{host}{WEBHOOK_PATH}"

    def _status(self, env_path: Path) -> None:
        """وضعیتِ فعلی: مقدار در `.env` هست؟ پروسه می‌بیند؟ بله پاسخ می‌دهد؟"""
        from apps.notifications import bale as bale_module

        in_file = None
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8").splitlines():
                if line.startswith("BALE_BOT_TOKEN="):
                    in_file = line.split("=", 1)[1].strip()
        token_file = bool(in_file)
        token_proc = str(getattr(settings, "BALE_BOT_TOKEN", "") or "").strip()

        self.stdout.write(f"  • در `{env_path}`: {'هست' if token_file else 'نیست'}")
        self.stdout.write(f"  • در پروسهٔ فعلی: {'هست' if token_proc else 'نیست'}")
        if token_file and not token_proc:
            self.stdout.write(
                self.style.ERROR(
                    "  ⇒ مقدار در فایل هست ولی این پروسه آن را نخوانده: **restart** لازم است "
                    "(Setup Python App → Restart)."
                )
            )
        if token_proc:
            try:
                me = bale_module.get_me()
            except bale_module.BaleError as exc:
                self.stdout.write(self.style.ERROR(f"  • تماس با بله: ناموفق ({exc})"))
            else:
                self.stdout.write(
                    self.style.SUCCESS(f"  • تماس با بله: موفق (@{me.get('username')})")
                )

"""رباتِ بله به‌صورتِ سرویسِ همیشه‌بیدار (long-polling) — جایگزینِ کرانِ یک‌دقیقه‌ای.

چرا این ماژول؟ روی هاستِ واقعی ثابت شد که بله وب‌هوکِ این دامنه را **تحویل
نمی‌دهد**: ثبت می‌کند، `pending_update_count` صفر گزارش می‌کند، ولی ۱۷ آپدیت
واقعی در صف می‌مانند. در همان حال مسیرِ `getUpdates` بی‌نقص کار می‌کند.

کران هر دقیقه هم دو ضعف دارد: تأخیرِ تا ۶۰ ثانیه، و اجراهای هم‌پوشان که
می‌توانند یک آپدیت را دو بار پردازش کنند. راهِ حرفه‌ای همان کاری است که خودِ
کلاینت‌های رسمی می‌کنند: **long-polling** با `timeout=25` و قفلِ فایل تا دو
نمونه هرگز هم‌زمان اجرا نشوند.

    python manage.py bale_worker            # اجرای پیوسته (برای systemd/supervisor)
    python manage.py bale_worker --once     # یک دور (برای cronِ نجات‌بخش)
    python manage.py bale_worker --status   # آیا سرویس زنده است؟
"""

from __future__ import annotations

import contextlib
import json
import os
import signal
import time
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.utils import timezone

from apps.notifications.bale import BaleError, _api, bale_is_configured
from apps.notifications.services import record_bale_delivery
from apps.notifications.views import process_bale_message

OFFSET_FILE = Path("tmp") / "bale-offset.json"
HEARTBEAT_FILE = Path("tmp") / "bale-worker.heartbeat"
LOCK_FILE = Path("tmp") / "bale-worker.lock"
#: اگر کرانِ نجات‌بخش اجرا شود، تا این مدت دست نمی‌زند تا با سرویسِ اصلی
#: رقابت نکند (heartbeat تازه یعنی سرویس زنده است).
STALE_AFTER_SECONDS = 180


class _Lock:
    """قفلِ فایل — دو نمونهٔ هم‌زمان، دو بار پردازش و پاسخِ تکراری می‌سازند."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.handle: Any = None

    def acquire(self) -> bool:
        """قفل را می‌گیرد؛ اگر نمونهٔ دیگری زنده است `False`."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = self.path.open("w")
        try:
            if os.name == "nt":  # pragma: no cover - ویندوز در تولید نیست
                import msvcrt

                # mypy روی لینوکس `msvcrt` را نمی‌شناسد؛ رفتار همان قفلِ اجباری است.
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)  # type: ignore[attr-defined]
            else:
                import fcntl

                fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.handle.close()
            self.handle = None
            return False
        self.handle.write(str(os.getpid()))
        self.handle.flush()
        return True

    def release(self) -> None:
        if not self.handle:
            return
        try:
            if os.name != "nt":  # pragma: no cover - ویندوز در تولید نیست
                import fcntl

                fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
        finally:
            self.handle.close()
            self.handle = None


def _read_offset() -> int:
    """offset ذخیره‌شده (اگر نبود صفر)."""
    try:
        return int(json.loads(OFFSET_FILE.read_text("utf-8")).get("offset") or 0)
    except (FileNotFoundError, ValueError, json.JSONDecodeError):
        return 0


def _write_offset(value: int) -> None:
    """offset تازه — تا آپدیتِ مصرف‌شده دوباره پردازش نشود."""
    OFFSET_FILE.parent.mkdir(parents=True, exist_ok=True)
    OFFSET_FILE.write_text(json.dumps({"offset": value}), encoding="utf-8")


def _heartbeat(handled: int = 0) -> None:
    """نشانِ زندگی برای `--status` و برای کرانِ نجات‌بخش."""
    HEARTBEAT_FILE.parent.mkdir(parents=True, exist_ok=True)
    HEARTBEAT_FILE.write_text(
        json.dumps({"pid": os.getpid(), "at": timezone.now().isoformat(), "handled": handled}),
        encoding="utf-8",
    )


def _heartbeat_age() -> float:
    """چند ثانیه از آخرین نشانِ زندگی گذشته (بی‌نهایت اگر نبود)."""
    try:
        data = json.loads(HEARTBEAT_FILE.read_text("utf-8"))
        last = timezone.datetime.fromisoformat(data["at"])
    except (FileNotFoundError, ValueError, KeyError, TypeError):
        return float("inf")
    return (timezone.now() - last).total_seconds()


class Command(BaseCommand):
    """مصرفِ پیوستهٔ آپدیت‌های بله با long-polling و قفلِ تک‌نمونه."""

    help = "سرویسِ همیشه‌بیدارِ رباتِ بله (long-polling؛ جایگزینِ کرانِ یک‌دقیقه‌ای)"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._stopping = False

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--once", action="store_true", help="فقط یک دور بخوان و برگرد (کران).")
        parser.add_argument("--status", action="store_true", help="وضعیتِ سرویس را نشان بده.")
        parser.add_argument("--verbose", action="store_true", help="هر پیام را چاپ کن.")
        parser.add_argument("--quiet", action="store_true", help="فقط خطاها (برای systemd).")
        parser.add_argument(
            "--poll-timeout",
            type=int,
            default=25,
            help="ثانیه‌های انتظارِ long-polling در هر تماس (پیش‌فرض ۲۵).",
        )
        parser.add_argument(
            "--max-seconds",
            type=int,
            default=0,
            help="حداکثر زمانِ اجرا؛ ۰ = بی‌نهایت (§ برای ماشینِ میزبان وقت‌گیر نشود).",
        )
        parser.add_argument(
            "--idle-exit",
            type=int,
            default=0,
            help="اگر بیش از این ثانیه پیامی نیامد، خارج شو (۰ = هرگز).",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="قفل/قلبِ تازه را نادیده بگیر (برای وقتی سرویس مرده و قفل مانده).",
        )

    # ── اجرا ────────────────────────────────────────────────────────────────
    def handle(self, *args: Any, **options: Any) -> None:
        del args
        if not bale_is_configured():
            raise CommandError("BALE_BOT_TOKEN تنظیم نشده است؛ اول ربات را در `.env` بگذارید.")

        if options["status"]:
            self._status()
            return

        if not options["force"] and not options["once"] and _heartbeat_age() < STALE_AFTER_SECONDS:
            self.stdout.write(
                self.style.WARNING(
                    "یک نمونهٔ دیگر همین حالا زنده است (قلبِ تازه). برای اجرای دوم: `--force`."
                )
            )
            return

        lock = _Lock(LOCK_FILE)
        if not lock.acquire():
            self.stdout.write(
                self.style.WARNING(
                    "نمونهٔ دیگری قفل را در دست دارد؛ برای پرهیز از پاسخِ تکراری خارج می‌شوم."
                )
            )
            return

        self._install_signals()
        try:
            self._loop(options)
        finally:
            lock.release()

    def _install_signals(self) -> None:
        """با `SIGTERM`/`SIGINT` تمیز می‌ایستد تا وسطِ پردازش نصفه نماند."""

        def _stop(signum: int, frame: Any) -> None:
            self._stopping = True

        for name in ("SIGTERM", "SIGINT"):
            sig = getattr(signal, name, None)
            if sig is not None:  # pragma: no cover - در تست صدا زده نمی‌شود
                with contextlib.suppress(ValueError):
                    signal.signal(sig, _stop)

    def _loop(self, options: dict[str, Any]) -> None:
        """حلقهٔ بی‌پایان (یا محدود) با long-polling و بازگشتِ نمایی در خطا."""
        started = time.monotonic()
        last_activity = time.monotonic()
        offset = _read_offset()
        handled_total = 0
        backoff = 1.0
        _heartbeat(handled_total)

        while not self._stopping:
            # ⚠️ سقفِ زمان و خروجِ بی‌کاری باید **قبل** از هر `continue` سنجیده
            # شوند؛ وگرنه در خطای پیوستهٔ شبکه حلقه بی‌پایان می‌شود و سرویس
            # هیچ‌وقت آزاد نمی‌شود (در آزمون همین اتفاق افتاد).
            elapsed = time.monotonic() - started
            idle = time.monotonic() - last_activity
            if options["max_seconds"] and elapsed >= int(options["max_seconds"]):
                self._say(options, f"به سقفِ زمان رسیدم ({int(elapsed)}ث)؛ خارج می‌شوم.")
                break
            if options["idle_exit"] and idle >= int(options["idle_exit"]):
                self._say(options, f"{int(idle)}ث پیامی نیامد؛ خارج می‌شوم.")
                break

            try:
                # ⚠️ مهلتِ HTTP **باید** از مهلتِ سرور بیشتر باشد، وگرنه هر بار
                # `TimeoutError` می‌گیریم: بله تا `timeout` ثانیه منتظرِ پیامِ
                # تازه می‌ماند و ما زودتر قطع می‌کنیم — همان چیزی که در آزمونِ
                # اول رخ داد. یک ثانیه هم برای تأخیرِ شبکه اضافه می‌شود.
                res = _api(
                    "getUpdates",
                    {"offset": offset, "limit": 100, "timeout": int(options["poll_timeout"])},
                    timeout=self._http_timeout(int(options["poll_timeout"])),
                )
            except BaleError as exc:
                if not options["quiet"]:
                    hint = ""
                    if "TimeoutError" in str(exc):
                        hint = (
                            " ⇒ مهلتِ شبکه/پروکسی کمتر از مهلتِ long-polling است؛ "
                            "با `--poll-timeout 5` امتحان کنید."
                        )
                    self.stdout.write(self.style.ERROR(f"خطای تماس با بله: {exc}{hint}"))
                time.sleep(backoff)
                backoff = min(backoff * 2, 30.0)
                continue
            backoff = 1.0

            updates = res.get("result") or []
            if updates:
                offset = self._consume(updates, offset, options)
                last_activity = time.monotonic()
                handled_total += len(updates)
                _heartbeat(handled_total)

            if options["once"]:
                break

    @staticmethod
    def _http_timeout(poll_timeout: int) -> float:
        """مهلتِ HTTPِ هر تماس: کمی بیشتر از مهلتِ long-pollingِ سرور.

        ریاضیِ ساده، اثرِ بزرگ: اگر `poll_timeout=25` و مهلتِ HTTP هم ۶ ثانیه
        باشد (پیش‌فرضِ `_api`)، هر تماس قبل از رسیدنِ پاسخ قطع می‌شود و حلقه
        فقط «TimeoutError» می‌چاپد — بی‌آنکه هیچ پیامی خوانده شود.
        """
        return float(max(poll_timeout, 0) + 10)

    def _consume(self, updates: list[Any], offset: int, options: dict[str, Any]) -> int:
        """هر آپدیت را پردازش می‌کند و offset را جلو می‌برد (برگشتِ offsetِ تازه)."""
        for update in updates:
            if not isinstance(update, dict):
                continue
            last_update_id = int(update.get("update_id") or 0)
            message = update.get("message") or {}
            chat = message.get("chat") or {}
            chat_id = chat.get("id")
            text = str(message.get("text") or "").strip()

            if last_update_id:
                # ⚠️ offset **قبل** از پردازش جلو می‌رود: اگر همین‌جا کرش کنیم،
                # آپدیت دوباره پردازش نمی‌شود (پیامِ تکراری) — و اگر پردازش خطا
                # بدهد، خطا لاگ می‌شود و صف گیر نمی‌کند.
                offset = max(offset, last_update_id + 1)
                _write_offset(offset)

            if chat_id is None:
                continue
            if options["verbose"]:
                self.stdout.write(f"update={last_update_id} chat={chat_id} text={text[:40]!r}")

            try:
                result = process_bale_message(
                    chat={"id": int(chat_id), **{k: v for k, v in chat.items() if k != "id"}},
                    text=text,
                    sender=message.get("from") or {},
                )
            except Exception:
                import logging

                logging.getLogger(__name__).exception("پردازشِ آپدیتِ بله شکست خورد")
                record_bale_delivery(
                    chat_id=int(chat_id),
                    handled="error",
                    replied=False,
                    source="polling",
                    note="خطای پردازش",
                )
                continue

            from apps.notifications.bale import send_bale_message

            delivered = send_bale_message(int(chat_id), str(result["reply"])).ok
            record_bale_delivery(
                chat_id=int(chat_id),
                handled=str(result["handled"]),
                replied=bool(delivered),
                source="polling",
                note="" if delivered else "ارسالِ پاسخ ناموفق بود",
            )
        return offset

    def _status(self) -> None:
        """آیا سرویس زنده است؟ با شاهدِ سنِ نشانِ زندگی."""
        age = _heartbeat_age()
        lock = _Lock(LOCK_FILE)
        free = lock.acquire()
        if free:
            lock.release()
        if age == float("inf"):
            self.stdout.write(self.style.ERROR("✗ سرویس هرگز اجرا نشده (نشانِ زندگی نیست)."))
        elif age < STALE_AFTER_SECONDS:
            self.stdout.write(
                self.style.SUCCESS(f"✓ سرویس زنده است (آخرین نشان: {int(age)}ث پیش).")
            )
        else:
            self.stdout.write(self.style.ERROR(f"✗ سرویس مرده است (آخرین نشان: {int(age)}ث پیش)."))
        self.stdout.write(f"  قفلِ فایل: {'آزاد' if free else 'در دستِ نمونهٔ دیگر'}")

        try:
            info = _api("getWebhookInfo").get("result") or {}
        except BaleError:
            info = {}
        if info.get("url"):
            self.stdout.write(
                self.style.WARNING(
                    f"⚠️ وب‌هوک هنوز ثبت است ({info.get('url')}) — بله آپدیت‌ها را به آن "
                    "می‌فرستد و polling چیزی نمی‌بیند. `manage.py bale_webhook --delete`."
                )
            )
        else:
            self.stdout.write("  وب‌هوک ثبت نیست ⇒ polling آزاد است.")

    def _say(self, options: dict[str, Any], text: str) -> None:
        if not options["quiet"]:
            self.stdout.write(text)

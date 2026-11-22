"""نگه‌داشتنِ `bale_worker` زنده — برای هاستی که نه `sudo` دارد، نه systemd.

چرا این دستور؟ روی این هاست `sudo` وجود ندارد، systemd نیست و Supervisor هم
نصب نیست؛ پس `bale_worker` تنها با `nohup` دوام می‌آورد و هر ری‌استارتِ سرویس
یا بسته‌شدنِ نشست آن را می‌کُشد. `keepalive` همان نقشِ systemd را با ابزارهایی
که **هست** انجام می‌دهد:

* اگر سرویس زنده است: هیچ کاری نمی‌کند (بی‌صدا).
* اگر مرده است: با `setsid` و `nohup` دوباره بالا می‌آوردش تا به نشستِ شل
  وابسته نباشد.
* با `--install` یک خطِ کران (هر ۲ دقیقه) نصب می‌کند تا خودش همیشه اجرا شود.

    python manage.py keepalive              # فقط همین حالا (کران این را صدا می‌زند)
    python manage.py keepalive --install    # نصبِ خطِ کران + اجرای فوری
    python manage.py keepalive --stop       # توقفِ کامل (برای بازگشت به کرانِ ساده)
"""

from __future__ import annotations

# ⚠️ bandit: این تنها جای پروژه است که فرآیند می‌سازد و عمداً است — اجرای
# `manage.py bale_worker` و `crontab`. هیچ ورودیِ کاربر به این آرگومان‌ها
# نمی‌رسد؛ مسیرها از `settings.BASE_DIR` و `sys.executable` می‌آیند و
# `shell=False` است. `# nosec B404` همان تصمیم را صریح ثبت می‌کند.
import os  # nosec B404
import shutil
import subprocess  # nosec B404
import sys
from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandParser

from apps.notifications.management.commands import bale_worker as worker

BASE_DIR = Path(settings.BASE_DIR)
CRON_MARKER = "# kaveh185-bale-worker-keepalive"


class Command(BaseCommand):
    """نگهبانِ `bale_worker` با کران (جای‌گزینِ systemd روی هاستِ اشتراکی)."""

    help = "اگر سرویسِ بله مرده باشد دوباره بالا می‌آوردش (جای‌گزینِ systemd با کران)"

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--install", action="store_true", help="خطِ کران را نصب کن (هر ۲ دقیقه)."
        )
        parser.add_argument("--uninstall", action="store_true", help="خطِ کران را بردار.")
        parser.add_argument("--stop", action="store_true", help="اگر سرویس زنده است، متوقفش کن.")
        parser.add_argument("--verbose", action="store_true", help="همه‌چیز را بگو.")

    def handle(self, *args: Any, **options: Any) -> None:
        del args
        if options["install"]:
            self._install_cron()
            return
        if options["uninstall"]:
            self._uninstall_cron()
            return
        if options["stop"]:
            self._stop(options)
            return

        age = worker._heartbeat_age()
        if age < worker.STALE_AFTER_SECONDS:
            if options["verbose"]:
                self.stdout.write(
                    self.style.SUCCESS(f"✓ سرویس زنده است (آخرین نشان: {int(age)}ث پیش).")
                )
            return
        self._start(options)

    # ── کارها ───────────────────────────────────────────────────────────────
    def _python(self) -> str:
        """مسیرِ مفسر — همان که همین دستور با آن اجرا شده (venvِ درست)."""
        return sys.executable

    def _start(self, options: dict[str, Any]) -> None:
        """سرویس را واقعاً مستقل از نشستِ شل بالا می‌آورد (`setsid` + `nohup`)."""
        log_path = Path.home() / "kaveh185_bale_worker.log"
        command = [
            self._python(),
            str(BASE_DIR / "manage.py"),
            "bale_worker",
            "--quiet",
        ]
        log_file = log_path.open("ab")
        kwargs: dict[str, Any] = {
            "cwd": str(BASE_DIR),
            "stdout": log_file,
            "stderr": subprocess.STDOUT,
            "stdin": subprocess.DEVNULL,
        }
        # `setsid` سرویس را از نشستِ شل جدا می‌کند؛ بدونِ آن، بستنِ SSH
        # (با اینکه `nohup` هست) روی بعضی هاست‌ها سیگنالِ HUP به گروه می‌دهد.
        if hasattr(os, "setsid"):
            kwargs["start_new_session"] = True
        try:
            process = subprocess.Popen(command, **kwargs)  # noqa: S603  # nosec B603
        except OSError as exc:  # pragma: no cover - محیطی
            self.stderr.write(self.style.ERROR(f"اجرای سرویس ناموفق بود: {exc}"))
            return
        finally:
            # ⚠️ توصیفگرِ فایل را خودمان می‌بندیم؛ فرزند نسخهٔ خودش را دارد.
            # نگه‌داشتنِ بازِ آن، هشدارِ «unclosed file» و نشتِ توصیفگر می‌سازد.
            log_file.close()
        self.stdout.write(
            self.style.SUCCESS(f"↻ سرویسِ بله بالا آمد (pid={process.pid}) · لاگ: {log_path}")
        )
        if options["verbose"]:
            self.stdout.write("  برای پایش: `manage.py bale_worker --status`")

    def _stop(self, options: dict[str, Any]) -> None:
        """سرویسِ در حالِ اجرا را با SIGTERM متوقف می‌کند (خروجِ تمیز)."""
        import signal

        pid = self._running_pid()
        if not pid:
            self.stdout.write("سرویسی در حالِ اجرا نبود.")
            return
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:  # pragma: no cover - فرآیند مرده
            self.stdout.write(self.style.WARNING("فرآیند از قبل مرده بود."))
            return
        self.stdout.write(self.style.SUCCESS(f"■ سیگنالِ توقف به pid={pid} فرستاده شد."))
        if options["verbose"]:
            self.stdout.write("  برای اطمینان: `manage.py bale_worker --status`")

    @staticmethod
    def _running_pid() -> int:
        """pidِ سرویس از نشانِ زندگی (اگر تازه باشد)."""
        import json

        try:
            data = json.loads(worker.HEARTBEAT_FILE.read_text("utf-8"))
            pid = int(data.get("pid") or 0)
        except (FileNotFoundError, ValueError, TypeError, json.JSONDecodeError):
            return 0
        if pid <= 0:
            return 0
        try:
            os.kill(pid, 0)  # فقط بررسیِ وجود
        except OSError:
            return 0
        return pid

    # ── کران ────────────────────────────────────────────────────────────────
    def _cron_line(self) -> str:
        return (
            f"*/2 * * * * cd {BASE_DIR} && {self._python()} manage.py keepalive "
            f">> {Path.home()}/kaveh185_keepalive.log 2>&1 {CRON_MARKER}"
        )

    def _install_cron(self) -> None:
        """خطِ کران را اضافه می‌کند (تکراری نمی‌سازد) و بلافاصله اجرا می‌کند."""
        current = self._crontab()
        lines = [line for line in current.splitlines() if CRON_MARKER not in line]
        lines.append(self._cron_line())
        self._write_crontab("\n".join(lines) + "\n")
        self.stdout.write(self.style.SUCCESS("✓ خطِ کرانِ نگهبان نصب شد (هر ۲ دقیقه)."))
        self.stdout.write(f"  {self._cron_line()}")
        self._start({"verbose": True})

    def _uninstall_cron(self) -> None:
        """خطِ کرانِ نگهبان را برمی‌دارد."""
        current = self._crontab()
        kept = [line for line in current.splitlines() if CRON_MARKER not in line]
        self._write_crontab("\n".join(kept) + ("\n" if kept else ""))
        self.stdout.write(self.style.SUCCESS("✓ خطِ کرانِ نگهبان برداشته شد."))

    @staticmethod
    def _crontab() -> str:
        """محتوای فعلیِ crontab (خالی اگر نباشد)."""
        crontab = shutil.which("crontab") or "crontab"
        try:
            res = subprocess.run(  # noqa: S603  # nosec B603
                [crontab, "-l"], capture_output=True, text=True, timeout=15, check=False
            )
        except (OSError, subprocess.SubprocessError):  # pragma: no cover - محیطی
            return ""
        return res.stdout if res.returncode == 0 else ""

    @staticmethod
    def _write_crontab(content: str) -> None:
        """crontab را از stdinِ `crontab -` می‌نویسد (بدونِ نیاز به فایلِ موقت)."""
        crontab = shutil.which("crontab") or "crontab"
        try:
            subprocess.run(  # noqa: S603  # nosec B603
                [crontab, "-"],
                input=content,
                text=True,
                timeout=15,
                check=True,
                capture_output=True,
            )
        except (OSError, subprocess.SubprocessError) as exc:  # pragma: no cover - محیطی
            raise SystemExit(f"نوشتنِ crontab ناموفق بود: {exc}") from exc

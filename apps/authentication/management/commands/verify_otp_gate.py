"""دستور `verify_otp_gate` — اثباتِ زندهٔ اینکه درگاهِ «کد تأیید» واقعاً بسته است.

چرا این دستور؟ کاربر دو بار گزارش داد «بدونِ کد وارد آزمون شدم». حدس زدن
بی‌فایده است؛ باید در همان پروسه‌ای که Passenger سرو می‌کند، سه چیز را دید:

۱) **نسخهٔ کدِ بارگذاری‌شده** — اگر `git pull` انجام شده باشد ولی Passenger
   پروسه را ری‌استارت نکرده باشد، حافظه همان کدِ قدیمی را اجرا می‌کند. این
   دستور هشِ فایلِ سرویس و مجوزها را چاپ می‌کند تا با `git log` مقایسه شود.
۲) **فعال بودنِ `BALE_OTP_MANDATORY`** در همان پروسه.
۳) **رفتارِ واقعی**: یک کاربرِ ساختگیِ تأییدنشده می‌سازد، توکن می‌دهد و
   `POST /api/v1/exam/start/` را از مسیرِ کاملِ HTTP اجرا می‌کند و می‌بیند
   آیا مسدود می‌شود یا نه. سپس همه‌چیز را پاک می‌کند.

هیچ داده‌ای باقی نمی‌گذارد (`--keep` برای دیباگ) و هیچ رازی چاپ نمی‌کند.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandParser
from django.test import Client

SENTINELS = {
    "services.py": "verification_needed = bool(exam_config.require_otp_before_exam) or mandatory_verification",
    "permissions.py": 'mandatory = bool(getattr(settings, "BALE_OTP_MANDATORY", True))',
}


class Command(BaseCommand):
    """بررسی زندهٔ گیتِ OTP روی همان کدی که Passenger اجرا می‌کند."""

    help = "اثباتِ زندهٔ بسته بودنِ درگاهِ آزمون برای کاربرِ تأییدنشده + وضعیتِ کدِ بارگذاری‌شده."

    def add_arguments(self, parser: CommandParser) -> None:
        """گزینه‌های خطِ فرمان."""
        parser.add_argument(
            "--keep",
            action="store_true",
            help="کاربرِ آزمایشی را پاک نکن (پیش‌فرض: پاک شود).",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        """اجرای سه بررسی و چاپِ گزارشِ کوتاه و بدونِ راز."""
        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING("۱) کدی که همین حالا در حافظه اجرا می‌شود"))

        base = Path(settings.BASE_DIR) / "apps" / "authentication"
        stale: list[str] = []
        for name, needle in SENTINELS.items():
            path = base / name
            if not path.exists():  # pragma: no cover - ساختار همیشه هست
                stale.append(name)
                continue
            raw = path.read_bytes()
            digest = hashlib.sha256(raw).hexdigest()[:12]
            has_fix = needle.encode("utf-8") in raw
            mark = (
                self.style.SUCCESS("✔ رفعِ باگ داخلِ فایل هست")
                if has_fix
                else self.style.ERROR("✘ فایل کدِ قدیمی است")
            )
            if not has_fix:
                stale.append(name)
            self.stdout.write(f"  {name:18s} sha256={digest}  {mark}")

        if stale:
            self.stdout.write("")
            self.stdout.write(
                self.style.ERROR(
                    "فایل‌ها روی دیسک قدیمی‌اند ⇒ `git pull` روی همین مسیر انجام نشده است."
                )
            )

        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING("۲) تنظیماتِ امنیتیِ فعال"))
        mandatory = bool(getattr(settings, "BALE_OTP_MANDATORY", False))
        self.stdout.write(
            f"  BALE_OTP_MANDATORY = {mandatory}   "
            + (self.style.SUCCESS("✔") if mandatory else self.style.ERROR("✘ (باید True باشد)"))
        )

        from apps.exam.selectors import get_or_create_exam_configuration

        cfg = get_or_create_exam_configuration()
        self.stdout.write(
            f"  require_otp_before_exam (سوئیچِ ادمین) = {cfg.require_otp_before_exam}"
        )

        self.stdout.write("")
        self.stdout.write(
            self.style.MIGRATE_HEADING("۳) آزمونِ واقعی: آیا کاربرِ تأییدنشده مسدود می‌شود؟")
        )
        blocked = self._probe(keep=bool(options.get("keep")))

        self.stdout.write("")
        if blocked and not stale and mandatory:
            self.stdout.write(
                self.style.SUCCESS(
                    "نتیجه: درگاه بسته است. اگر مرورگر خلافِ این را نشان می‌دهد، "
                    "دلیلش نه بک‌اند است بلکه کش/نشستِ مرورگر یا نسخهٔ فرانت."
                )
            )
            return
        self.stdout.write(
            self.style.ERROR(
                "نتیجه: درگاه باز است یا کد قدیمی است — گزارشِ بالا را برای رفع بفرستید."
            )
        )
        raise SystemExit(1)

    def _probe(self, keep: bool) -> bool:
        """یک کاربرِ تأییدنشدهٔ موقت می‌سازد و ورودش به آزمون را می‌سنجد."""
        from apps.authentication.models import User
        from apps.authentication.services import issue_tokens_and_session
        from apps.mosques.models import Mosque

        phone = "09000000000"
        mosque = Mosque.objects.filter(is_active=True).first() or Mosque.objects.first()
        if mosque is None:  # pragma: no cover - نصبِ بدونِ مسجد
            self.stdout.write(self.style.WARNING("  مسجدی ثبت نشده؛ آزمونِ زنده ممکن نیست."))
            return False

        User.objects.filter(phone_number=phone).delete()
        user = User.objects.create_user(
            phone_number=phone,
            national_id="9990000018",  # رقمِ کنترل معتبر، متعلق به هیچ‌کس
            first_name="آزمون",
            last_name="درگاه",
            birth_date="1383-01-01",
            mosque=mosque,
            role="participant",
            is_phone_verified=False,
        )
        try:
            tokens = issue_tokens_and_session(user=user, request=None)
            # `testserver` در ALLOWED_HOSTS تولید نیست؛ از همان هاستِ واقعیِ
            # سایت استفاده می‌کنیم تا این آزمون دقیقاً همان مسیری باشد که
            # کاربرِ واقعی می‌رود (وگرنه ۴۰۰ِ DisallowedHost ما را گمراه می‌کند).
            host = next(
                (
                    h
                    for h in settings.ALLOWED_HOSTS
                    if h and h not in {"*", "localhost", "127.0.0.1"}
                ),
                "localhost",
            )
            client = Client(HTTP_HOST=host)
            res = client.post(
                "/api/v1/exam/start/",
                HTTP_AUTHORIZATION=f"Bearer {tokens['access']}",
                content_type="application/json",
                data="{}",
            )
            body = res.content.decode("utf-8", "replace")[:200]
            self.stdout.write(f"  POST /exam/start/ با کاربرِ تأییدنشده ⇒ HTTP {res.status_code}")
            blocked = res.status_code in {403, 401}
            if blocked:
                self.stdout.write(self.style.SUCCESS("  ✔ مسدود شد (انتظار)  ") + body[:120])
            else:
                self.stdout.write(self.style.ERROR("  ✘ وارد شد، در حالی که نباید!  ") + body[:120])
            return blocked
        finally:
            if not keep:
                user.delete()

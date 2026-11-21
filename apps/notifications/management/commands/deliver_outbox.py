"""تحویلِ پیام‌های معلقِ Outbox — با پشتیبانِ بله برای کدِ تأیید.

چرا لازم است؟ روی هاستِ اشتراکی Celery/worker همیشه‌روشن نداریم. تا امروز
پیام‌ها با `OUTBOX_INLINE_DISPATCH` همان لحظه و «درون‌خطی» فرستاده می‌شدند؛
اگر پنل پیامکی خطا می‌داد، رکورد در صف می‌ماند و **هیچ‌کس** دوباره سراغش
نمی‌رفت. این دستور همان «workerِ کوچک» است: هر چند دقیقه یک‌بار از cron
اجرا می‌شود و صف را خالی می‌کند.

ویژگیِ مهم: اگر `sms.otp` از راهِ پیامک نشد، **یک‌بار** از راهِ بله تلاش
می‌کند. یعنی کاربری که ربات را شروع کرده، حتی وقتی پنلِ پیامکی نداریم، کدش
را می‌گیرد؛ و کسی که پیامک دارد، همان مسیرِ اول را می‌رود.
"""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandParser
from django.utils import timezone

from apps.core.choices import OutboxStatus
from apps.core.models import OutboxMessage
from apps.core.outbox import relay_pending_outbox
from apps.notifications.services import send_otp_via_bale


class Command(BaseCommand):
    """پردازشِ صفِ پیام‌ها با یک لایهٔ پشتیبانِ بله."""

    help = "تحویلِ پیام‌های معلقِ Outbox (با پشتیبانِ بله برای کدِ تأیید)"

    def add_arguments(self, parser: CommandParser) -> None:
        """سقفِ پردازش و حالتِ آزمایشی."""
        parser.add_argument("--limit", type=int, default=100, help="حداکثر پیام در هر اجرا")
        parser.add_argument("--dry-run", action="store_true", help="فقط فهرست را نشان بده")
        parser.add_argument(
            "--retry-dead",
            action="store_true",
            help="پیام‌های مرده (DEAD) را هم دوباره در صف بگذار.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        """اجرای یک دورِ پردازش."""
        del args
        if options["retry_dead"]:
            revived = OutboxMessage.objects.filter(status=OutboxStatus.DEAD).update(
                status=OutboxStatus.PENDING,
                scheduled_at=timezone.now(),
                attempts=0,
            )
            self.stdout.write(f"{revived} پیامِ مرده دوباره در صف گذاشته شد.")

        pending = OutboxMessage.objects.filter(
            status__in=[OutboxStatus.PENDING, OutboxStatus.FAILED],
            scheduled_at__lte=timezone.now(),
        ).order_by("scheduled_at", "id")[: int(options["limit"])]

        if options["dry_run"]:
            for row in pending:
                self.stdout.write(f"  • [{row.status}] {row.topic} → {row.recipient}")
            self.stdout.write(self.style.WARNING("حالتِ آزمایشی: هیچ پیامی فرستاده نشد."))
            return

        report = relay_pending_outbox(limit=int(options["limit"]))

        # ── پشتیبانِ بله: پیام‌های کدِ تأییدی که هنوز نرفته‌اند ──────────────
        bale_sent = 0
        still_pending = OutboxMessage.objects.filter(
            topic="sms.otp",
            status__in=[OutboxStatus.PENDING, OutboxStatus.FAILED],
            scheduled_at__lte=timezone.now(),
        )[:50]
        for row in still_pending:
            payload = row.payload or {}
            phone = str(row.recipient or payload.get("phone_number") or "").strip()
            code = str(payload.get("code") or "").strip()
            if not phone or not code:
                continue
            result = send_otp_via_bale(phone_number=phone, code=code)
            if result.get("sent"):
                row.status = OutboxStatus.SENT
                row.processed_at = timezone.now()
                row.last_error = "delivered: bale"
                row.save(update_fields=["status", "processed_at", "last_error", "updated_at"])
                bale_sent += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"{report['processed']} پیام پردازش شد · {report['sent']} پیامک · "
                f"{bale_sent} کد از راهِ بله · {report['failed']} خطا."
            )
        )
        if bale_sent:
            self.stdout.write(
                self.style.WARNING(
                    "یادآوری: این کدها از بله رفتند چون پیامک در دسترس نبود "
                    f"(SMS_PROVIDER={getattr(settings, 'SMS_PROVIDER', 'console')})."
                )
            )

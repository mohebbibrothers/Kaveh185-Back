"""تست قفل بازهٔ واقعی مسابقه و تبدیل تاریخ شمسی.

چرا این تست‌ها وجود دارند
─────────────────────────
۱) مقدار پیش‌فرض `ends_at` در مدل، `now() + 7 روز` است — یعنی هر بار seed
   بزنید مهلت جابه‌جا می‌شود. این تست تضمین می‌کند دستور `set_exam_window`
   بتواند بازهٔ ثابت و صریح بنویسد، و تاریخ شمسی درست تفسیر شود.

۲) الگوریتم تبدیل شمسی→میلادی بدون وابستگی بیرونی نوشته شد. اگر اشتباه باشد،
   مهلت آزمون یک ماه جابه‌جا می‌شود و کسی متوجه نمی‌شود. پس با تاریخ‌های
   مرجع شناخته‌شده قفلش می‌کنیم.
"""

from __future__ import annotations

from datetime import timedelta
from io import StringIO
from pathlib import Path

import pytest
from django.core.management import CommandError, call_command
from django.test import Client
from django.utils import timezone

from apps.exam.management.commands.set_exam_window import _jalali_to_gregorian
from apps.exam.models import ExamConfiguration


class TestJalaliConversion:
    """تبدیل شمسی به میلادی با تاریخ‌های مرجعِ قابل بررسی."""

    @pytest.mark.parametrize(
        ("jalali", "gregorian"),
        [
            # نوروزها — سال‌های مختلف، شامل سال کبیسه
            ((1405, 1, 1), (2026, 3, 21)),
            ((1404, 1, 1), (2025, 3, 21)),
            ((1403, 1, 1), (2024, 3, 20)),
            ((1400, 1, 1), (2021, 3, 21)),
            # هفتهٔ بسیج ۱۴۰۵ — همان بازه‌ای که در مسابقه استفاده می‌شود
            ((1405, 8, 29), (2026, 11, 20)),
            ((1405, 9, 5), (2026, 11, 26)),
            # پایان سال و اول فروردین بعد
            ((1405, 12, 29), (2027, 3, 20)),
        ],
    )
    def test_known_dates(
        self, jalali: tuple[int, int, int], gregorian: tuple[int, int, int]
    ) -> None:
        assert _jalali_to_gregorian(*jalali) == gregorian

    def test_roundtrip_months_of_1405(self) -> None:
        """همهٔ ۱۲ ماه سال ۱۴۰۵ باید به تاریخ معتبر میلادی تبدیل شوند."""
        for month in range(1, 13):
            gy, gm, gd = _jalali_to_gregorian(1405, month, 1)
            assert 2026 <= gy <= 2027, f"ماه {month} → {gy}-{gm}-{gd}"
            assert 1 <= gm <= 12
            assert 1 <= gd <= 31


class TestSetExamWindowCommand:
    """دستور باید بازهٔ صریح بنویسد، نه بازهٔ نسبی."""

    def test_show_does_not_change_anything(self, db: None) -> None:
        config = ExamConfiguration.objects.create(singleton_key="show_test")
        before = (config.starts_at, config.ends_at)
        out = StringIO()
        call_command("set_exam_window", "--show", stdout=out)
        config.refresh_from_db()
        assert (config.starts_at, config.ends_at) == before
        assert "شروع" in out.getvalue()

    def test_jalali_window_is_written_exactly(self, db: None) -> None:
        ExamConfiguration.objects.create(singleton_key="kaveh185_main")
        out = StringIO()
        call_command(
            "set_exam_window",
            "--starts",
            "1405/08/29",
            "--ends",
            "1405/09/05",
            "--force",
            stdout=out,
        )
        config = ExamConfiguration.objects.get(singleton_key="kaveh185_main")
        tz = timezone.get_current_timezone()
        start_local = timezone.localtime(config.starts_at, tz)
        end_local = timezone.localtime(config.ends_at, tz)

        assert (start_local.year, start_local.month, start_local.day) == (2026, 11, 20)
        assert (start_local.hour, start_local.minute) == (0, 0)
        assert (end_local.year, end_local.month, end_local.day) == (2026, 11, 26)
        assert (end_local.hour, end_local.minute) == (23, 59)
        assert (config.ends_at - config.starts_at).days == 6

    def test_end_before_start_is_rejected(self, db: None) -> None:
        ExamConfiguration.objects.create(singleton_key="kaveh185_main")
        with pytest.raises(CommandError, match="بعد از شروع"):
            call_command("set_exam_window", "--starts", "1405/09/05", "--ends", "1405/08/29")

    def test_past_window_rejected_without_force(self, db: None) -> None:
        ExamConfiguration.objects.create(singleton_key="kaveh185_main")
        past = (timezone.now() - timedelta(days=30)).date().isoformat()
        earlier = (timezone.now() - timedelta(days=60)).date().isoformat()
        with pytest.raises(CommandError, match="گذشته"):
            call_command("set_exam_window", "--starts", earlier, "--ends", past)

    def test_garbage_date_is_rejected(self, db: None) -> None:
        ExamConfiguration.objects.create(singleton_key="kaveh185_main")
        with pytest.raises(CommandError, match="قابل تفسیر نیست"):
            call_command("set_exam_window", "--starts", "فردا", "--ends", "1405/09/05")

    def test_requires_both_bounds_or_show(self, db: None) -> None:
        ExamConfiguration.objects.create(singleton_key="kaveh185_main")
        with pytest.raises(CommandError, match="لازم است"):
            call_command("set_exam_window", "--starts", "1405/08/29")

    def test_time_component_is_honoured(self, db: None) -> None:
        ExamConfiguration.objects.create(singleton_key="kaveh185_main")
        call_command(
            "set_exam_window",
            "--starts",
            "1405/08/29T08:30",
            "--ends",
            "1405/09/05T18:00",
            "--force",
        )
        config = ExamConfiguration.objects.get(singleton_key="kaveh185_main")
        tz = timezone.get_current_timezone()
        start_local = timezone.localtime(config.starts_at, tz)
        assert (start_local.hour, start_local.minute) == (8, 30)


class TestDefaultIsRelative:
    """ثبت رفتار پیش‌فرض مدل تا کسی تصادفاً به آن تکیه نکند."""

    def test_defaults_are_relative_to_creation_time(self, db: None) -> None:
        """بازهٔ پیش‌فرض نسبت به «حالا» است، نه تاریخ ثابت مسابقه.

        این تست رفتار فعلی را مستند می‌کند: هر بار رکورد ساخته شود، مهلت
        جابه‌جا می‌شود. پس روی سرور واقعی باید `set_exam_window` اجرا شود.
        """
        before = timezone.now()
        config = ExamConfiguration.objects.create(singleton_key="relative_test")
        after = timezone.now()

        assert config.starts_at <= before
        # پایان حدوداً ۷ روز بعد است (با تلورانس چند ثانیه برای اجرای تست)
        expected = before + timedelta(days=7)
        assert abs((config.ends_at - expected).total_seconds()) < 60
        assert config.ends_at > after


class TestGregorianInput:
    """ورودی ISO میلادی هم باید کار کند — برای اسکریپت‌های خودکار."""

    def test_iso_dates_accepted(self, db: None) -> None:
        ExamConfiguration.objects.create(singleton_key="kaveh185_main")
        call_command(
            "set_exam_window",
            "--starts",
            "2026-11-20",
            "--ends",
            "2026-11-26",
            "--force",
        )
        config = ExamConfiguration.objects.get(singleton_key="kaveh185_main")
        tz = timezone.get_current_timezone()
        end_local = timezone.localtime(config.ends_at, tz)
        assert (end_local.year, end_local.month, end_local.day) == (2026, 11, 26)
        assert end_local.hour == 23


class TestBookFileEmbeddingHeaders:
    """فایل کتاب باید در iframeِ همان دامنه قابلِ نمایش باشد.

    ── چرا این تست؟
    صفحهٔ «مطالعهٔ کتاب» فایل را با `<iframe>` نشان می‌دهد. تا پیش از این
    اصلاح، `X-Frame-Options: DENY` سراسری روی همین پاسخ می‌نشست و خواننده
    فقط یک کادرِ سفید بود — یعنی مسیرِ مطالعه عملاً کار نمی‌کرد. این تست
    جلوی برگشتِ آن باگ را می‌گیرد: `SAMEORIGIN` (نه `DENY`) و
    `frame-ancestors 'self'` (نه `'none'`).
    """

    @pytest.mark.django_db
    def test_book_file_allows_same_origin_frame(self, tmp_path: Path) -> None:
        """پاسخِ فایل کتاب قاب‌شدن در همان دامنه را مجاز می‌کند."""
        from django.core.files.uploadedfile import SimpleUploadedFile

        from apps.exam.models import BookFile

        pdf = tmp_path / "book.pdf"
        pdf.write_bytes(b"%PDF-1.4\n%test\n")
        BookFile.objects.create(
            title="شهادت آیه‌ها",
            slug="embed-test",
            is_published=True,
            file=SimpleUploadedFile("book.pdf", pdf.read_bytes(), content_type="application/pdf"),
        )

        client = Client()
        response = client.get("/api/v1/exam/book/embed-test/file/")

        assert response.status_code == 200
        # بدنه را مصرف و بسته می‌کنیم؛ وگرنه فایلِ باز در `/tmp` باز می‌ماند
        # و pytest هشدارِ «resource warning» می‌دهد.
        b"".join(response.streaming_content)
        response.close()

        assert response["X-Frame-Options"] == "SAMEORIGIN"
        assert "frame-ancestors 'self'" in response["Content-Security-Policy"]

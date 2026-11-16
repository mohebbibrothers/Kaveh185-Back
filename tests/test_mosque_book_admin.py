"""تست‌های خودکارسازی مسجد و مدیریت کتاب.

چه چیزی را قفل می‌کنیم؟
───────────────────────
• کد مسجد خودکار ساخته می‌شود و ادامهٔ شمارهٔ موجود است (نه از ۱).
• ترتیب نمایش خودکار پر می‌شود و با `move_to` بی‌شکاف بازچینش می‌شود.
• شمارنده‌های ثبت‌نام/آزمون در فرم ادمین ورودی نیستند (`editable=False`).
• کتاب منتشرنشده به هیچ کسی سرو نمی‌شود؛ منتشرشده می‌شود.
"""

from __future__ import annotations

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse

from apps.exam.models import BookFile
from apps.mosques.models import Mosque

pytestmark = pytest.mark.django_db


# ── کد خودکار ────────────────────────────────────────────────────────────
def test_code_is_generated_automatically() -> None:
    """مسجد بدون کد ذخیره می‌شود و کد `MSQ-01` می‌گیرد."""
    mosque = Mosque.objects.create(name="مسجد آزمون یکم")
    mosque.refresh_from_db()
    assert mosque.code == "MSQ-01"


def test_code_continues_from_existing_maximum() -> None:
    """کد بعدی ادامهٔ بیشترین شمارهٔ موجود است، نه اول فهرست خالی."""
    Mosque.objects.create(name="مسجد الف", code="MSQ-07")
    mosque = Mosque.objects.create(name="مسجد ب")
    mosque.refresh_from_db()
    assert mosque.code == "MSQ-08"


def test_explicit_code_is_respected() -> None:
    """اگر ادمین کد بدهد، همان می‌ماند."""
    mosque = Mosque.objects.create(name="مسجد ج", code="CUSTOM-9")
    mosque.refresh_from_db()
    assert mosque.code == "CUSTOM-9"


# ── ترتیب خودکار ─────────────────────────────────────────────────────────
def test_display_order_is_automatic() -> None:
    """ترتیب نمایش به ترتیب افزودن پر می‌شود."""
    first = Mosque.objects.create(name="الف")
    second = Mosque.objects.create(name="ب")
    third = Mosque.objects.create(name="ج")
    for mosque, expected in ((first, 1), (second, 2), (third, 3)):
        mosque.refresh_from_db()
        assert mosque.display_order == expected


def test_move_to_reorders_without_gaps() -> None:
    """جابه‌جایی یک مسجد، ترتیب کل فهرست را بی‌شکاف بازنویسی می‌کند."""
    a = Mosque.objects.create(name="الف")
    b = Mosque.objects.create(name="ب")
    c = Mosque.objects.create(name="ج")

    c.move_to(1)  # ج به اول
    orders = list(Mosque.objects.order_by("display_order").values_list("name", flat=True))
    assert orders == ["ج", "الف", "ب"]
    assert sorted(Mosque.objects.values_list("display_order", flat=True)) == [1, 2, 3], (
        "ترتیب باید ۱..n و بی‌شکاف باشد"
    )
    del a, b, c


# ── شمارنده‌ها خواندنی‌اند ───────────────────────────────────────────────
def test_counters_are_not_editable() -> None:
    """شمارندهٔ ثبت‌نام و آزمون ورودی فرم نیستند."""
    for field_name in ("registered_count", "completed_exam_count"):
        field = Mosque._meta.get_field(field_name)
        assert field.editable is False, f"{field_name} نباید دستی قابل ویرایش باشد"


# ── کتاب ────────────────────────────────────────────────────────────────
def _pdf(name: str = "book.pdf") -> SimpleUploadedFile:
    """یک PDF مینیمال (فقط برای تست جریان فایل)."""
    return SimpleUploadedFile(name, b"%PDF-1.4\n%%EOF\n", content_type="application/pdf")


def test_unpublished_book_is_not_served() -> None:
    """کتاب پیش‌نویس حتی در API دیده نمی‌شود."""
    BookFile.objects.create(title="پیش‌نویس", slug="draft", file=_pdf())
    response = Client().get("/api/v1/exam/book/")
    assert response.status_code == 404


def test_published_book_metadata_is_public() -> None:
    """متادیتای کتاب منتشرشده بدون ورود در دسترس است."""
    BookFile.objects.create(
        title="شهادت آیه‌ها (۲)",
        slug="shahadat",
        file=_pdf(),
        is_published=True,
        page_count=48,
        story_count=30,
    )
    response = Client().get("/api/v1/exam/book/")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["title"] == "شهادت آیه‌ها (۲)"
    assert data["file_url"].endswith("/file/")
    assert data["format_label"] == "PDF"


def test_published_book_file_streams() -> None:
    """فایل کتاب منتشرشده با نوع درست و به‌صورت inline سرو می‌شود."""
    BookFile.objects.create(title="کتاب", slug="pub", file=_pdf(), is_published=True)
    response = Client().get("/api/v1/exam/book/pub/file/")
    assert response.status_code == 200
    assert response["Content-Type"] == "application/pdf"
    assert "inline" in response["Content-Disposition"]
    assert response["X-Robots-Tag"] == "noindex"
    assert b"".join(response.streaming_content).startswith(b"%PDF")


def test_book_view_counter_increments() -> None:
    """ثبت بازدید شمارنده را یک واحد بالا می‌برد."""
    book = BookFile.objects.create(title="کتاب", slug="counted", file=_pdf(), is_published=True)
    response = Client().post("/api/v1/exam/book/counted/view/")
    assert response.status_code == 200
    book.refresh_from_db()
    assert book.view_count == 1


# ── پنل ادمین ───────────────────────────────────────────────────────────
def test_admin_mosque_form_hides_counters() -> None:
    """فرم ادمین مسجد، شمارنده‌ها را نشان نمی‌دهد."""
    from django.contrib import admin as dj_admin

    from apps.mosques.admin import MosqueAdmin

    model_admin = MosqueAdmin(Mosque, dj_admin.site)
    for field_name in ("registered_count", "completed_exam_count"):
        assert (
            field_name not in model_admin.get_fields(None)
            or not Mosque._meta.get_field(field_name).editable
        )


def test_admin_move_url_exists() -> None:
    """مسیر جابه‌جایی در پنل ادمین ثبت شده است."""
    url = reverse("admin:mosques_mosque_move", args=[1, "up"])
    assert "/move/up/" in url


# ── منبع داستان: فقط ادمین، هرگز شرکت‌کننده ────────────────────────────────
def test_participant_payload_never_leaks_story_or_page() -> None:
    """قرارداد عمومی آزمون نباید نام داستان یا شمارهٔ صفحه را بفرستد.

    چرا این تست لازم است؟ فیلدهای `source_story`/`source_page` عمداً روی
    مدل `Question` هستند تا ادمین بداند پرسشش از کجای کتاب آمده. اما اگر
    روزی کسی سریالایزر آزمون را با `fields = "__all__"` بازنویسی کند،
    همان اطلاعات به مرورگر شرکت‌کننده می‌رود و «کدام داستان» لو می‌رود.
    این تست همان قفل است.
    """
    from apps.authentication.choices import UserRole
    from apps.authentication.models import User
    from apps.exam.models import Question
    from apps.exam.selectors import build_active_attempt_payload
    from apps.exam.services import start_or_resume_exam

    # بانک باید دست‌کم به اندازهٔ پرسش‌های یک آزمون پر باشد.
    questions = []
    for idx in range(5):
        q = Question.objects.create(
            text=f"پرسش آزمون منبع {idx + 1}",
            source_story="داستان ۱۲ — آب را که گل‌آلود کنی…" if idx == 0 else f"داستان {idx + 1}",
            source_page=41 if idx == 0 else 10 + idx,
        )
        for pos in (1, 2, 3, 4):
            q.options.create(
                option_number=pos, text=f"گزینهٔ {pos} پرسش {idx + 1}", is_correct=(pos == 1)
            )
        questions.append(q)

    mosque = Mosque.objects.create(name="مسجد منبع آزمون")

    user = User.objects.create_user(
        phone_number="09121110000",
        national_id="0009900012",
        first_name="شرکت",
        last_name="کننده",
        birth_date="1375-01-01",
        mosque=mosque,
        role=UserRole.PARTICIPANT,
        is_phone_verified=True,
    )
    attempt, _ = start_or_resume_exam(user=user)
    payload = build_active_attempt_payload(attempt)

    # کلیدهای هر پرسش، دقیقاً همان‌هایی که رابط کاربری می‌خواند
    allowed = {"question_number", "question_text", "selected_position", "is_answered", "options"}
    for item in payload["questions"]:
        assert set(item.keys()) == allowed

    flat = str(payload)
    assert "داستان ۱۲" not in flat
    assert "source_story" not in flat
    assert "source_page" not in flat

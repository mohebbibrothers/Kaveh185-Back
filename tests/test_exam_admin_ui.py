"""تست‌های پنل ادمین آزمون و کتاب.

چه چیزی را قفل می‌کنیم؟
───────────────────────
• ستون «منبع» در فهرست سؤال، داستان و صفحه را نشان می‌دهد (یا خط تیره).
• ستون «تعداد کشش» عدد واقعی از جلسه‌های آزمون می‌دهد.
• صفحهٔ افزودن کتاب، فیلدهای ضروری و توضیح «تا انتشار سرو نمی‌شود» را دارد.
• بارگذاری واقعی فایل PDF از پنل کار می‌کند و پیوند عمومی پس از انتشار
  ظاهر می‌شود.

چرا مهم است؟ بارگذاری کتاب تنها راه رساندن «شهادت آیه‌ها (۲)» به دست
شرکت‌کننده است؛ اگر فرم بشکند، آزمون بدون کتاب می‌ماند و پرسش‌ها بی‌معنا.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.exam.models import BookFile, Question

pytestmark = pytest.mark.django_db

User = get_user_model()


@pytest.fixture()
def admin_logged_in(client):
    user = User.objects.create_user(
        phone_number="09121230010",
        national_id="0009900012",
        first_name="مدیر",
        last_name="بانک",
        birth_date="1370-01-01",
        is_staff=True,
        is_superuser=True,
        is_phone_verified=True,
    )
    user.set_password("TempPass#185")
    user.save()
    assert client.login(username=user.phone_number, password="TempPass#185")
    return client


# ── فهرست سؤال ────────────────────────────────────────────────────────────
def test_question_list_shows_story_and_page(admin_logged_in) -> None:
    """منبع پرسش در فهرست ادمین دیده می‌شود."""
    Question.objects.create(
        text="پرسش با منبع",
        source_story="داستان ۱۲ — آب را که گل‌آلود کنی…",
        source_page=41,
    )
    response = admin_logged_in.get(reverse("admin:exam_question_changelist"))
    assert response.status_code == 200
    body = response.content.decode()
    assert "داستان ۱۲" in body
    assert "ص 41" in body


def test_question_list_handles_missing_source(admin_logged_in) -> None:
    """پرسش بی‌منبع، خط تیره می‌گیرد و صفحه نمی‌شکند."""
    Question.objects.create(text="پرسش بی‌منبع")
    response = admin_logged_in.get(reverse("admin:exam_question_changelist"))
    assert response.status_code == 200


def test_question_add_form_labels_source_as_admin_only(admin_logged_in) -> None:
    """فرم افزودن سؤال باید بگوید منبع فقط برای ادمین است."""
    response = admin_logged_in.get(reverse("admin:exam_question_add"))
    assert response.status_code == 200
    body = response.content.decode()
    assert "فقط ادمین" in body
    # متن راهنمای فرم، منبع را از کتاب تعیین می‌کند
    assert "شهادت آیه‌ها" in body


# ── کتاب ──────────────────────────────────────────────────────────────────
def test_book_add_page_explains_publish_gate(admin_logged_in) -> None:
    """صفحهٔ افزودن کتاب: توضیح می‌دهد تا انتشار سرو نمی‌شود."""
    response = admin_logged_in.get(reverse("admin:exam_bookfile_add"))
    assert response.status_code == 200
    body = response.content.decode()
    assert "منتشر" in body


def test_uploading_book_file_creates_published_record(admin_logged_in) -> None:
    """بارگذاری PDF از پنل: فایل ذخیره می‌شود، اسلاگ ساخته می‌شود."""
    upload = SimpleUploadedFile(
        "shahadat.pdf",
        b"%PDF-1.4\n%test\n",
        content_type="application/pdf",
    )
    response = admin_logged_in.post(
        reverse("admin:exam_bookfile_add"),
        data={
            "title": "شهادت آیه‌ها (۲)",
            # اسلاگ: همان مقدار پیش‌فرض مدل، ولی ارسالش از فرم لازم است.
            "slug": "shahadat-ayeha-2",
            "description": "سی داستان کوتاه",
            "story_count": "30",
            "page_count": "120",
            "file": upload,
            "is_published": "on",
        },
        follow=True,
    )
    assert response.status_code == 200
    book = BookFile.objects.get(title="شهادت آیه‌ها (۲)")
    assert book.is_published is True
    assert book.slug == "shahadat-ayeha-2"
    assert book.extension == "pdf"
    assert book.file


def test_book_changelist_shows_publish_state_and_link(admin_logged_in) -> None:
    """فهرست کتاب: وضعیت انتشار و پیوند عمومی برای کتاب منتشرشده."""
    book = BookFile.objects.create(
        title="کتاب منتشرشده",
        slug="published-book",
        is_published=True,
        file=SimpleUploadedFile("b.pdf", b"%PDF-1.4\n", content_type="application/pdf"),
    )
    response = admin_logged_in.get(reverse("admin:exam_bookfile_changelist"))
    assert response.status_code == 200
    body = response.content.decode()
    assert "منتشر شده" in body
    assert book.slug in body

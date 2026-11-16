"""تست‌های جریان عمومی کتاب مسابقه — همان مسیری که شرکت‌کننده می‌رود.

قراردادهایی که این‌جا قفل می‌شوند
─────────────────────────────────
• تا ادمین «منتشر شده» را تیک نزند، هیچ چیز عمومی سرو نمی‌شود (۴۰۴).
• فایل با `Content-Disposition: inline` می‌آید تا در مرورگر باز شود،
  نه این‌که کاربر مجبور به دانلود شود.
• `X-Robots-Tag: noindex` هست تا نسخهٔ قدیمی کتاب در گوگل ایندکس نشود.
• شمارندهٔ بازدید فقط با POST بالا می‌رود، نه با GET (پیش‌بارگذاری
  پیام‌رسان‌ها نباید عدد را باد کند).
"""

from __future__ import annotations

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework.test import APIClient

from apps.exam.models import BookFile

pytestmark = pytest.mark.django_db


def _book(*, published: bool = True, slug: str = "shahadat-2", name: str = "b.pdf"):
    return BookFile.objects.create(
        title="شهادت آیه‌ها (۲)",
        slug=slug,
        is_published=published,
        page_count=120,
        story_count=30,
        file=SimpleUploadedFile(name, b"%PDF-1.4\n%stub\n", content_type="application/pdf"),
    )


@pytest.fixture()
def api() -> APIClient:
    return APIClient()


def test_meta_returns_published_book(api) -> None:
    """کتاب منتشرشده: متادیتا با عنوان و شمارش داستان/صفحه."""
    _book()
    response = api.get(reverse("exam:book-meta"))
    assert response.status_code == 200
    payload = response.json()
    data = payload.get("data", payload)
    assert data["title"] == "شهادت آیه‌ها (۲)"
    assert data["story_count"] == 30
    assert data["page_count"] == 120


def test_meta_returns_404_when_nothing_published(api) -> None:
    """هیچ کتاب منتشرشده‌ای نیست ⇒ ۴۰۴ صادقانه، نه ۲۰۰ خالی."""
    response = api.get(reverse("exam:book-meta"))
    assert response.status_code == 404


def test_draft_book_never_leaks(api) -> None:
    """کتاب پیش‌نویس از مسیر عمومی دیده نمی‌شود."""
    _book(published=False, slug="draft-book")
    assert api.get(reverse("exam:book-meta")).status_code == 404
    assert api.get(reverse("exam:book-file", kwargs={"slug": "draft-book"})).status_code == 404


def test_file_is_served_inline_with_noindex(api) -> None:
    """فایل PDF با inline، نوع درست و noindex می‌آید."""
    _book()
    response = api.get(reverse("exam:book-file", kwargs={"slug": "shahadat-2"}))
    assert response.status_code == 200
    assert response["Content-Type"] == "application/pdf"
    assert response["Content-Disposition"].startswith("inline;")
    assert response["X-Robots-Tag"] == "noindex"
    assert response["Cache-Control"].startswith("public")
    # FileResponse دستهٔ فایل را باز نگه می‌دارد؛ بدون بستنش pytest هشدار
    # «unraisable exception» می‌دهد و تست بی‌دلیل قرمز می‌شود.
    response.close()


def test_unknown_slug_is_404(api) -> None:
    """slug ناشناخته ۴۰۴ می‌دهد."""
    _book()
    assert api.get(reverse("exam:book-file", kwargs={"slug": "nope"})).status_code == 404


def test_view_count_increments_only_on_post(api) -> None:
    """GET متادیتا شمارنده را بالا نمی‌برد؛ POST بازدید یکی اضافه می‌کند."""
    book = _book()
    api.get(reverse("exam:book-meta"))
    book.refresh_from_db()
    assert book.view_count == 0

    first = api.post(reverse("exam:book-view-count", kwargs={"slug": "shahadat-2"}))
    second = api.post(reverse("exam:book-view-count", kwargs={"slug": "shahadat-2"}))
    assert first.status_code == 200 and second.status_code == 200
    book.refresh_from_db()
    assert book.view_count == 2
    assert second.json().get("data", {}).get("view_count") == 2


def test_view_count_on_draft_is_404(api) -> None:
    """ثبت بازدید روی کتاب پیش‌نویس معنا ندارد و ۴۰۴ است."""
    _book(published=False, slug="draft-2")
    assert api.post(reverse("exam:book-view-count", kwargs={"slug": "draft-2"})).status_code == 404


def test_highest_updated_book_wins_when_multiple(api) -> None:
    """اگر دو کتاب منتشر شده باشد، تازه‌ترین (آخرین به‌روزرسانی) سرو می‌شود."""
    _book(slug="old-book", name="old.pdf")
    newer = _book(slug="new-book", name="new.pdf")
    BookFile.objects.filter(pk=newer.pk).update(title="کتاب تازه‌تر")
    data = api.get(reverse("exam:book-meta")).json()
    body = data.get("data", data)
    assert body["title"] == "کتاب تازه‌تر"

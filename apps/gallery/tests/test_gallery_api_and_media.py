"""تست‌های گالری محتوایی و سرو امنِ `/media/`.

── چرا این تست‌ها؟ ──────────────────────────────────────────────────────
گالری دو ریسک واقعی دارد که هیچ‌کدام با «چشم» گرفته نمی‌شود:

۱) **قرارداد پاسخ.** فرانت دقیقاً `leader`/`martyrs` و
   `caption_paragraphs` را می‌خواند. تغییر بی‌خبرِ شکلِ پاسخ، صفحهٔ اول را
   بی‌صدا خالی می‌کند — بدون هیچ خطایی در سرور.
۲) **سرو رسانه.** مسیری که از دیسک فایل می‌خواند، در نبودِ محدودیت
   می‌تواند هر فایلی را بیرون بدهد. تست، همان مرزها را می‌سنجد.
"""

from __future__ import annotations

import io
import tempfile
from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from PIL import Image
from rest_framework.test import APIClient

from apps.gallery.models import LeaderPortrait, Martyr
from apps.gallery.services import move_item


def _png_bytes(width: int = 8, height: int = 10) -> bytes:
    """یک PNG واقعیِ کوچک (نه بایتِ الکی) تا اعتبارسنجی pillow رد نشود."""
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), (20, 30, 60)).save(buffer, format="PNG")
    return buffer.getvalue()


def _leader(order: int = 0, caption: str = "") -> LeaderPortrait:
    upload = SimpleUploadedFile(f"leader-{order}.png", _png_bytes(), content_type="image/png")
    return LeaderPortrait.objects.create(
        image=upload,
        alt=f"تصویر آزمایشی {order}",
        caption=caption,
        source="منبع آزمایشی",
        order=order,
    )


@pytest.fixture()
def media_root() -> object:
    """پوشهٔ رسانهٔ موقت تا تست‌ها در `media/` واقعیِ پروژه کثیفی نگذارند.

    ⚠️ پوشه تا پایانِ تست زنده می‌ماند: `FileResponse` فایل را تنبل (lazy)
    باز می‌کند و اگر پوشه زیر دستش پاک شود، هنگام بستن خطای «Exception
    ignored in FileIO close» می‌دهد. پس پاسخ را در تست کامل می‌خوانیم.
    """
    with tempfile.TemporaryDirectory() as tmp, override_settings(MEDIA_ROOT=tmp):
        yield tmp


def _drain(response: object) -> bytes:
    """بدنهٔ پاسخِ جریانی را کامل می‌خواند و می‌بندد."""
    body = b"".join(getattr(response, "streaming_content", []) or [])
    close = getattr(response, "close", None)
    if callable(close):
        close()
    return body


# ── گالری: قرارداد پاسخ ────────────────────────────────────────────────────


@pytest.mark.django_db()
def test_leader_endpoint_returns_ordered_portraits_with_paragraphs(
    api_client: APIClient, media_root: object
) -> None:
    """ترتیب با `order` است و کلام به بندها شکسته می‌شود — همان شکلِ قرارداد."""
    _leader(order=2, caption="بند اول\n\nبند دوم")
    _leader(order=1, caption="")

    response = api_client.get("/api/v1/gallery/leader/")

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["count"] == 2
    first, second = payload["leader"]
    # `order` کوچک‌تر جلوتر (شناسه در پاسخ نیست؛ با alt می‌سنجیم)
    assert first["alt"] == "تصویر آزمایشی 1"
    assert second["alt"] == "تصویر آزمایشی 2"
    # کلام خالی ⇒ آرایهٔ خالی تا فرانت به متن پیش‌فرض برگردد (اصل صداقت)
    assert first["caption_paragraphs"] == []
    assert second["caption_paragraphs"] == ["بند اول", "بند دوم"]
    # آدرس تصویر باید مطلق و در مسیر رسانه باشد
    assert second["image_url"].startswith("http")
    assert "/media/gallery/leader/" in second["image_url"]


@pytest.mark.django_db()
def test_inactive_records_are_never_published(api_client: APIClient, media_root: object) -> None:
    """رکورد خاموش‌شده از پنل ادمین نباید در پاسخ عمومی بیاید."""
    hidden = _leader(order=0)
    hidden.is_active = False
    hidden.save(update_fields=["is_active"])
    _leader(order=1)

    payload = api_client.get("/api/v1/gallery/leader/").json()["data"]

    assert payload["count"] == 1
    assert payload["leader"][0]["alt"] == "تصویر آزمایشی 1"


@pytest.mark.django_db()
def test_empty_gallery_is_an_empty_list_not_an_error(
    api_client: APIClient, media_root: object
) -> None:
    """«خالی» یک پاسخ معتبر است؛ فرانت با آن بخش را پنهان می‌کند."""
    body = api_client.get("/api/v1/gallery/martyrs/").json()["data"]

    assert body == {"martyrs": [], "count": 0}


@pytest.mark.django_db()
def test_martyr_alt_falls_back_to_title(api_client: APIClient, media_root: object) -> None:
    """اگر ادمین alt را خالی بگذارد، تصویر بی‌متن نمی‌ماند."""
    upload = SimpleUploadedFile("m.png", _png_bytes(8, 8), content_type="image/png")
    Martyr.objects.create(image=upload, title="شهید نمونه", subtitle="زیرنویس", order=0)

    item = api_client.get("/api/v1/gallery/martyrs/").json()["data"]["martyrs"][0]

    assert item["alt"] == "شهید نمونه"
    assert item["title"] == "شهید نمونه"


@pytest.mark.django_db()
def test_bootstrap_carries_the_gallery(api_client: APIClient, media_root: object) -> None:
    """صفحهٔ اول باید گالری را در همان بستهٔ bootstrap بگیرد (یک درخواست، نه سه)."""
    _leader(order=0, caption="یک کلام")

    data = api_client.get("/api/v1/core/bootstrap/").json()["data"]

    assert data["gallery"]["leader"][0]["caption"] == "یک کلام"


@pytest.mark.django_db()
def test_move_item_reorders_and_normalises(api_client: APIClient, media_root: object) -> None:
    """دکمهٔ ↑/↓ ترتیب را عوض می‌کند؛ کش هم باطل می‌شود تا سایت فوراً تازه شود."""
    first = _leader(order=0)
    second = _leader(order=0)  # عمداً ترتیبِ تکراری — حالت واقعیِ دادهٔ قدیمی

    assert move_item(LeaderPortrait, second.pk, "up") is True

    ordered = list(LeaderPortrait.objects.order_by("order", "id"))
    assert ordered[0].pk == second.pk
    # ترتیب نرمال شده: ۰،۱ (نه اعداد تصادفی)
    assert [row.order for row in ordered] == [0, 1]
    # ردیف اول را نمی‌شود بالاتر برد
    assert move_item(LeaderPortrait, second.pk, "up") is False
    assert move_item(LeaderPortrait, 999_999, "down") is False
    del first


# ── سرو رسانه: مرزهای امنیتی ───────────────────────────────────────────────


@pytest.mark.django_db()
def test_media_serves_an_existing_image_with_cache_headers(
    api_client: APIClient, media_root: object
) -> None:
    """تصویر موجود: ۲۰۰ + نوع درست + کش یک‌هفته‌ای + nosniff."""
    record = _leader(order=0)

    response = api_client.get(f"/media/{record.image.name}")
    body = _drain(response)

    assert body[:8] == b"\x89PNG\r\n\x1a\n"  # یک PNG واقعی، نه صفحهٔ خطا
    assert response.status_code == 200
    assert response["Content-Type"] == "image/png"
    assert "max-age=604800" in response["Cache-Control"]
    assert response["X-Content-Type-Options"] == "nosniff"


@pytest.mark.django_db()
def test_media_refuses_non_image_and_missing_files(
    api_client: APIClient, media_root: object
) -> None:
    """پسوند غیرتصویری (حتی اگر فایل باشد) و فایل ناموجود ⇒ ۴۰۴."""
    root = Path(str(media_root))
    (root / "secret.txt").write_text("top secret", encoding="utf-8")

    assert api_client.get("/media/secret.txt").status_code == 404
    assert api_client.get("/media/gallery/leader/missing.png").status_code == 404

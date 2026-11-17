"""تست‌های گالری محتوایی و سرو امنِ `/media/`.

── چرا این تست‌ها نوشته شدند؟ ───────────────────────────────────────────
گالری تازه اضافه شده بود و دو ریسک واقعی داشت که هیچ تستی نمی‌گرفت:

۱) **قرارداد پاسخ.** فرانت دقیقاً انتظار `leader`/`martyrs` و
   `caption_paragraphs` را دارد. تغییرِ بی‌خبرِ شکلِ پاسخ، صفحهٔ اول را
   بی‌صدا خالی می‌کند (بدون هیچ خطایی در سرور).
۲) **سرو رسانه.** مسیری که فایل از دیسک می‌خواند، در نبودِ محدودیت
   می‌تواند هر فایلی را بیرون بدهد. تست‌ها همان مرزهای واقعی را
   می‌سنجند: فقط تصویر، فقط زیر مسیر رسانه، و ۴۰۴ برای بقیه.
"""

from __future__ import annotations

import io
import tempfile

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from PIL import Image
from rest_framework.test import APIClient

from apps.gallery.models import LeaderPortrait, Martyr


def _png_bytes(width: int = 8, height: int = 10) -> bytes:
    """یک PNG واقعیِ کوچک می‌سازد (نه بایتِ الکی) تا اعتبارسنجی pillow رد نشود."""
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

    ⚠️ پوشه تا پایانِ تست زنده می‌ماند. اگر در خودِ تست پاک شود،
    `FileResponse` که فایل را تنبل (lazy) باز می‌کند هنگام بستن، خطای
    «Exception ignored in FileIO close» می‌دهد — همان چیزی که اول این‌جا
    رخ داد. پس محتوای پاسخ را در تست می‌خوانیم (`_drain`) و پاک‌سازی را
    به teardown می‌سپاریم.
    """
    with tempfile.TemporaryDirectory() as tmp, override_settings(MEDIA_ROOT=tmp):
        yield tmp


def _drain(response: object) -> bytes:
    """بدنهٔ پاسخِ جریانی را کامل می‌خواند و می‌بندد (وگرنه فایل باز می‌ماند)."""
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
    """ترتیب با `order` است و کلام به بندها شکسته می‌شود — همان چیزی که فرانت می‌خواند."""
    _leader(order=2, caption="بند اول\n\nبند دوم")
    _leader(order=1, caption="")

    response = api_client.get("/api/v1/gallery/leader/")

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["count"] == 2
    first, second = payload["leader"]
    # `order` کوچک‌تر جلوتر — شناسه در پاسخ نیست، پس با alt می‌سنجیم
    assert first["alt"] == "تصویر آزمایشی 1"
    assert second["alt"] == "تصویر آزمایشی 2"
    # کلام خالی ⇒ آرایهٔ خالی، تا فرانت به متن پیش‌فرض برگردد (اصل صداقت)
    assert first["caption_paragraphs"] == []
    assert second["caption_paragraphs"] == ["بند اول", "بند دوم"]
    # آدرس تصویر باید مطلق و از مسیر رسانه باشد
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


# ── سرو رسانه: مرزهای امنیتی ───────────────────────────────────────────────


@pytest.mark.django_db()
def test_media_serves_an_existing_image_with_cache_headers(
    api_client: APIClient, media_root: object
) -> None:
    """تصویر موجود: ۲۰۰ + نوع درست + کش یک‌هفته‌ای + nosniff."""
    record = _leader(order=0)
    url = f"/media/{record.image.name}"

    response = api_client.get(url)
    body = _drain(response)

    assert body[:8] == b"\x89PNG\r\n\x1a\n"  # یک PNG واقعی برگشته، نه HTML خطا
    assert response.status_code == 200
    assert response["Content-Type"] == "image/png"
    assert "max-age=604800" in response["Cache-Control"]
    assert response["X-Content-Type-Options"] == "nosniff"


@pytest.mark.django_db()
def test_media_refuses_non_image_suffix(api_client: APIClient, media_root: object) -> None:
    """پسوند غیرتصویری حتی اگر فایل روی دیسک باشد هم ۴۰۴ می‌گیرد."""
    from pathlib import Path

    from django.conf import settings

    root = Path(str(settings.MEDIA_ROOT))
    (root / "secret.txt").write_text("top secret", encoding="utf-8")

    assert api_client.get("/media/secret.txt").status_code == 404
    # فایلِ موجود ولی ممنوع، نباید لو برود
    assert api_client.get("/media/gallery/leader/missing.png").status_code == 404

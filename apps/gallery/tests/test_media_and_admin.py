"""تست‌های سرو رسانه، امنیت مسیر، و پنل ادمین گالری."""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

import pytest
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from PIL import Image

from apps.gallery.models import LeaderPortrait, Martyr


def _jpeg(name: str = "a.jpg") -> SimpleUploadedFile:
    """تصویر JPEG واقعی در حافظه."""
    buf = io.BytesIO()
    Image.new("RGB", (40, 40), (10, 20, 30)).save(buf, format="JPEG")
    buf.seek(0)
    return SimpleUploadedFile(name, buf.read(), content_type="image/jpeg")


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    """کش خالی برای هر تست."""
    cache.clear()


@pytest.fixture(autouse=True)
def _isolated_media(settings, tmp_path: Path) -> Path:
    """رسانهٔ هر تست در پوشهٔ موقت خودش — مخزن و `media/` واقعی آلوده نمی‌شوند."""
    root = tmp_path / "media"
    root.mkdir(parents=True, exist_ok=True)
    settings.MEDIA_ROOT = str(root)
    return root


# ── سرو رسانه ──────────────────────────────────────────────────────────────
@pytest.mark.django_db
def test_media_serves_an_uploaded_image_even_when_debug_is_off(settings) -> None:
    """مهم‌ترین تست این فایل: روی هاست `DEBUG=False` است و تصویر باید بیاید."""
    settings.DEBUG = False
    portrait = LeaderPortrait.objects.create(image=_jpeg("hero.jpg"), caption="کلام")

    response = Client().get(portrait.image.url)

    assert response.status_code == 200
    assert response["Content-Type"] == "image/jpeg"
    assert "immutable" in response["Cache-Control"]
    assert response["X-Content-Type-Options"] == "nosniff"
    response.close()  # آزادکردن دستهٔ فایل، تا هشدار «فایل باز مانده» ندهد


@pytest.mark.django_db
def test_media_refuses_non_image_files(_isolated_media: Path) -> None:
    """فایل غیرتصویری (اینجا: یک `.txt`) هرگز سرو نمی‌شود."""
    (_isolated_media / "secret.txt").write_text("دادهٔ حساس", encoding="utf-8")

    response = Client().get("/media/secret.txt")

    assert response.status_code == 404


@pytest.mark.django_db
def test_media_refuses_path_traversal(settings) -> None:
    """`../` در مسیر، ۴۰۴ می‌دهد و چیزی از بیرون ریشه نمی‌خواند."""
    response = Client().get("/media/../../etc/passwd")
    assert response.status_code in {404, 400}

    response = Client().get("/media/..%2F..%2Fetc%2Fpasswd")
    assert response.status_code in {404, 400}


@pytest.mark.django_db
def test_media_returns_404_for_a_missing_file() -> None:
    """فایل ناموجود ⇒ ۴۰۴ تمیز، نه ۵۰۰."""
    assert Client().get("/media/gallery/leader/does-not-exist.jpg").status_code == 404


# ── ادمین ──────────────────────────────────────────────────────────────────
@pytest.mark.django_db
def test_admin_root_loads(admin_client: Any) -> None:
    """ریشهٔ پنل بالا می‌آید (یعنی اپ گالری سالم ثبت شده است)."""
    response = admin_client.get("/secure-kaveh185-admin/")
    assert response.status_code in {200, 302}


@pytest.mark.django_db
def test_move_service_reorders_without_gaps() -> None:
    """جابه‌جایی، ترتیب را از ۱ و بی‌شکاف بازچینش می‌کند."""
    a = Martyr.objects.create(image=_jpeg("a.jpg"), title="الف")
    b = Martyr.objects.create(image=_jpeg("b.jpg"), title="ب")
    c = Martyr.objects.create(image=_jpeg("c.jpg"), title="ج")

    from apps.gallery.services import move_item

    move_item(item=c, position=1)

    assert [m.title for m in Martyr.all_objects.order_by("display_order")] == ["ج", "الف", "ب"]
    assert [m.display_order for m in Martyr.all_objects.order_by("display_order")] == [1, 2, 3]
    a.refresh_from_db()
    b.refresh_from_db()
    assert a.display_order == 2 and b.display_order == 3


@pytest.mark.django_db
def test_deactivating_an_item_invalidates_the_cache(client: Client) -> None:
    """خاموش‌کردن یک قلم در ادمین، فوراً از خروجی عمومی حذفش می‌کند."""
    portrait = LeaderPortrait.objects.create(image=_jpeg(), caption="کلام")
    assert len(client.get("/api/v1/gallery/leader/").json()["data"]["items"]) == 1

    from apps.gallery.services import invalidate_gallery

    portrait.is_active = False
    portrait.save()
    invalidate_gallery("test.deactivate")

    assert client.get("/api/v1/gallery/leader/").json()["data"]["items"] == []

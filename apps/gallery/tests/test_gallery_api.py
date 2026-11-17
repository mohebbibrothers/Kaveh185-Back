"""تست‌های API گالری — قرارداد پاسخ، ترتیب، آدرس مطلق، و حالات خالی.

این تست‌ها سه چیز را تضمین می‌کنند که در نسخهٔ اول غایب بودند:

۱) **قراردادِ دقیق.** فرانت به کلیدهای مشخصی تکیه می‌کند؛ اگر یکی حذف یا
   تغییر نام داده شود، این‌جا می‌شکند، نه در مرورگر کاربر.
۲) **آدرس مطلق.** با `request` ساخته می‌شود، پس در `bootstrap` و مسیر
   مستقل یکسان است.
۳) **حالت خالی.** هیچ داده‌ای ⇒ آرایهٔ خالی، هرگز خطا. فرانت روی همین
   تکیه می‌کند تا بخش را پنهان کند.
"""

from __future__ import annotations

import io
from typing import Any

import pytest
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image
from rest_framework.test import APIClient

from apps.gallery.models import LeaderPortrait, Martyr


def _image_file(name: str = "portrait.jpg", size: tuple[int, int] = (60, 60)) -> SimpleUploadedFile:
    """ساخت یک تصویر JPEG واقعی در حافظه (بدون فایل باینری در مخزن)."""
    buf = io.BytesIO()
    Image.new("RGB", size, (30, 60, 120)).save(buf, format="JPEG")
    buf.seek(0)
    return SimpleUploadedFile(name, buf.read(), content_type="image/jpeg")


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    """هر تست با کش خالی شروع شود (گالری از SWR استفاده می‌کند)."""
    cache.clear()


@pytest.fixture
def client() -> APIClient:
    """کلاینت عمومی بدون احراز هویت."""
    return APIClient()


@pytest.mark.django_db
def test_gallery_endpoint_is_empty_and_friendly_when_nothing_is_stored(
    client: APIClient,
) -> None:
    """بدون داده: پاسخ موفق با دو آرایهٔ خالی — نه خطا، نه دادهٔ ساختگی."""
    response = client.get("/api/v1/gallery/")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"] == {"leader": [], "martyrs": []}


@pytest.mark.django_db
def test_leader_payload_matches_the_contract_the_frontend_relies_on(client: APIClient) -> None:
    """همهٔ کلیدهای قرارداد موجودند و کلام به پاراگراف شکسته شده."""
    LeaderPortrait.objects.create(
        image=_image_file(),
        caption="پاراگراف اول.\nپاراگراف دوم.",
        source="از بیانات رهبر انقلاب",
    )

    response = client.get("/api/v1/gallery/leader/")
    assert response.status_code == 200
    body = response.json()

    assert body["data"]["count"] == 1
    item = body["data"]["items"][0]
    assert set(item) == {
        "id",
        "image_url",
        "alt",
        "caption",
        "caption_paragraphs",
        "source",
        "show_in_box",
        "order",
    }
    assert item["caption_paragraphs"] == ["پاراگراف اول.", "پاراگراف دوم."]
    assert item["source"] == "از بیانات رهبر انقلاب"
    # آدرس باید مطلق باشد؛ فرانت و پیام‌رسان‌ها به آن تکیه می‌کنند.
    assert item["image_url"].startswith("http")
    assert "/media/gallery/leader/" in item["image_url"]


@pytest.mark.django_db
def test_alt_falls_back_to_the_caption_when_the_admin_leaves_it_empty(
    client: APIClient,
) -> None:
    """متن جانشین خالی ⇒ از کلام ساخته می‌شود، نه رشتهٔ خالی."""
    LeaderPortrait.objects.create(image=_image_file(), caption="کلام نمونه")

    item = client.get("/api/v1/gallery/leader/").json()["data"]["items"][0]
    assert item["alt"] == "کلام نمونه"


@pytest.mark.django_db
def test_inactive_items_never_reach_the_public_api(client: APIClient) -> None:
    """قلم غیرفعال در ادمین می‌ماند و در سایت دیده نمی‌شود."""
    LeaderPortrait.objects.create(image=_image_file(), caption="پیدا", is_active=True)
    LeaderPortrait.objects.create(image=_image_file(), caption="پنهان", is_active=False)

    body = client.get("/api/v1/gallery/leader/").json()
    assert body["data"]["count"] == 1
    assert body["data"]["items"][0]["caption"] == "پیدا"


@pytest.mark.django_db
def test_order_is_the_real_display_order_not_the_creation_time(client: APIClient) -> None:
    """ترتیب با جابه‌جایی عوض می‌شود و همان ترتیب در API دیده می‌شود."""
    first = LeaderPortrait.objects.create(image=_image_file(), caption="اول")
    second = LeaderPortrait.objects.create(image=_image_file(), caption="دوم")
    assert [i["order"] for i in client.get("/api/v1/gallery/leader/").json()["data"]["items"]] == [
        1,
        2,
    ]

    second.move_to(1)

    from apps.gallery.services import invalidate_gallery

    invalidate_gallery("test.reorder")
    captions = [i["caption"] for i in client.get("/api/v1/gallery/leader/").json()["data"]["items"]]
    assert captions == ["دوم", "اول"]
    assert [i["order"] for i in client.get("/api/v1/gallery/leader/").json()["data"]["items"]] == [
        1,
        2,
    ]
    first.refresh_from_db()
    assert first.display_order == 2


@pytest.mark.django_db
def test_martyrs_payload_and_fallback_alt(client: APIClient) -> None:
    """قرارداد نوار شهدا: عنوان، زیرنویس، و altِ ساخته‌شده از هر دو."""
    Martyr.objects.create(
        image=_image_file("m.jpg"), title="سیدشهدای مقاومت", subtitle="شهید محمود کاوه"
    )

    item = client.get("/api/v1/gallery/martyrs/").json()["data"]["items"][0]
    assert set(item) == {"id", "image_url", "title", "subtitle", "alt", "order"}
    assert item["title"] == "سیدشهدای مقاومت"
    assert item["alt"] == "سیدشهدای مقاومت — شهید محمود کاوه"


@pytest.mark.django_db
def test_bootstrap_carries_the_gallery_with_absolute_urls(client: APIClient) -> None:
    """صفحهٔ اول با یک درخواست، گالری را هم می‌گیرد — با آدرس مطلق."""
    LeaderPortrait.objects.create(image=_image_file(), caption="کلام")
    Martyr.objects.create(image=_image_file("m.jpg"), title="عنوان")

    body = client.get("/api/v1/core/bootstrap/").json()["data"]

    assert "gallery" in body
    assert len(body["gallery"]["leader"]) == 1
    assert len(body["gallery"]["martyrs"]) == 1
    assert body["gallery"]["leader"][0]["image_url"].startswith("http")


@pytest.mark.django_db
def test_show_in_box_is_exposed_so_the_frontend_can_filter(client: APIClient) -> None:
    """پرچم «در باکس دیده شود» در خروجی هست تا فرانت باکس را جدا فیلتر کند."""
    LeaderPortrait.objects.create(image=_image_file(), caption="در باکس", show_in_box=True)
    LeaderPortrait.objects.create(image=_image_file(), caption="فقط گالری", show_in_box=False)

    items: list[dict[str, Any]] = client.get("/api/v1/gallery/leader/").json()["data"]["items"]
    assert [i["show_in_box"] for i in items] == [True, False]

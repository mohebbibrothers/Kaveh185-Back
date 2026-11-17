"""تست‌های پنل ادمین، اعتبارسنجی مدل، و دستور `seed_gallery`.

پوشش این فایل روی سه ناحیهٔ پرخطر است:

۱) **دکمه‌های ▲▼.** این‌ها مسیرهای واقعی HTTP‌اند؛ اگر نامِ URL یا
   دسترسی عوض شود، ادمین در پنل با ۴۰۴ روبه‌رو می‌شود و هیچ تست دیگری
   نمی‌فهمد.
۲) **اعتبارسنجی تصویر.** یک فایل غیرتصویری نباید وارد گالری شود.
۳) **دستور seed.** هم باید روی پایگاه‌دادهٔ خالی کار کند، هم دوباره‌اجرا
   بی‌خطر باشد، و هم وقتی تصاویر نیستند استقرار را نشکند.
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

import pytest
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from PIL import Image

from apps.authentication.models import User
from apps.gallery.models import LeaderPortrait, Martyr


def _jpeg(name: str = "a.jpg") -> SimpleUploadedFile:
    """تصویر JPEG واقعی در حافظه."""
    buf = io.BytesIO()
    Image.new("RGB", (32, 32), (90, 30, 30)).save(buf, format="JPEG")
    buf.seek(0)
    return SimpleUploadedFile(name, buf.read(), content_type="image/jpeg")


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    """کش خالی برای هر تست."""
    cache.clear()


@pytest.fixture()
def staff_client(db: Any) -> Any:
    """کلاینت لاگین‌شده به پنل ادمین."""
    from django.test import Client

    user = User.objects.create_superuser(phone_number="09120000001", password="Xx!12345678")
    client = Client()
    client.force_login(user)
    return client


# ── اعتبارسنجی مدل ─────────────────────────────────────────────────────────
@pytest.mark.django_db
def test_model_rejects_a_non_image_file(_isolated_media: Path) -> None:
    """فایل غیرتصویری در `ImageField` رد می‌شود."""
    portrait = LeaderPortrait(image=SimpleUploadedFile("x.txt", b"hello"))
    with pytest.raises(ValidationError):
        portrait.clean()


@pytest.mark.django_db
def test_model_rejects_a_missing_image() -> None:
    """بدون تصویر، اعتبارسنجی خطا می‌دهد (تصویر الزامی است)."""
    with pytest.raises(ValidationError):
        Martyr(title="بی‌تصویر").clean()


@pytest.mark.django_db
def test_paragraphs_split_the_caption_into_clean_lines() -> None:
    """کلام به پاراگراف‌های غیرخالی شکسته می‌شود — خطوط خالی حذف می‌شوند."""
    portrait = LeaderPortrait(caption="اول\n\n  دوم  \n")
    assert portrait.paragraphs() == ["اول", "دوم"]


@pytest.mark.django_db
def test_effective_alt_prefers_the_admin_value_then_falls_back() -> None:
    """`alt` ادمین مقدم است؛ اگر نبود از متن ساخته می‌شود."""
    assert LeaderPortrait(alt="عینک", caption="متن").effective_alt() == "عینک"
    assert LeaderPortrait(caption="متن").effective_alt() == "متن"
    assert LeaderPortrait().effective_alt()


@pytest.mark.django_db
def test_str_is_readable_in_the_admin_list() -> None:
    """نمایش متنیِ هر دو مدل، خالی یا بی‌معنا نیست."""
    assert str(Martyr(title="سیدشهدای مقاومت")) == "سیدشهدای مقاومت"
    assert "تصویر" in str(LeaderPortrait())


@pytest.mark.django_db
def test_order_starts_at_one_and_increments() -> None:
    """ترتیب خودکار از ۱ شروع می‌شود و یکی‌یکی بالا می‌رود — نه صفر."""
    first = Martyr.objects.create(image=_jpeg("1.jpg"), title="الف")
    second = Martyr.objects.create(image=_jpeg("2.jpg"), title="ب")
    assert (first.display_order, second.display_order) == (1, 2)


# ── پنل ادمین ──────────────────────────────────────────────────────────────
@pytest.mark.django_db
def test_admin_list_pages_render(staff_client: Any, _isolated_media: Path) -> None:
    """هر دو فهرست ادمین بالا می‌آیند (قالب، ستون‌ها و پیش‌نمایش سالم‌اند)."""
    LeaderPortrait.objects.create(image=_jpeg("p.jpg"), caption="کلام")
    Martyr.objects.create(image=_jpeg("m.jpg"), title="عنوان")

    for slug in ("leaderportrait", "martyr"):
        response = staff_client.get(f"/secure-kaveh185-admin/gallery/{slug}/")
        assert response.status_code == 200

    add_leader = staff_client.get("/secure-kaveh185-admin/gallery/leaderportrait/add/")
    assert add_leader.status_code == 200
    add_martyr = staff_client.get("/secure-kaveh185-admin/gallery/martyr/add/")
    assert add_martyr.status_code == 200


@pytest.mark.django_db
def test_admin_move_buttons_change_the_order(staff_client: Any, _isolated_media: Path) -> None:
    """دکمهٔ ▲ در ادمین، رکورد را یک پله بالا می‌آورد و کش را باطل می‌کند."""
    first = Martyr.objects.create(image=_jpeg("1.jpg"), title="الف")
    second = Martyr.objects.create(image=_jpeg("2.jpg"), title="ب")

    response = staff_client.get(f"/secure-kaveh185-admin/gallery/martyr/{second.pk}/move/up/")

    assert response.status_code == 302
    assert [m.title for m in Martyr.all_objects.order_by("display_order")] == ["ب", "الف"]
    first.refresh_from_db()
    assert first.display_order == 2


@pytest.mark.django_db
def test_admin_move_down_is_clamped_at_the_last_position(
    staff_client: Any, _isolated_media: Path
) -> None:
    """▼ روی آخرین رکورد، ترتیب را خراب نمی‌کند (به انتها می‌چسبد)."""
    Martyr.objects.create(image=_jpeg("1.jpg"), title="الف")
    last = Martyr.objects.create(image=_jpeg("2.jpg"), title="ب")

    response = staff_client.get(f"/secure-kaveh185-admin/gallery/martyr/{last.pk}/move/down/")

    assert response.status_code == 302
    assert [m.title for m in Martyr.all_objects.order_by("display_order")] == ["الف", "ب"]


@pytest.mark.django_db
def test_saving_in_the_admin_invalidates_the_public_cache(_isolated_media: Path) -> None:
    """ذخیره از ادمین، کش عمومی را باطل می‌کند تا سایت فوراً عوض شود.

    ⚠️ چرا متد ادمین مستقیم صدا زده می‌شود و نه فرم؟
    فرمِ تغییر، `ImageField` را دوباره به‌عنوان فایلِ آپلودی می‌خواند و
    دستهٔ فایل در تست باز می‌ماند (هشدار `UnraisableException` که تستِ
    بعدی را می‌اندازد). چیزی که این‌جا می‌سنجیم رفتارِ خودِ ادمین است،
    نه اعتبارسنجی فرم — و آن یک نقطه است: `save_model`.
    """
    from django.contrib.admin.sites import site as admin_site

    from apps.gallery.selectors import get_leader_gallery

    portrait = LeaderPortrait.objects.create(image=_jpeg("p.jpg"), caption="قبل")
    assert get_leader_gallery()[0]["caption"] == "قبل"  # در کش نشست

    portrait.caption = "بعد"
    portrait.save()
    model_admin = admin_site._registry[LeaderPortrait]
    model_admin.save_model(request=None, obj=portrait, form=None, change=True)

    # کش باطل شده ⇒ مقدار تازه خوانده می‌شود.
    assert get_leader_gallery()[0]["caption"] == "بعد"


@pytest.mark.django_db
def test_admin_thumbnails_render_for_existing_and_empty_images(_isolated_media: Path) -> None:
    """پیش‌نمایش تصویر در فهرست و در فرم، در هر دو حالت کار می‌کند."""
    portrait = LeaderPortrait.objects.create(image=_jpeg("t.jpg"), caption="کلام")
    martyr = Martyr.objects.create(image=_jpeg("tm.jpg"), title="عنوان")

    from apps.gallery.admin import LeaderPortraitAdmin, MartyrAdmin

    leader_admin = LeaderPortraitAdmin(
        LeaderPortrait, __import__("django.contrib.admin").contrib.admin.site
    )
    martyr_admin = MartyrAdmin(Martyr, __import__("django.contrib.admin").contrib.admin.site)

    assert "img" in str(leader_admin.thumb(portrait))
    assert "img" in str(leader_admin.thumb_large(portrait))
    assert "img" in str(martyr_admin.thumb(martyr))
    assert "img" in str(martyr_admin.thumb_large(martyr))

    # رکورد بدون تصویر نباید خطا بدهد.
    empty = LeaderPortrait()
    assert str(leader_admin.thumb(empty)) == "—"
    assert "پس از ذخیره" in str(leader_admin.thumb_large(empty))
    empty_martyr = Martyr()
    assert str(martyr_admin.thumb(empty_martyr)) == "—"
    assert "پس از ذخیره" in str(martyr_admin.thumb_large(empty_martyr))


@pytest.mark.django_db
def test_admin_delete_paths_invalidate_the_cache(_isolated_media: Path) -> None:
    """حذف تک‌رکورد و حذف گروهی، کش عمومی را باطل می‌کنند."""
    from django.contrib.admin.sites import site as admin_site
    from django.contrib.messages.storage.fallback import FallbackStorage
    from django.test import RequestFactory

    from apps.gallery.selectors import get_leader_gallery

    LeaderPortrait.objects.create(image=_jpeg("d1.jpg"), caption="یک")
    LeaderPortrait.objects.create(image=_jpeg("d2.jpg"), caption="دو")
    assert len(get_leader_gallery()) == 2

    request = RequestFactory().get("/")
    request.session = {}  # type: ignore[attr-defined]
    request._messages = FallbackStorage(request)  # type: ignore[attr-defined]

    model_admin = admin_site._registry[LeaderPortrait]
    model_admin.delete_model(request, LeaderPortrait.objects.first())
    # کش باطل شد ⇒ یک رکورد مانده.
    assert len(get_leader_gallery()) == 1

    model_admin.delete_queryset(request, LeaderPortrait.all_objects.all())
    assert get_leader_gallery() == []


# ── دستور seed ─────────────────────────────────────────────────────────────
@pytest.fixture()
def frontend_bundle(settings: Any, tmp_path: Path) -> Path:
    """یک «بستهٔ فرانت» ساختگی با تصاویر واقعی.

    ⚠️ چرا نمی‌توان به `frontend/img` مخزن تکیه کرد؟ چون آن پوشه یک
    سیم‌لینک به خروجیِ بیلد فرانت است و در CI وجود ندارد؛ تستی که به آن
    وابسته باشد، محلی سبز و روی CI قرمز می‌شود. این‌جا خودمان تصویر
    می‌سازیم، پس تست در هر محیطی یکسان است.
    """
    img = tmp_path / "dist" / "img"
    img.mkdir(parents=True, exist_ok=True)
    for name in (
        "emam-reading.jpg",
        "emam-reading-sm.jpg",
        "kaveh-hero.jpg",
        "icon-face.png",
        "emblem-portrait-sm.jpg",
    ):
        buf = io.BytesIO()
        Image.new("RGB", (24, 24), (40, 80, 120)).save(
            buf, format="PNG" if name.endswith(".png") else "JPEG"
        )
        (img / name).write_bytes(buf.getvalue())
    settings.FRONTEND_DIST = str(tmp_path / "dist")
    return img


@pytest.mark.django_db
def test_seed_creates_items_once_and_is_idempotent(
    _isolated_media: Path, frontend_bundle: Path
) -> None:
    """اجرای دوبارهٔ دستور، رکورد تکراری نمی‌سازد."""
    call_command("seed_gallery", verbosity=0)
    first_leader = LeaderPortrait.all_objects.count()
    first_martyr = Martyr.all_objects.count()
    assert first_leader > 0 and first_martyr > 0

    call_command("seed_gallery", verbosity=0)

    assert LeaderPortrait.all_objects.count() == first_leader
    assert Martyr.all_objects.count() == first_martyr


@pytest.mark.django_db
def test_seed_copies_images_into_media_and_sets_positions(
    _isolated_media: Path, frontend_bundle: Path
) -> None:
    """تصویرها واقعاً در `MEDIA_ROOT` کپی می‌شوند و ترتیب ۱، ۲، ۳ است."""
    call_command("seed_gallery", verbosity=0)

    portrait = LeaderPortrait.all_objects.order_by("display_order").first()
    assert portrait is not None
    assert portrait.image.name.startswith("gallery/leader/")
    assert (_isolated_media / portrait.image.name).is_file()

    positions = list(
        Martyr.all_objects.order_by("display_order").values_list("display_order", flat=True)
    )
    assert positions == list(range(1, len(positions) + 1))


@pytest.mark.django_db
def test_seed_force_updates_in_place(_isolated_media: Path, frontend_bundle: Path) -> None:
    """با `--force` رکوردهای ساختهٔ همین دستور به‌روز می‌شوند، نه تکرار."""
    call_command("seed_gallery", verbosity=0)
    before = LeaderPortrait.all_objects.count()
    call_command("seed_gallery", "--force", verbosity=0)
    assert LeaderPortrait.all_objects.count() == before


@pytest.mark.django_db
def test_seed_dry_run_writes_nothing(frontend_bundle: Path) -> None:
    """`--dry-run` فقط گزارش می‌دهد."""
    call_command("seed_gallery", "--dry-run", verbosity=0)
    assert LeaderPortrait.all_objects.count() == 0
    assert Martyr.all_objects.count() == 0


@pytest.mark.django_db
def test_seed_survives_a_missing_image_folder(settings: Any, _isolated_media: Path) -> None:
    """نبودنِ پوشهٔ تصاویر، استقرار را نمی‌شکند — فقط پیام می‌دهد."""
    settings.FRONTEND_DIST = "/nonexistent-path-for-test"
    settings.BASE_DIR = Path("/nonexistent-base-for-test")
    call_command("seed_gallery", verbosity=0)
    assert LeaderPortrait.all_objects.count() == 0


@pytest.mark.django_db
def test_seed_finds_images_in_a_nested_img_folder(
    settings: Any, tmp_path: Path, _isolated_media: Path
) -> None:
    """اگر `img/` جای پیش‌فرض نباشد، در عمقِ خروجی پیدا می‌شود.

    روی هاست دقیقاً همین اتفاق افتاد: یکی از تصاویر (`emblem-portrait-sm.jpg`)
    «پیدا نشد» و بی‌صدا رد شد. حالا جست‌وجو به عمقِ دو سطح می‌رود تا گم نشود.
    """
    nested = tmp_path / "dist" / "static" / "img"
    nested.mkdir(parents=True)
    buf = io.BytesIO()
    Image.new("RGB", (24, 24), (9, 9, 9)).save(buf, format="JPEG")
    for name in ("emam-reading.jpg", "emam-reading-sm.jpg"):
        (nested / name).write_bytes(buf.getvalue())
    settings.FRONTEND_DIST = str(tmp_path / "dist")
    # `BASE_DIR/frontend/img` روی هاست وجود دارد؛ اینجا هم آن را از معادله
    # بیرون می‌بریم تا فقط مسیرِ «جست‌وجوی عمقی» سنجیده شود.
    settings.BASE_DIR = tmp_path / "no-bundle-here"

    call_command("seed_gallery", verbosity=0)

    assert LeaderPortrait.all_objects.count() == 2  # هر دو تصویرِ رهبر
    assert Martyr.all_objects.count() == 0  # هیچ فایلِ شهیدی نبود


@pytest.mark.django_db
def test_seed_skips_an_item_whose_file_is_missing(
    settings: Any, tmp_path: Path, _isolated_media: Path
) -> None:
    """اگر یکی از تصاویر نباشد، فقط همان قلم رد می‌شود و بقیه می‌آیند."""
    img = tmp_path / "partial" / "img"
    img.mkdir(parents=True)
    buf = io.BytesIO()
    Image.new("RGB", (24, 24), (0, 0, 0)).save(buf, format="JPEG")
    (img / "emam-reading.jpg").write_bytes(buf.getvalue())  # فقط یکی از پنچ
    settings.FRONTEND_DIST = str(tmp_path / "partial")

    call_command("seed_gallery", verbosity=0)

    assert LeaderPortrait.all_objects.count() == 1
    assert Martyr.all_objects.count() == 0

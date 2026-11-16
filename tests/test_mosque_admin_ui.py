"""تست‌های سطح رابط ادمین مساجد.

چه چیزی را قفل می‌کنیم؟
───────────────────────
این بخش کد «کارِ ادمین» است و پیش‌تر هیچ تستی نداشت: ستون‌ها، دکمه‌های
جابه‌جایی ↑↓، و اقدام‌های گروهی. اگر روزی کسی نام مسیر یا امضای تابع را
عوض کند، ادمین در پنل با خطای ۵۰۰ روبه‌رو می‌شود — و همان لحظه‌ای است که
بیشترین نیاز به پنل دارد (افزودن مسجد پیش از شروع مسابقه).

پس این‌جا هر سه گروه را با درخواست واقعی ادمین می‌سنجیم، نه با فراخوانی
تابع به‌تنهایی؛ چون شکستن URL یا مجوز هم بخشی از قرارداد است.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.mosques.models import Mosque

pytestmark = pytest.mark.django_db

User = get_user_model()


@pytest.fixture()
def admin_client_logged_in(client):
    """ورود ادمین واقعی به پنل (بدون رمز ساختگی در داده‌ها)."""
    user = User.objects.create_user(
        phone_number="09121230000",
        national_id="0009900012",
        first_name="مدیر",
        last_name="آزمون",
        birth_date="1370-01-01",
        is_staff=True,
        is_superuser=True,
        is_phone_verified=True,
    )
    user.set_password("TempPass#185")
    user.save()
    assert client.login(username=user.phone_number, password="TempPass#185")
    return client


# ── ستون‌های فهرست ────────────────────────────────────────────────────────
def test_changelist_renders_with_new_columns(admin_client_logged_in) -> None:
    """فهرست ادمین بالا می‌آید و ستون‌های ترتیب/مشارکت/کد را نشان می‌دهد."""
    Mosque.objects.create(name="مسجد صاحب‌الزمان (عج)", code="MSQ-01")
    response = admin_client_logged_in.get(reverse("admin:mosques_mosque_changelist"))
    assert response.status_code == 200
    body = response.content.decode()
    assert "MSQ-01" in body
    # نشان ترتیب و سلول آمار باید رندر شوند
    assert "مشارکت / ثبت‌نام" in body
    # دکمه‌های جابه‌جایی داخل ردیف
    assert "move/up" in body and "move/down" in body


def test_changelist_survives_empty_database(admin_client_logged_in) -> None:
    """با صفر مسجد هم صفحه باید ۲۰۰ بدهد (حالت روز اول)."""
    response = admin_client_logged_in.get(reverse("admin:mosques_mosque_changelist"))
    assert response.status_code == 200


# ── فرم افزودن ────────────────────────────────────────────────────────────
def test_add_form_hides_auto_fields_and_explains_them(admin_client_logged_in) -> None:
    """فرم افزودن: شمارنده‌ها ورودی نیستند و توضیح «خودکار» دارد."""
    response = admin_client_logged_in.get(reverse("admin:mosques_mosque_add"))
    assert response.status_code == 200
    body = response.content.decode()
    # توضیح خودکار بودن کد و ترتیب — همان چیزی که ادمین باید بخواند
    assert "خودکار" in body
    # شمارندهٔ ثبت‌نام نباید ورودی قابل ویرایش باشد
    assert 'name="registered_count"' not in body
    assert 'name="completed_exam_count"' not in body


def test_adding_mosque_via_admin_post_generates_code_and_order(admin_client_logged_in) -> None:
    """ثبت واقعی فرم: کد و ترتیب خودکار پر می‌شوند، حداقل فیلد لازم است."""
    response = admin_client_logged_in.post(
        reverse("admin:mosques_mosque_add"),
        data={
            "name": "مسجد تازه از پنل",
            "code": "",
            "neighborhood": "",
            "address": "",
            "imam_name": "",
            "commander_name": "",
            "contact_phone": "",
            # «ترتیب نمایش» باید قابل خالی گذاشتن باشد؛ صفر یعنی «خودکار پر کن».
            "display_order": "0",
            "target_participants": "40",
            "is_active": "on",
        },
        follow=True,
    )
    assert response.status_code == 200
    mosque = Mosque.objects.get(name="مسجد تازه از پنل")
    assert mosque.code.startswith("MSQ-")
    assert mosque.display_order >= 1
    assert mosque.target_participants == 40


# ── جابه‌جایی با دکمه ─────────────────────────────────────────────────────
def test_move_up_swaps_order(admin_client_logged_in) -> None:
    """دکمهٔ ↑ ترتیب را با مسجد بالایی جابه‌جا می‌کند."""
    a = Mosque.objects.create(name="مسجد الف", code="MSQ-01")
    b = Mosque.objects.create(name="مسجد ب", code="MSQ-02")
    a.refresh_from_db()
    b.refresh_from_db()
    assert (a.display_order, b.display_order) == (1, 2)

    response = admin_client_logged_in.get(
        reverse("admin:mosques_mosque_move", args=[b.pk, "up"]), follow=True
    )
    assert response.status_code == 200
    a.refresh_from_db()
    b.refresh_from_db()
    assert (b.display_order, a.display_order) == (1, 2)


def test_move_down_at_bottom_is_safe(admin_client_logged_in) -> None:
    """آخرین مسجد که ↓ بخورد خطا نمی‌دهد و ترتیبش خراب نمی‌شود."""
    a = Mosque.objects.create(name="مسجد یک", code="MSQ-01")
    a.refresh_from_db()
    response = admin_client_logged_in.get(
        reverse("admin:mosques_mosque_move", args=[a.pk, "down"]), follow=True
    )
    assert response.status_code == 200
    a.refresh_from_db()
    assert a.display_order == 1


def test_move_with_unknown_direction_is_ignored(admin_client_logged_in) -> None:
    """جهت ناشناخته (sideways) بی‌اثر است، نه ۵۰۰."""
    mosque = Mosque.objects.create(name="مسجد جهتنما", code="MSQ-01")
    response = admin_client_logged_in.get(
        reverse("admin:mosques_mosque_move", args=[mosque.pk, "sideways"]), follow=True
    )
    assert response.status_code == 200
    mosque.refresh_from_db()
    assert mosque.display_order == 1


# ── اقدام‌های گروهی ───────────────────────────────────────────────────────
def test_bulk_actions_change_many_rows(admin_client_logged_in) -> None:
    """غیرفعال/فعال‌سازی گروهی روی چند مسجد اثر می‌گذارد."""
    mosques = [Mosque.objects.create(name=f"مسجد {i}", code=f"MSQ-0{i}") for i in range(1, 4)]
    ids = [m.pk for m in mosques]

    admin_client_logged_in.post(
        reverse("admin:mosques_mosque_changelist"),
        data={"action": "action_deactivate", "_selected_action": ids},
        follow=True,
    )
    assert Mosque.objects.filter(pk__in=ids, is_active=False).count() == 3

    admin_client_logged_in.post(
        reverse("admin:mosques_mosque_changelist"),
        data={"action": "action_activate", "_selected_action": ids},
        follow=True,
    )
    assert Mosque.objects.filter(pk__in=ids, is_active=True).count() == 3


def test_bulk_move_actions_keep_order_contiguous(admin_client_logged_in) -> None:
    """جابه‌جایی گروهی، ترتیب را بی‌شکاف نگه می‌دارد."""
    mosques = [Mosque.objects.create(name=f"مسجد {i}") for i in range(1, 4)]
    ids = [m.pk for m in mosques]

    admin_client_logged_in.post(
        reverse("admin:mosques_mosque_changelist"),
        data={"action": "action_move_down", "_selected_action": ids},
        follow=True,
    )
    order = list(Mosque.objects.order_by("display_order").values_list("display_order", flat=True))
    assert order == [1, 2, 3]

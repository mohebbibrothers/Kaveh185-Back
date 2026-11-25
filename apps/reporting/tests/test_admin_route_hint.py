"""تستِ «۴۰۴ِ گویا» — چون این ۴۰۴ یک بار چند ساعت عیب‌یابی شد.

سه رفتاری که باید قفل شود:
۱) ادمینِ staff روی مسیری که وجود ندارد، **علت و دستورِ تشخیص** می‌بیند؛
۲) کاربرِ عادی هیچ نشانه‌ای از وجودِ پنل نمی‌بیند (بدونِ افشا)؛
۳) آدرسِ قدیمی/غلطِ صفحهٔ رتبه‌بندی خودکار به آدرسِ درست هدایت می‌شود.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.authentication.choices import UserRole

pytestmark = [pytest.mark.django_db]

User = get_user_model()


def _staff(seq: str = "1") -> User:
    """ادمینِ staff با کد ملی و شمارهٔ معتبر."""
    return User.objects.create_user(
        phone_number=f"0914{seq:0>7}"[:11],
        national_id="0013542419",
        password="SecretPass!234",
        first_name="مدیر",
        last_name="پنل",
        role=UserRole.ADMIN,
        is_staff=True,
        is_superuser=True,
    )


@pytest.fixture()
def staff_client(client):
    client.force_login(_staff())
    return client


def test_staff_gets_diagnostic_page_on_unknown_admin_path(staff_client, settings) -> None:
    """صفحهٔ ۴۰۴ِ پنل باید بگوید «کد را چطور بررسی کنم»."""
    settings.DEBUG = False
    response = staff_client.get("/secure-kaveh185-admin/nope-does-not-exist/")
    assert response.status_code == 404
    body = response.content.decode()
    assert "این مسیر در این نصب وجود ندارد" in body
    assert "check_ranking_page" in body, "دستورِ تشخیص باید در صفحه باشد"


def test_anonymous_gets_no_hint_about_the_panel(client, settings) -> None:
    """بدونِ ورود، هیچ نشانی از وجودِ پنل نباید در پاسخ باشد."""
    settings.DEBUG = False
    response = client.get("/secure-kaveh185-admin/nope-does-not-exist/")
    assert response.status_code in (301, 302), "کاربرِ ناشناس باید به صفحهٔ ورود برود"
    assert "check_ranking_page" not in response.content.decode()


def test_misspelled_ranking_url_redirects_to_real_one(staff_client, settings) -> None:
    """آدرسِ قدیمی یا با اسلشِ کم ⇒ هدایتِ خودکار، نه ۴۰۴."""
    settings.DEBUG = False
    response = staff_client.get("/secure-kaveh185-admin/participant-ranking-old/")
    assert response.status_code == 302
    assert response["Location"] == reverse("participant-ranking")


def test_hint_is_off_when_debug_is_on(client, settings) -> None:
    """در توسعه، پیامِ استانداردِ جنگو گویاتر از راهنمای ماست."""
    settings.DEBUG = True
    client.force_login(_staff("2"))
    response = client.get("/secure-kaveh185-admin/nope/")
    assert response.status_code == 404
    assert "این مسیر در این نصب وجود ندارد" not in response.content.decode()


def test_following_the_real_url_still_works(staff_client) -> None:
    """بعد از همهٔ این‌ها، مسیرِ درست باید ۲۰۰ بدهد."""
    assert staff_client.get(reverse("participant-ranking")).status_code == 200

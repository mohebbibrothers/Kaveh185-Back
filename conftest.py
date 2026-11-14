"""تنظیمات و فیکسچرهای مشترک Pytest برای تست‌های سامانه کاوه ۱۸۵."""

from __future__ import annotations

from typing import Any

import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from apps.authentication.models import User
from apps.authentication.services import issue_tokens_and_session
from apps.exam.models import Question
from apps.mosques.models import Mosque
from apps.mosques.services import seed_default_mosques
from tests.factories import (
    create_test_admin,
    create_test_participant,
    seed_test_question_bank,
)


@pytest.fixture(autouse=True)
def _clear_cache_between_tests() -> Any:
    """پاک‌سازی کش پیش و پس از اجرای هر تست برای ایزولاسیون کامل."""
    cache.clear()
    yield
    cache.clear()


@pytest.fixture()
def api_client() -> APIClient:
    """کلاینت خام HTTP برای فراخوانی اندپوینت‌های DRF."""
    return APIClient()


@pytest.fixture()
def seeded_mosques(db: Any) -> list[Mosque]:
    """بارگذاری ۱۷ مسجد پیش‌فرض حوزه ۱۸۵ شهید کاوه برای تست‌ها."""
    del db
    seed_default_mosques()
    return list(Mosque.objects.filter(is_active=True).order_by("display_order", "id"))


@pytest.fixture()
def seeded_questions(db: Any) -> list[Question]:
    """بارگذاری ۸ سوال چهارگزینه‌ای در بانک سوال برای تست‌ها."""
    del db
    return seed_test_question_bank(count=8)


@pytest.fixture()
def participant_user(db: Any, seeded_mosques: list[Mosque]) -> User:
    """ایجاد شرکت‌کنندهٔ معتبر متصل به مسجد اول."""
    del db
    return create_test_participant(seq=1, mosque=seeded_mosques[0])


@pytest.fixture()
def participant_client(participant_user: User) -> APIClient:
    """کلاینت احرازشده با توکن JWT متصل به نشست معتبر برای شرکت‌کننده."""
    client = APIClient()
    tokens = issue_tokens_and_session(user=participant_user)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
    return client


@pytest.fixture()
def admin_user(db: Any) -> User:
    """ایجاد مدیر کل سامانه برای تست اندپوینت‌های مدیریتی."""
    del db
    return create_test_admin(seq=900)


@pytest.fixture()
def admin_client(admin_user: User) -> APIClient:
    """کلاینت احرازشده با توکن JWT متصل به نشست معتبر برای ادمین."""
    client = APIClient()
    tokens = issue_tokens_and_session(user=admin_user)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
    return client

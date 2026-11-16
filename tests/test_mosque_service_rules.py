"""تست‌های قاعده‌های سرویس مسجد (کد یکتا، به‌روزرسانی، غیرفعال‌سازی نرم).

چرا؟
───
این توابع هم از پنل ادمین صدا زده می‌شوند و هم از API مدیریتی. اگر قاعدهٔ
یکتایی یا غیرفعال‌سازی نرم بشکند، یک مسجد حذف‌شده ممکن است در رنکینگ و
آمار برگردد یا دو مسجد با یک کد در گزارش‌ها قاطی شوند.
"""

from __future__ import annotations

import pytest
from apps.core.exceptions import ConflictDomainError, ValidationDomainError
from apps.mosques.models import Mosque
from apps.mosques.services import (
    create_mosque,
    deactivate_mosque,
    increment_mosque_completed_exam_count,
    increment_mosque_registered_count,
    update_mosque,
    validate_mosque_code,
)

pytestmark = pytest.mark.django_db


def test_validate_code_normalizes_and_rejects_bad_input() -> None:
    """کد مسجد نرمال‌سازی می‌شود و ورودی نامعتبر رد می‌شود."""
    assert validate_mosque_code(" msq-05 ") == "MSQ-05"
    with pytest.raises(ValidationDomainError):
        validate_mosque_code("###")


def test_create_mosque_assigns_defaults_and_counters() -> None:
    """مسجد تازه: کد، ترتیب و شمارندهٔ صفر."""
    mosque = create_mosque(data={"name": "مسجد سرویس"})
    assert mosque.code.startswith("MSQ-")
    assert mosque.display_order >= 1
    assert mosque.registered_count == 0
    assert mosque.is_active is True


def test_duplicate_code_raises_conflict() -> None:
    """کد تکراری ⇒ خطای ۴۰۹ با کد دامنه، نه ۵۰۰."""
    create_mosque(data={"name": "اولی", "code": "MSQ-77"})
    with pytest.raises(ConflictDomainError) as exc:
        create_mosque(data={"name": "دومی", "code": "MSQ-77"})
    assert exc.value.code == "mosque_duplicate"


def test_update_mosque_records_changes() -> None:
    """به‌روزرسانی فیلدها ذخیره می‌شود و کد خالی کد را پاک نمی‌کند."""
    mosque = create_mosque(data={"name": "قبل", "code": "MSQ-31"})
    update_mosque(mosque=mosque, data={"name": "بعد", "code": "", "target_participants": 250})
    mosque.refresh_from_db()
    assert mosque.name == "بعد"
    assert mosque.code == "MSQ-31"  # دست‌نخورده
    assert mosque.target_participants == 250


def test_update_to_taken_code_conflicts() -> None:
    """تغییر کد به کدی که مسجد دیگری دارد، رد می‌شود."""
    create_mosque(data={"name": "الف", "code": "MSQ-41"})
    second = create_mosque(data={"name": "ب", "code": "MSQ-42"})
    with pytest.raises(ConflictDomainError):
        update_mosque(mosque=second, data={"code": "MSQ-41"})


def test_deactivate_mosque_hides_from_public_list() -> None:
    """غیرفعال‌سازی نرم: از فهرست عمومی و انتخاب مسجد غیب می‌شود، داده می‌ماند."""
    mosque = create_mosque(data={"name": "مسجد حذفی"})
    deactivate_mosque(mosque=mosque)
    mosque.refresh_from_db()
    assert mosque.is_active is False
    # همان فیلتری که API عمومی استفاده می‌کند
    assert not Mosque.objects.filter(pk=mosque.pk, is_active=True).exists()
    assert Mosque.all_objects.filter(pk=mosque.pk).exists()


def test_counters_increment_atomically() -> None:
    """شمارنده‌ها با F() زیاد می‌شوند و کش را بی‌اعتبار می‌کنند."""
    mosque = create_mosque(data={"name": "مسجد شمارنده"})
    increment_mosque_registered_count(mosque.pk)
    increment_mosque_registered_count(mosque.pk)
    increment_mosque_completed_exam_count(mosque.pk)
    mosque.refresh_from_db()
    assert mosque.registered_count == 2
    assert mosque.completed_exam_count == 1


def test_display_order_auto_fills_after_creation() -> None:
    """چند مسجد پشت‌سرهم، ترتیب یکتا و صعودی می‌گیرند."""
    orders = [create_mosque(data={"name": f"مسجد {i}"}).display_order for i in range(3)]
    assert orders == sorted(orders)
    assert len(set(orders)) == 3

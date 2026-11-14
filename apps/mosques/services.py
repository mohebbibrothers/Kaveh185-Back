"""سرویس‌های نوشتن، به‌روزرسانی اتمیک آمار مشارکت و مدیریت ۱۷ مسجد حوزه ۱۸۵ شهید کاوه."""

from __future__ import annotations

from typing import Any

from django.db import IntegrityError, transaction
from django.db.models import F

from apps.audit_logs.choices import AuditAction
from apps.audit_logs.services import record_audit_log
from apps.core.cache_invalidation import invalidate_domain_cache
from apps.core.exceptions import ConflictDomainError

from .choices import DEFAULT_KAVEH185_MOSQUES
from .models import Mosque
from .validators import validate_mosque_code


def create_mosque(*, data: dict[str, Any], request: Any = None) -> Mosque:
    """ایجاد یک مسجد جدید توسط ادمین همراه با ثبت در زنجیرهٔ حسابرسی و ابطال کش."""
    code = validate_mosque_code(str(data.get("code", "")))
    name = str(data.get("name", "")).strip()
    try:
        with transaction.atomic():
            mosque = Mosque.all_objects.create(
                code=code,
                name=name,
                neighborhood=str(data.get("neighborhood", "")).strip(),
                address=str(data.get("address", "")).strip(),
                imam_name=str(data.get("imam_name", "")).strip(),
                commander_name=str(data.get("commander_name", "")).strip(),
                contact_phone=str(data.get("contact_phone", "")).strip(),
                target_participants=int(data.get("target_participants", 500)),
                display_order=int(data.get("display_order", 1)),
                is_active=bool(data.get("is_active", True)),
            )
            record_audit_log(
                action=AuditAction.MOSQUE_CREATED,
                resource_type="mosque",
                resource_id=mosque.pk,
                request=request,
                changes={"code": mosque.code, "name": mosque.name},
            )
            invalidate_domain_cache("mosques", reason=f"mosque.created:{mosque.code}")
            invalidate_domain_cache(
                "reporting", reason=f"mosque.created:{mosque.code}", record_outbox=False
            )
            return mosque
    except IntegrityError as exc:
        raise ConflictDomainError(
            "مسجدی با این کد یا نام پیش‌تر ثبت شده است.",
            code="mosque_duplicate",
        ) from exc


def update_mosque(*, mosque: Mosque, data: dict[str, Any], request: Any = None) -> Mosque:
    """به‌روزرسانی اطلاعات یک مسجد توسط ادمین."""
    changes: dict[str, Any] = {}
    if "code" in data:
        new_code = validate_mosque_code(str(data["code"]))
        if new_code != mosque.code:
            changes["code"] = {"old": mosque.code, "new": new_code}
            mosque.code = new_code

    editable_fields = (
        "name",
        "neighborhood",
        "address",
        "imam_name",
        "commander_name",
        "contact_phone",
        "target_participants",
        "display_order",
        "is_active",
    )
    for field in editable_fields:
        if field in data:
            new_val = data[field]
            old_val = getattr(mosque, field)
            if new_val != old_val:
                changes[field] = {"old": old_val, "new": new_val}
                setattr(mosque, field, new_val)

    try:
        with transaction.atomic():
            mosque.save()
            record_audit_log(
                action=AuditAction.MOSQUE_UPDATED,
                resource_type="mosque",
                resource_id=mosque.pk,
                request=request,
                changes=changes,
            )
            invalidate_domain_cache("mosques", reason=f"mosque.updated:{mosque.code}")
            invalidate_domain_cache(
                "reporting", reason=f"mosque.updated:{mosque.code}", record_outbox=False
            )
            return mosque
    except IntegrityError as exc:
        raise ConflictDomainError(
            "کد یا نام انتخاب‌شده با مسجد دیگری تداخل دارد.",
            code="mosque_duplicate",
        ) from exc


def deactivate_mosque(*, mosque: Mosque, request: Any = None) -> Mosque:
    """غیرفعال‌سازی نرم یک مسجد توسط ادمین."""
    with transaction.atomic():
        mosque.soft_delete()
        record_audit_log(
            action=AuditAction.MOSQUE_DELETED,
            resource_type="mosque",
            resource_id=mosque.pk,
            request=request,
            changes={"is_active": {"old": True, "new": False}},
        )
        invalidate_domain_cache("mosques", reason=f"mosque.deleted:{mosque.code}")
        invalidate_domain_cache(
            "reporting", reason=f"mosque.deleted:{mosque.code}", record_outbox=False
        )
        return mosque


def increment_mosque_registered_count(mosque_id: int) -> None:
    """افزایش اتمیک شمارندهٔ ثبت‌نام‌کنندگان یک مسجد."""
    Mosque.all_objects.filter(pk=mosque_id).update(registered_count=F("registered_count") + 1)
    invalidate_domain_cache("mosques", reason=f"mosque.registered:{mosque_id}", record_outbox=False)


def increment_mosque_completed_exam_count(mosque_id: int) -> None:
    """افزایش اتمیک شمارندهٔ تکمیل‌کنندگان آزمون یک مسجد و ابطال آنی کش رنکینگ."""
    Mosque.all_objects.filter(pk=mosque_id).update(
        completed_exam_count=F("completed_exam_count") + 1,
    )
    invalidate_domain_cache("mosques", reason=f"mosque.exam_completed:{mosque_id}")
    invalidate_domain_cache(
        "reporting", reason=f"mosque.exam_completed:{mosque_id}", record_outbox=False
    )


def seed_default_mosques(*, request: Any = None) -> dict[str, int]:
    """ایجاد یا همگام‌سازی ۱۷ مسجد پیش‌فرض حوزه مقاومت بسیج ۱۸۵ شهید کاوه."""
    created_count = 0
    existing_count = 0
    with transaction.atomic():
        for item in DEFAULT_KAVEH185_MOSQUES:
            _, created = Mosque.all_objects.get_or_create(
                code=str(item["code"]),
                defaults={
                    "name": str(item["name"]),
                    "neighborhood": str(item["neighborhood"]),
                    "display_order": int(item["display_order"]),
                    "target_participants": int(item["target_participants"]),
                    "is_active": True,
                },
            )
            if created:
                created_count += 1
            else:
                existing_count += 1

        record_audit_log(
            action=AuditAction.MOSQUE_SEEDED,
            resource_type="mosque",
            resource_id="default_17_mosques",
            request=request,
            extra_data={"created": created_count, "existing": existing_count},
        )
        invalidate_domain_cache("mosques", reason="mosques.seeded")
    return {
        "created": created_count,
        "existing": existing_count,
        "total": created_count + existing_count,
    }

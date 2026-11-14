"""تست‌های زنجیرهٔ هش SHA-256، تشخیص دستکاری، فرمان CLI و خروجی فارنزیک لاگ‌های حسابرسی."""

from __future__ import annotations

from io import StringIO

import pytest
from django.core.exceptions import PermissionDenied
from django.core.management import call_command
from django.db import connection
from rest_framework.test import APIClient

from apps.audit_logs.chain import GENESIS_HASH, verify_audit_chain
from apps.audit_logs.choices import AuditAction
from apps.audit_logs.models import AuditLog
from apps.audit_logs.services import record_audit_log
from apps.authentication.models import User


@pytest.mark.django_db()
def test_audit_hash_chain_links_and_tamper_detection(admin_user: User) -> None:
    """رکوردهای حسابرسی باید زنجیرهٔ هش پیوسته بسازند و هرگونه دستکاری را تشخیص دهند."""
    log1 = record_audit_log(
        action=AuditAction.MOSQUE_CREATED,
        resource_type="mosque",
        resource_id=1,
        user=admin_user,
        changes={"name": "مسجد جامع"},
    )
    log2 = record_audit_log(
        action=AuditAction.QUESTION_CREATED,
        resource_type="question",
        resource_id=10,
        user=admin_user,
        changes={"text": "سوال اول"},
    )

    assert log1.previous_hash == GENESIS_HASH
    assert log2.previous_hash == log1.event_hash

    verification = verify_audit_chain()
    assert verification["valid"] is True
    assert verification["checked_count"] >= 2

    # بررسی مسدود بودن ویرایش مستقیم در سطح ORM
    with pytest.raises(PermissionDenied):
        AuditLog.objects.filter(pk=log1.pk).update(resource_id="999999")

    # شبیه‌سازی دستکاری غیرمجاز مستقیم در سطح SQL دیتابیس
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE audit_logs_auditlog SET resource_id = %s WHERE id = %s",
            ["999999", log1.pk],
        )
    tampered = verify_audit_chain()
    assert tampered["valid"] is False
    assert tampered["broken_at_index"] == log1.chain_index


@pytest.mark.django_db()
def test_verify_audit_chain_management_command_and_admin_endpoints(
    admin_client: APIClient,
    admin_user: User,
) -> None:
    """تست فرمان `verify_audit_chain` و اندپوینت‌های ادمین برای مشاهده، اعتبارسنجی و خروجی فارنزیک."""
    log = record_audit_log(
        action=AuditAction.EXAM_CONFIG_UPDATED,
        resource_type="exam_configuration",
        resource_id=1,
        user=admin_user,
    )

    out = StringIO()
    call_command("verify_audit_chain", stdout=out)
    assert "معتبر" in out.getvalue() or "OK" in out.getvalue()

    list_resp = admin_client.get(
        f"/api/v1/audit-logs/admin/logs/?action={AuditAction.EXAM_CONFIG_UPDATED}"
        f"&resource_type=exam_configuration&resource_id=1&user_id={admin_user.id}&q=exam"
    )
    assert list_resp.status_code == 200
    assert list_resp.json()["data"]["pagination"]["count"] >= 1

    from apps.audit_logs.filters import AuditLogFilterSet

    fs = AuditLogFilterSet(
        data={"action": AuditAction.EXAM_CONFIG_UPDATED}, queryset=AuditLog.objects.all()
    )
    assert fs.qs.count() >= 1

    detail_resp = admin_client.get(f"/api/v1/audit-logs/admin/logs/{log.id}/")
    assert detail_resp.status_code == 200
    assert detail_resp.json()["data"]["id"] == log.id

    verify_resp = admin_client.get("/api/v1/audit-logs/admin/logs/verify/")
    assert verify_resp.status_code == 200
    assert verify_resp.json()["data"]["valid"] is True

    csv_resp = admin_client.get("/api/v1/audit-logs/admin/logs/export/?export_format=csv")
    assert csv_resp.status_code == 200
    assert "X-Export-SHA256" in csv_resp

    jsonl_resp = admin_client.get("/api/v1/audit-logs/admin/logs/export/?export_format=jsonl")
    assert jsonl_resp.status_code == 200
    assert "X-Export-SHA256" in jsonl_resp

"""سلکتورهای خواندن و فیلتر کردن لاگ‌های حسابرسی برای پنل مدیریت کاوه ۱۸۵."""

from __future__ import annotations

from typing import Any

from django.db.models import Q, QuerySet

from apps.core.exceptions import NotFoundDomainError

from .models import AuditLog


def get_audit_logs_queryset(*, params: dict[str, Any] | None = None) -> QuerySet[AuditLog]:
    """واکشی کوئری‌ست بهینهٔ لاگ‌های حسابرسی همراه با فیلترهای مدیریتی."""
    qs = AuditLog.objects.select_related("user").order_by("-chain_index")
    if not params:
        return qs

    action = str(params.get("action", "")).strip()
    if action:
        qs = qs.filter(action=action)

    resource_type = str(params.get("resource_type", "")).strip()
    if resource_type:
        qs = qs.filter(resource_type=resource_type)

    resource_id = str(params.get("resource_id", "")).strip()
    if resource_id:
        qs = qs.filter(resource_id=resource_id)

    user_id = params.get("user_id")
    if user_id:
        qs = qs.filter(user_id=user_id)

    search = str(params.get("q") or params.get("search") or "").strip()
    if search:
        qs = qs.filter(
            Q(actor_label__icontains=search)
            | Q(action__icontains=search)
            | Q(resource_type__icontains=search)
            | Q(resource_id__icontains=search)
            | Q(reason__icontains=search)
            | Q(request_id__icontains=search)
        )
    return qs


def get_audit_log_by_id(audit_log_id: int) -> AuditLog:
    """واکشی یک رکورد حسابرسی با شناسه یا پرتاب استثنای ۴۰۴."""
    row = AuditLog.objects.select_related("user").filter(pk=audit_log_id).first()
    if row is None:
        raise NotFoundDomainError("رکورد حسابرسی مورد نظر یافت نشد.")
    return row

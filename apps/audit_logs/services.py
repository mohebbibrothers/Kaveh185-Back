"""سرویس ثبت اتمیک لاگ‌های حسابرسی همراه با استخراج متادیتای درخواست و زنجیرهٔ هش."""

from __future__ import annotations

from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.core.client_ip import get_client_ip
from apps.core.responses import get_current_trace_id

from .chain import GENESIS_HASH, compute_audit_event_hash
from .models import AuditLog


def record_audit_log(
    *,
    action: Any,
    resource_type: str,
    resource_id: str | int,
    user: Any = None,
    actor_label: str = "",
    reason: str = "",
    request: Any = None,
    changes: dict[str, Any] | None = None,
    extra_data: dict[str, Any] | None = None,
) -> AuditLog:
    """ثبت یک رکورد جدید در زنجیرهٔ حسابرسی با قفل تراکنشی و محاسبهٔ هش پیوسته."""
    resolved_user = user
    if resolved_user is None and request is not None:
        req_user = getattr(request, "user", None)
        if req_user is not None and getattr(req_user, "is_authenticated", False):
            resolved_user = req_user

    user_id = getattr(resolved_user, "pk", None) if resolved_user is not None else None
    if not actor_label and resolved_user is not None:
        actor_label = str(
            getattr(resolved_user, "full_name", "") or getattr(resolved_user, "phone_number", "")
        )

    ip_address = get_client_ip(request) if request is not None else ""
    meta = getattr(request, "META", {}) if request is not None else {}
    user_agent = str(meta.get("HTTP_USER_AGENT", ""))[:300]
    path = str(getattr(request, "path", ""))[:255] if request is not None else ""
    method = str(getattr(request, "method", ""))[:16] if request is not None else ""
    req_id_attr = getattr(request, "request_id", None) if request is not None else None
    request_id = str(req_id_attr) if req_id_attr else get_current_trace_id()

    safe_changes = changes or {}
    safe_extra = extra_data or {}
    now = timezone.now()

    with transaction.atomic():
        last_log = AuditLog.objects.select_for_update().order_by("-chain_index").first()
        chain_index = (last_log.chain_index + 1) if last_log is not None else 1
        previous_hash = last_log.event_hash if last_log is not None else GENESIS_HASH

        event_hash = compute_audit_event_hash(
            chain_index=chain_index,
            previous_hash=previous_hash,
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=str(resource_id),
            reason=reason,
            request_id=request_id,
            changes=safe_changes,
            extra_data=safe_extra,
            created_at=now,
        )

        return AuditLog.objects.create(
            chain_index=chain_index,
            hash_version=1,
            previous_hash=previous_hash,
            event_hash=event_hash,
            user=resolved_user,
            actor_label=actor_label[:160],
            action=action,
            resource_type=resource_type[:64],
            resource_id=str(resource_id)[:64],
            reason=reason[:300],
            ip_address=ip_address[:64],
            user_agent=user_agent,
            path=path,
            method=method,
            request_id=request_id[:64],
            changes=safe_changes,
            extra_data=safe_extra,
            created_at=now,
        )

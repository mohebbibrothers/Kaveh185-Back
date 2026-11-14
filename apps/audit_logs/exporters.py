"""ساخت بستهٔ خروجی فارنزیک (Forensic Export Package) از زنجیرهٔ لاگ‌های حسابرسی."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from django.utils import timezone

from .chain import verify_audit_chain
from .models import AuditLog


def build_forensic_audit_package(*, limit: int = 1000) -> dict[str, Any]:
    """تولید بستهٔ JSON قابل استناد از رکوردهای حسابرسی به همراه اثر انگشت SHA-256."""
    verification = verify_audit_chain()
    rows = list(AuditLog.objects.order_by("chain_index")[:limit])
    events = [
        {
            "chain_index": r.chain_index,
            "previous_hash": r.previous_hash,
            "event_hash": r.event_hash,
            "user_id": r.user_id,
            "actor_label": r.actor_label,
            "action": r.action,
            "resource_type": r.resource_type,
            "resource_id": r.resource_id,
            "reason": r.reason,
            "ip_address": r.ip_address,
            "request_id": r.request_id,
            "changes": r.changes,
            "extra_data": r.extra_data,
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]
    canonical_events = json.dumps(events, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    package_sha256 = hashlib.sha256(canonical_events.encode("utf-8")).hexdigest()
    return {
        "exported_at": timezone.now().isoformat(),
        "service": "kaveh185",
        "chain_verification": verification,
        "count": len(events),
        "package_sha256": package_sha256,
        "events": events,
    }

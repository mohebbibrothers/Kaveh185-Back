"""محاسبه و راستی‌آزمایی زنجیرهٔ هش پیوسته (Tamper-Evident Hash Chain) لاگ‌های حسابرسی."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from .models import AuditLog

GENESIS_HASH = "0" * 64


def compute_audit_event_hash(
    *,
    chain_index: int,
    previous_hash: str,
    user_id: int | None,
    action: str,
    resource_type: str,
    resource_id: str,
    reason: str,
    request_id: str,
    changes: Any,
    extra_data: Any,
    created_at: datetime,
) -> str:
    """محاسبهٔ هش قطعی SHA-256 برای یک رکورد حسابرسی بر اساس رکورد قبلی و فیلدهای کلیدی."""
    canonical_payload = {
        "chain_index": chain_index,
        "previous_hash": previous_hash,
        "user_id": user_id,
        "action": action,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "reason": reason,
        "request_id": request_id,
        "changes": changes,
        "extra_data": extra_data,
        "created_at": created_at.isoformat(),
    }
    serialized = json.dumps(
        canonical_payload,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def verify_audit_chain(*, limit: int | None = None) -> dict[str, Any]:
    """بررسی کامل پیوستگی و صحت رمزنگاری زنجیرهٔ هش حسابرسی."""
    qs = AuditLog.objects.order_by("chain_index")
    if limit is not None:
        total = qs.count()
        start_offset = max(0, total - limit)
        rows = list(qs[start_offset:])
    else:
        rows = list(qs)

    if not rows:
        return {
            "valid": True,
            "checked_count": 0,
            "broken_at_index": None,
            "reason": None,
        }

    expected_prev: str | None = GENESIS_HASH if rows[0].chain_index == 1 else None
    expected_index: int = rows[0].chain_index

    for row in rows:
        if row.chain_index != expected_index:
            return {
                "valid": False,
                "checked_count": len(rows),
                "broken_at_index": row.chain_index,
                "reason": f"عدم پیوستگی شماره زنجیره: انتظار {expected_index}، مشاهده {row.chain_index}",
            }
        if expected_prev is not None and row.previous_hash != expected_prev:
            return {
                "valid": False,
                "checked_count": len(rows),
                "broken_at_index": row.chain_index,
                "reason": "عدم تطابق previous_hash با هش رکورد قبلی",
            }
        recomputed = compute_audit_event_hash(
            chain_index=row.chain_index,
            previous_hash=row.previous_hash,
            user_id=row.user_id,
            action=row.action,
            resource_type=row.resource_type,
            resource_id=row.resource_id,
            reason=row.reason,
            request_id=row.request_id,
            changes=row.changes,
            extra_data=row.extra_data,
            created_at=row.created_at,
        )
        if recomputed != row.event_hash:
            return {
                "valid": False,
                "checked_count": len(rows),
                "broken_at_index": row.chain_index,
                "reason": "دستکاری محتوای رکورد: event_hash با محتوای فعلی همخوانی ندارد",
            }
        expected_prev = row.event_hash
        expected_index += 1

    return {
        "valid": True,
        "checked_count": len(rows),
        "broken_at_index": None,
        "reason": None,
        "head_hash": rows[-1].event_hash,
        "head_index": rows[-1].chain_index,
    }

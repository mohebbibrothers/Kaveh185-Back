"""مدیریت هم‌توانی درخواست‌ها (`Idempotency-Key`) — تضمین «دوبار ارسال، یک‌بار اثر».

وقتی کاربر در زمان شروع یا پایان آزمون روی دکمه دو بار کلیک کند یا اینترنت موبایلش
قطع و وصل شود، ارسال همان `Idempotency-Key` باعث بازپخش دقیق پاسخ اول بدون تکرار
عملیات در دیتابیس می‌شود.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from django.db import IntegrityError, transaction
from django.utils import timezone

from .choices import IdempotencyOutcome
from .exceptions import ConflictDomainError
from .models import IdempotencyKey

IDEMPOTENCY_HEADER = "Idempotency-Key"
DEFAULT_TTL_HOURS = 24
STALE_LOCK_SECONDS = 120


def fingerprint(payload: Any, *, extra: str = "") -> str:
    """تولید اثر انگشت پایدار SHA-256 از بدنهٔ درخواست."""
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(f"{extra}|{canonical}".encode()).hexdigest()


def reserve_key(
    *,
    key: str,
    scope: str,
    actor_ref: str = "",
    payload: Any = None,
) -> tuple[Any, IdempotencyKey | None]:
    """رزرو کلید هم‌توانی پیش از اجرای عملیات نوشتن."""
    fp = fingerprint(payload, extra=scope) if payload is not None else ""
    now = timezone.now()
    expires = now + timedelta(hours=DEFAULT_TTL_HOURS)

    try:
        with transaction.atomic():
            record = IdempotencyKey.all_objects.create(
                key=key,
                scope=scope,
                actor_ref=actor_ref,
                request_fingerprint=fp,
                locked_at=now,
                expires_at=expires,
            )
        return IdempotencyOutcome.RESERVED, record
    except IntegrityError:
        existing = IdempotencyKey.all_objects.filter(key=key, scope=scope).first()
        if existing is None:  # pragma: no cover
            return IdempotencyOutcome.IN_PROGRESS, None
        return _resolve_existing(existing, actor_ref=actor_ref, fp=fp), existing


def _resolve_existing(
    existing: IdempotencyKey,
    *,
    actor_ref: str,
    fp: str,
) -> Any:
    """تعیین وضعیت کلیدی که قبلاً ثبت شده است."""
    if existing.actor_ref != actor_ref or (
        existing.request_fingerprint and fp and existing.request_fingerprint != fp
    ):
        return IdempotencyOutcome.CONFLICT
    if existing.response_status is not None:
        return IdempotencyOutcome.REPLAY

    now = timezone.now()
    expires = now + timedelta(hours=DEFAULT_TTL_HOURS)
    reclaimed = IdempotencyKey.all_objects.filter(
        pk=existing.pk,
        response_status__isnull=True,
        locked_at__lt=now - timedelta(seconds=STALE_LOCK_SECONDS),
    ).update(locked_at=now, expires_at=expires)
    if not reclaimed:
        return IdempotencyOutcome.IN_PROGRESS
    existing.locked_at = now
    existing.expires_at = expires
    return IdempotencyOutcome.RESERVED


def release_key(record: IdempotencyKey) -> None:
    """حذف فیزیکی کلید در صورت بروز استثنا تا تلاش مجدد کاربر مسدود نماند."""
    IdempotencyKey.all_objects.filter(pk=record.pk, response_status__isnull=True).delete()


def store_result(record: IdempotencyKey, *, status_code: int, body: Any) -> None:
    """ذخیرهٔ نتیجهٔ عملیات موفق برای بازپخش در درخواست‌های تکراری."""
    record.response_status = status_code
    record.response_body = body
    record.save(update_fields=["response_status", "response_body", "updated_at"])


@dataclass(frozen=True, slots=True)
class IdempotentExecutionResult:
    """خروجی اجرای یک عملیات هم‌توان."""

    status_code: int
    body: Any
    replayed: bool


def execute_idempotent(
    *,
    key: str,
    scope: str,
    actor_ref: str,
    payload: Any,
    action: Callable[[], tuple[int, Any]],
) -> IdempotentExecutionResult:
    """اجرای عملیات با تضمین هم‌توانی و بازپخش ایمن پاسخ."""
    outcome, record = reserve_key(key=key, scope=scope, actor_ref=actor_ref, payload=payload)
    if outcome is IdempotencyOutcome.REPLAY and record is not None:
        return IdempotentExecutionResult(
            status_code=int(record.response_status or 200),
            body=record.response_body,
            replayed=True,
        )
    if outcome is IdempotencyOutcome.CONFLICT:
        raise ConflictDomainError(
            "این کلید هم‌توانی (Idempotency-Key) پیش‌تر با محتوای دیگری استفاده شده است.",
            code="idempotency_conflict",
        )
    if outcome is IdempotencyOutcome.IN_PROGRESS:
        raise ConflictDomainError(
            "درخواست هم‌زمان دیگری با همین کلید در حال پردازش است.",
            code="idempotent_in_progress",
        )

    try:
        status_code, body = action()
    except Exception:
        if record is not None:
            release_key(record)
        raise

    if record is not None:
        store_result(record, status_code=status_code, body=body)
    return IdempotentExecutionResult(status_code=status_code, body=body, replayed=False)


def purge_expired_keys(*, batch: int = 1000) -> int:
    """پاک‌سازی دسته‌ای کلیدهای هم‌توانی منقضی‌شده."""
    stale_ids = list(
        IdempotencyKey.all_objects.filter(expires_at__lt=timezone.now())
        .order_by("expires_at")
        .values_list("id", flat=True)[:batch]
    )
    if not stale_ids:
        return 0
    deleted, _ = IdempotencyKey.all_objects.filter(id__in=stale_ids).delete()
    return int(deleted)


def idempotent_endpoint(view_method: Callable[..., Any]) -> Callable[..., Any]:
    """دکوراتور ویوهای DRF برای پشتیبانی خودکار از هدر `Idempotency-Key`."""
    from functools import wraps

    from rest_framework.response import Response

    @wraps(view_method)
    def _wrapped(self: Any, request: Any, *args: Any, **kwargs: Any) -> Any:
        key = str(request.headers.get(IDEMPOTENCY_HEADER, "")).strip()
        if not key:
            return view_method(self, request, *args, **kwargs)

        user = getattr(request, "user", None)
        actor_ref = (
            f"user:{user.pk}" if user and getattr(user, "is_authenticated", False) else "anon"
        )
        scope = f"{request.method}:{request.path}"
        raw_payload = getattr(request, "data", None)

        def _run() -> tuple[int, Any]:
            resp = view_method(self, request, *args, **kwargs)
            return int(resp.status_code), resp.data

        res = execute_idempotent(
            key=key[:128],
            scope=scope,
            actor_ref=actor_ref,
            payload=raw_payload,
            action=_run,
        )
        response = Response(res.body, status=res.status_code)
        response["X-Idempotent-Replayed"] = "true" if res.replayed else "false"
        return response

    return _wrapped

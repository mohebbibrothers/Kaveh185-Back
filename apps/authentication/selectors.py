"""سلکتورهای خواندن کاربران، نشست‌ها، سیگنال‌های ریسک و وضعیت آمادگی ورود به آزمون."""

from __future__ import annotations

from typing import Any

from django.db.models import Q, QuerySet

from apps.core.exceptions import NotFoundDomainError

from .models import AuthRiskSignal, AuthSession, User


def get_user_exam_eligibility(user: User) -> dict[str, Any]:
    """بررسی وضعیت مجاز بودن کاربر برای ورود به آزمون (پنجره زمانی + عدم شرکت قبلی)."""
    from apps.exam.choices import ExamAttemptStatus
    from apps.exam.models import ExamAttempt
    from apps.exam.selectors import get_public_exam_status

    exam_status = get_public_exam_status()
    attempt = ExamAttempt.objects.filter(user=user).first()

    has_completed = bool(
        attempt is not None
        and attempt.status in {ExamAttemptStatus.COMPLETED, ExamAttemptStatus.TIMED_OUT}
    )
    has_in_progress = bool(attempt is not None and attempt.status == ExamAttemptStatus.IN_PROGRESS)
    profile_ready = bool(
        user.first_name
        and user.last_name
        and user.national_id
        and user.phone_number
        and user.birth_date
        and user.mosque_id
    )
    can_enter = bool(
        profile_ready and not has_completed and (exam_status["can_participate"] or has_in_progress)
    )

    if has_completed:
        reason_code = "already_completed"
        reason_message = "شما قبلاً در این آزمون شرکت کرده‌اید و کارنامهٔ شما صادر شده است."
    elif not profile_ready:
        reason_code = "incomplete_profile"
        reason_message = "لطفاً اطلاعات هویتی و مسجد خود را تکمیل کنید."
    elif not exam_status["can_participate"] and not has_in_progress:
        reason_code = f"exam_{exam_status['window_state']}"
        reason_message = exam_status["status_message"]
    else:
        reason_code = "ready"
        reason_message = "دکمهٔ ورود به آزمون برای شما فعال است."

    return {
        "can_enter_exam": can_enter,
        "reason_code": reason_code,
        "reason_message": reason_message,
        "profile_ready": profile_ready,
        "has_completed_exam": has_completed,
        "has_in_progress_exam": has_in_progress,
        "attempt_status": attempt.status if attempt else None,
        "tracking_code": attempt.tracking_code if (attempt and has_completed) else None,
        "exam_window": exam_status,
    }


def list_user_active_sessions(user: User, *, current_sid: str = "") -> list[dict[str, Any]]:
    """دریافت فهرست نشست‌های فعال کاربر با مشخص کردن نشست جاری."""
    rows = AuthSession.objects.filter(user=user, is_revoked=False).order_by("-last_seen_at")
    items: list[dict[str, Any]] = []
    for row in rows:
        sid = row.sid_str
        items.append(
            {
                "id": row.id,
                "session_uid": sid,
                "device_label": row.device_label,
                "ip_address": row.ip_address,
                "network_prefix": row.network_prefix,
                "created_at": row.created_at,
                "last_seen_at": row.last_seen_at,
                "mfa_verified_at": row.mfa_verified_at,
                "is_current": bool(current_sid and sid == current_sid),
            }
        )
    items.sort(key=lambda x: not x["is_current"])
    return items


def get_admin_users_queryset(*, params: dict[str, Any] | None = None) -> QuerySet[User]:
    """واکشی کوئری‌ست کاربران برای پنل مدیریت ادمین همراه با فیلترها."""
    qs = User.objects.select_related("mosque", "exam_attempt").order_by("-created_at", "-id")
    if not params:
        return qs

    role = str(params.get("role", "")).strip()
    if role:
        qs = qs.filter(role=role)

    mosque_id = params.get("mosque_id")
    if mosque_id:
        qs = qs.filter(mosque_id=mosque_id)

    search = str(params.get("q") or params.get("search") or "").strip()
    if search:
        qs = qs.filter(
            Q(first_name__icontains=search)
            | Q(last_name__icontains=search)
            | Q(phone_number__icontains=search)
            | Q(national_id__icontains=search)
            | Q(mosque__name__icontains=search)
        )
    return qs


def get_user_by_id_or_404(user_id: int) -> User:
    """واکشی کاربر با شناسه یا پرتاب استثنای ۴۰۴."""
    user = User.objects.select_related("mosque").filter(pk=user_id).first()
    if user is None:
        raise NotFoundDomainError("کاربر مورد نظر یافت نشد.", code="user_not_found")
    return user


def get_risk_signals_queryset(
    *, is_reviewed: str = "", severity: str = ""
) -> QuerySet[AuthRiskSignal]:
    """واکشی سیگنال‌های ریسک امنیتی برای بررسی ادمین."""
    qs = AuthRiskSignal.objects.select_related("user", "reviewed_by").order_by("-created_at", "-id")
    if is_reviewed.lower() in {"true", "1"}:
        qs = qs.filter(is_reviewed=True)
    elif is_reviewed.lower() in {"false", "0"}:
        qs = qs.filter(is_reviewed=False)
    if severity.strip():
        qs = qs.filter(severity=severity.strip())
    return qs


def get_risk_signal_by_id(signal_id: int) -> AuthRiskSignal:
    """واکشی یک سیگنال ریسک با شناسه."""
    sig = AuthRiskSignal.objects.select_related("user", "reviewed_by").filter(pk=signal_id).first()
    if sig is None:
        raise NotFoundDomainError("سیگنال ریسک مورد نظر یافت نشد.", code="risk_signal_not_found")
    return sig

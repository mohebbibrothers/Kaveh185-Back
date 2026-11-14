"""سلکتور تجمیع وضعیت کل سامانه در یک اسنپ‌شات واحد برای پنل مدیریت."""

from __future__ import annotations

from typing import Any

from django.utils import timezone

from apps.audit_logs.chain import verify_audit_chain
from apps.audit_logs.models import AuditLog
from apps.authentication.models import AuthRiskSignal
from apps.core.choices import OutboxStatus
from apps.core.health.checks import build_detailed_health_report
from apps.core.jalali import format_jalali_datetime
from apps.core.models import OutboxMessage
from apps.exam.selectors import get_public_exam_status
from apps.notifications.models import SMSDeliveryLog
from apps.reporting.selectors import get_live_analytics_dashboard


def get_command_center_snapshot() -> dict[str, Any]:
    """تولید نمای ۳۶۰ درجه از وضعیت مسابقه، ۱۷ مسجد، امنیت، پیامک‌ها و سلامت زیرساخت."""
    now = timezone.now()
    exam_status = get_public_exam_status()
    analytics = get_live_analytics_dashboard()
    health_report = build_detailed_health_report()
    audit_integrity = verify_audit_chain(limit=500)

    unreviewed_risk_count = AuthRiskSignal.objects.filter(is_reviewed=False).count()
    pending_outbox_count = OutboxMessage.objects.filter(
        status__in=[OutboxStatus.PENDING, OutboxStatus.FAILED]
    ).count()
    total_sms_logs = SMSDeliveryLog.objects.count()
    recent_audit_logs = list(
        AuditLog.objects.values(
            "id",
            "action",
            "resource_type",
            "resource_id",
            "ip_address",
            "created_at",
        )[:10]
    )

    return {
        "generated_at": now.isoformat(),
        "generated_at_jalali": format_jalali_datetime(now),
        "exam_status": exam_status,
        "overview": analytics["overview"],
        "top_mosques": analytics["mosques_ranking_and_analytics"][:5],
        "correct_count_distribution": analytics["correct_count_distribution"],
        "age_groups_distribution": analytics["age_groups_distribution"],
        "security_and_integrity": {
            "unreviewed_risk_signals_count": unreviewed_risk_count,
            "audit_chain_intact": bool(audit_integrity.get("valid", True)),
            "audit_checked_records": int(audit_integrity.get("checked_count", 0)),
        },
        "infrastructure_and_outbox": {
            "healthy": health_report["overall_status"] == "healthy",
            "overall_status": health_report["overall_status"],
            "components": health_report["checks"],
            "pending_outbox_messages": pending_outbox_count,
            "total_sms_deliveries": total_sms_logs,
        },
        "recent_audit_events": recent_audit_logs,
    }

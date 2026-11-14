"""بررسی‌های عمیق سلامت زیرساخت برای کاوه ۱۸۵ (دیتابیس، کش، مایگریشن‌ها، زنجیرهٔ Audit و درگاه پیامک)."""

from __future__ import annotations

import time
from typing import Any

from django.conf import settings
from django.core.cache import cache
from django.db import connections
from django.db.migrations.executor import MigrationExecutor


def check_database() -> dict[str, Any]:
    """بررسی اتصال زنده به دیتابیس اصلی."""
    start = time.perf_counter()
    try:
        conn = connections["default"]
        with conn.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        return {
            "status": "healthy",
            "latency_ms": round((time.perf_counter() - start) * 1000.0, 2),
            "vendor": conn.vendor,
        }
    except Exception as exc:
        return {
            "status": "unhealthy",
            "error": str(exc),
        }


def check_cache() -> dict[str, Any]:
    """بررسی خواندن و نوشتن در لایهٔ کش."""
    start = time.perf_counter()
    probe_key = "kaveh185:health:probe"
    try:
        cache.set(probe_key, "ok", timeout=10)
        val = cache.get(probe_key)
        healthy = val == "ok"
        return {
            "status": "healthy" if healthy else "degraded",
            "latency_ms": round((time.perf_counter() - start) * 1000.0, 2),
        }
    except Exception as exc:
        return {
            "status": "degraded",
            "error": str(exc),
        }


def check_migrations() -> dict[str, Any]:
    """بررسی عدم وجود مایگریشن اعمال‌نشده."""
    try:
        conn = connections["default"]
        executor = MigrationExecutor(conn)
        targets = executor.loader.graph.leaf_nodes()
        plan = executor.migration_plan(targets)
        return {
            "status": "healthy" if not plan else "degraded",
            "unapplied_count": len(plan),
        }
    except Exception as exc:
        return {
            "status": "degraded",
            "error": str(exc),
        }


def check_audit_chain_quick() -> dict[str, Any]:
    """بررسی سریع یکپارچگی آخرین رکوردهای زنجیرهٔ حسابرسی (Audit Hash Chain)."""
    try:
        from apps.audit_logs.chain import verify_audit_chain

        result = verify_audit_chain(limit=100)
        return {
            "status": "healthy" if result["valid"] else "unhealthy",
            "checked_count": result["checked_count"],
            "valid": result["valid"],
        }
    except Exception as exc:
        return {
            "status": "degraded",
            "error": str(exc),
        }


def check_sms_provider_readiness() -> dict[str, Any]:
    """بررسی وضعیت پیکربندی درگاه پیامکی سامانه."""
    provider = str(getattr(settings, "OTP_SMS_PROVIDER", "console")).strip().lower()
    if provider == "console":
        return {"status": "healthy", "provider": "console", "mode": "development"}
    if provider == "iranpayamak":
        api_key = bool(str(getattr(settings, "SMS_IRANPAYAMAK_API_KEY", "")).strip())
        return {
            "status": "healthy" if api_key else "degraded",
            "provider": "iranpayamak",
            "configured": api_key,
        }
    return {"status": "healthy", "provider": provider}


def build_detailed_health_report() -> dict[str, Any]:
    """ساخت گزارش تشخیصی جامع از تمام زیرسیستم‌های کاوه ۱۸۵."""
    db_info = check_database()
    cache_info = check_cache()
    mig_info = check_migrations()
    audit_info = check_audit_chain_quick()
    sms_info = check_sms_provider_readiness()

    checks = {
        "database": db_info,
        "cache": cache_info,
        "migrations": mig_info,
        "audit_chain": audit_info,
        "sms_provider": sms_info,
    }
    if db_info["status"] == "unhealthy" or audit_info["status"] == "unhealthy":
        overall = "unhealthy"
    elif any(c["status"] != "healthy" for c in checks.values()):
        overall = "degraded"
    else:
        overall = "healthy"

    return {
        "overall_status": overall,
        "service": "kaveh185",
        "checks": checks,
    }

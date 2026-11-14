"""محدودسازی نرخ درخواست برای مسیرهای پایش سلامت."""

from __future__ import annotations

from rest_framework.throttling import AnonRateThrottle


class HealthCheckThrottle(AnonRateThrottle):
    """محدودکنندهٔ نرخ برای مسیرهای Health Check."""

    scope = "health_check"

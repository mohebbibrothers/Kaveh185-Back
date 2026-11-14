"""قراردادهای بودجهٔ کارایی (Performance Contracts) برای مسیرهای حیاتی کاوه ۱۸۵."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class EndpointPerformanceBudget:
    """بودجهٔ حداکثر زمان پاسخ (میلی‌ثانیه) و حداکثر تعداد کوئری دیتابیس."""

    path_prefix: str
    max_response_ms: int
    max_db_queries: int


DEFAULT_BUDGET = EndpointPerformanceBudget(
    path_prefix="/api/",
    max_response_ms=400,
    max_db_queries=15,
)

ENDPOINT_PERFORMANCE_BUDGETS: tuple[EndpointPerformanceBudget, ...] = (
    EndpointPerformanceBudget("/api/v1/health/", max_response_ms=200, max_db_queries=8),
    EndpointPerformanceBudget(
        "/api/v1/mosques/leaderboard/", max_response_ms=250, max_db_queries=6
    ),
    EndpointPerformanceBudget("/api/v1/mosques/", max_response_ms=200, max_db_queries=5),
    EndpointPerformanceBudget("/api/v1/exam/status/", max_response_ms=150, max_db_queries=4),
    EndpointPerformanceBudget("/api/v1/exam/start/", max_response_ms=400, max_db_queries=18),
    EndpointPerformanceBudget("/api/v1/exam/answer/", max_response_ms=250, max_db_queries=10),
    EndpointPerformanceBudget("/api/v1/exam/finish/", max_response_ms=450, max_db_queries=22),
    EndpointPerformanceBudget("/api/v1/exam/report-card/", max_response_ms=250, max_db_queries=8),
)


def resolve_performance_budget(path: str) -> EndpointPerformanceBudget:
    """یافتن بودجهٔ کارایی متناظر با مسیر درخواست."""
    for budget in ENDPOINT_PERFORMANCE_BUDGETS:
        if path.startswith(budget.path_prefix):
            return budget
    return DEFAULT_BUDGET

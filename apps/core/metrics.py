"""متریک‌های Prometheus برای مشاهده‌پذیری (Observability) سامانهٔ کاوه ۱۸۵."""

from __future__ import annotations

from prometheus_client import Counter, Histogram

HTTP_REQUESTS_TOTAL = Counter(
    "kaveh185_http_requests_total",
    "Total HTTP requests processed by Kaveh185 backend.",
    ["method", "status"],
)

HTTP_SLOW_REQUESTS_TOTAL = Counter(
    "kaveh185_http_slow_requests_total",
    "Total HTTP requests exceeding their configured performance budget.",
    ["method"],
)

HTTP_DB_QUERY_COUNT = Histogram(
    "kaveh185_http_db_query_count",
    "Number of database queries executed per HTTP request.",
    buckets=(1, 2, 4, 8, 12, 16, 24, 32, 64),
)

HTTP_DB_QUERY_TIME_SECONDS = Histogram(
    "kaveh185_http_db_query_time_seconds",
    "Database query execution time per HTTP request in seconds.",
    buckets=(0.002, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0),
)

EXAM_ATTEMPTS_STARTED_TOTAL = Counter(
    "kaveh185_exam_attempts_started_total",
    "Total exam attempts started.",
)

EXAM_ATTEMPTS_FINALIZED_TOTAL = Counter(
    "kaveh185_exam_attempts_finalized_total",
    "Total exam attempts finalized by status.",
    ["status"],
)

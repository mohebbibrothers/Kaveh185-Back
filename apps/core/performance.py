"""رهگیری زمان اجرای کوئری‌های دیتابیس و شمارش کوئری‌ها در هر درخواست HTTP."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any


class QueryPerformanceTracker:
    """Wrapper اتصال دیتابیس جنگو برای شمارش دقیق تعداد کوئری‌ها و زمان کل اجرای SQL."""

    def __init__(self) -> None:
        """مقداردهی شمارنده‌ها."""
        self.query_count: int = 0
        self.total_time_ms: float = 0.0

    def __call__(
        self,
        execute: Callable[..., Any],
        sql: str,
        params: Any,
        many: bool,
        context: dict[str, Any],
    ) -> Any:
        """ثبت زمان و تعداد هر فراخوانی SQL."""
        start = time.perf_counter()
        try:
            return execute(sql, params, many, context)
        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            self.query_count += 1
            self.total_time_ms += elapsed_ms

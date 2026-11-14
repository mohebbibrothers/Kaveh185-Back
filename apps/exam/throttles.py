"""محدودکننده‌های نرخ درخواست (Rate Limit) برای شروع آزمون و ثبت پاسخ."""

from __future__ import annotations

from rest_framework.throttling import UserRateThrottle


class ExamStartRateThrottle(UserRateThrottle):
    """محدودکنندهٔ نرخ شروع آزمون."""

    scope = "exam_start"


class ExamAnswerRateThrottle(UserRateThrottle):
    """محدودکنندهٔ نرخ ثبت پاسخ در حین آزمون."""

    scope = "exam_answer"

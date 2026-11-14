"""موتور محاسبهٔ امتیاز ترکیبی (پاسخ‌های درست + پاداش سرعت) و نمایش زمان آزمون."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ScoreBreakdown:
    """ساختار تفکیک‌شدهٔ امتیاز کارنامهٔ هر شرکت‌کننده."""

    base_score: float
    time_bonus_score: float
    total_score: float
    accuracy_percent: float


def compute_exam_score(
    *,
    correct_count: int,
    wrong_count: int,
    total_questions: int,
    duration_seconds: int,
    duration_limit_seconds: int,
    points_per_correct: float = 20.0,
    points_per_wrong: float = 0.0,
    max_time_bonus: float = 20.0,
) -> ScoreBreakdown:
    """محاسبهٔ امتیاز نهایی بر اساس تعداد سوالات درست و سرعت پاسخگویی.

    فرمول ریاضی:
    1) امتیاز پایه = `(correct_count * points_per_correct) + (wrong_count * points_per_wrong)`
    2) پاداش سرعت = `max_time_bonus * (correct_count / total_questions) * max(0, 1 - (duration_seconds / duration_limit_seconds))`
       نکتهٔ کلیدی: ضریب `(correct_count / total_questions)` تضمین می‌کند کسی که سوالات را
       بدون خواندن و شانسی در چند ثانیه غلط بزند، هیچ پاداش سرعتی نگیرد؛ اما بین افرادی که
       پاسخ صحیح داده‌اند، فرد سریع‌تر امتیاز بالاتری کسب کند.
    """
    safe_total = max(1, int(total_questions))
    safe_limit = max(1, int(duration_limit_seconds))
    clamped_duration = max(1, min(int(duration_seconds), safe_limit))

    raw_base = (int(correct_count) * float(points_per_correct)) + (
        int(wrong_count) * float(points_per_wrong)
    )
    base_score = round(max(0.0, raw_base), 2)

    accuracy_ratio = max(0.0, min(1.0, int(correct_count) / safe_total))
    speed_ratio = max(0.0, min(1.0, 1.0 - (clamped_duration / safe_limit)))

    time_bonus = round(float(max_time_bonus) * accuracy_ratio * speed_ratio, 2)
    total_score = round(base_score + time_bonus, 2)
    accuracy_percent = round(accuracy_ratio * 100.0, 2)

    return ScoreBreakdown(
        base_score=base_score,
        time_bonus_score=time_bonus,
        total_score=total_score,
        accuracy_percent=accuracy_percent,
    )


def format_duration_persian(duration_seconds: int) -> str:
    """تبدیل مدت زمان به ثانیه به متن خوانای فارسی (مثلاً `۲ دقیقه و ۱۵ ثانیه`)."""
    sec = max(0, int(duration_seconds))
    minutes = sec // 60
    rem_sec = sec % 60
    if minutes == 0:
        return f"{rem_sec} ثانیه"
    if rem_sec == 0:
        return f"{minutes} دقیقه"
    return f"{minutes} دقیقه و {rem_sec} ثانیه"

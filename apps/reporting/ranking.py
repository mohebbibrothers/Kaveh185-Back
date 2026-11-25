"""قاعدهٔ رتبه‌بندی، در یک جا — تا فهرستِ ادمین، CSV و اکسل هر سه یک عدد بدهند.

## چرا این ماژول جدا شد

پیش از این منطقِ مرتب‌سازی در `selectors.get_filtered_exam_attempts_queryset`
بود و فقط برای خروجیِ سنگینِ تحلیلی استفاده می‌شد. کپی‌کردنِ همان منطق در
صفحهٔ تازهٔ رتبه‌بندی یعنی **دو منبعِ حقیقت**: کافی بود یک نفر ترتیبِ
`duration_seconds` را در یکی عوض کند تا اکسل و پنل دو رتبهٔ متفاوت بدهند —
و در روزِ داوری، همین اختلاف سؤال می‌سازد. پس قاعده یک بار این‌جا نوشته
شده و همه از آن می‌خوانند.

## قاعدهٔ رتبه (قفل‌شده با تست)

۱. **امتیاز کل** نزولی
۲. **تعداد پاسخ درست** نزولی
۳. **زمانِ کمتر** (فقط وقتی جلسه تمام شده؛ برای جلسهٔ در جریان زمانِ
   ناتمام معنا ندارد و صفر است)
۴. **زمانِ ثبتِ زودتر**
۵. `id` — تا رتبه هیچ‌وقت بین دو درخواست نلرزد (پایدار بودنِ رتبه).

⚠️ قاعدهٔ ۳ عمداً «زمان کمتر» است نه «زمان بیشتر»: در آزمونِ امتیازدار،
سرعت پاداش دارد. اگر روزی این سیاست عوض شد، فقط همین تابع باید تغییر کند.
"""

from __future__ import annotations

from typing import Any

from django.db.models import Q, QuerySet

from apps.exam.choices import ExamAttemptStatus as Status
from apps.exam.models import ExamAttempt

#: وضعیت‌هایی که در رتبه‌بندی حساب می‌شوند.
ACTIVE_STATUSES = (Status.COMPLETED, Status.TIMED_OUT)

#: همهٔ مقادیرِ مجازِ فیلترِ وضعیت. صریح نوشته شده (نه `{s.value for s in Status}`)
#: چون mypy روی پیمایشِ کلاسِ `TextChoices` خطا می‌دهد و صریح‌بودن، منبعِ
#: حقیقت را هم شفاف می‌کند: اگر وضعیتِ تازه‌ای اضافه شد، همین‌جا دیده می‌شود.
STATUS_VALUES = ("in_progress", "completed", "timed_out")

#: اندازهٔ تکه در خواندن و نوشتنِ جریانی — با ۲۰۰ سطر، حافظه ثابت می‌ماند و
#: هر کوئری چند میلی‌ثانیه است (نه چند ثانیه).
RANKING_CHUNK_SIZE = 200

#: سرآیندِ اکسل/CSV — ترتیبش با `build_ranking_row` یکی است (تست دارد).
RANKING_EXPORT_HEADERS = [
    "رتبه",
    "کد رهگیری",
    "نام",
    "نام خانوادگی",
    "کد ملی",
    "شماره همراه",
    "مسجد",
    "محله",
    "درست",
    "غلط",
    "بی‌پاسخ",
    "درصد صحت",
    "زمان (ثانیه)",
    "امتیاز کل",
    "وضعیت",
]

#: نگاشتِ نامِ فیلتر به ستون — تنها منبعِ مجاز برای `ordering`.
ORDERING_FIELD_MAP: dict[str, str] = {
    "score": "total_score",
    "correct": "correct_count",
    "wrong": "wrong_count",
    "duration": "duration_seconds",
    "completed": "completed_at",
    "tracking": "tracking_code",
}

DEFAULT_ORDERING = ["-total_score", "-correct_count", "duration_seconds", "completed_at", "id"]


def ranking_queryset(filters: dict[str, Any] | None = None) -> QuerySet[ExamAttempt]:
    """کوئریِ مرتبِ رتبه‌بندی با اعمالِ فیلترهای سبک.

    Args:
        filters: کلیدهای مجاز: `mosque_id`، `status`، `min_score`، `max_score`،
            `search`، `ordering`. هر کلیدِ ناشناخته نادیده گرفته می‌شود.

    ⚠️ `only()` عمدی است. فهرستِ ادمین فقط ۱۵ ستون نشان می‌دهد؛ اگر
    `select_related` بدونِ `only` بنویسیم، هر سطر همهٔ ستون‌های متنی
    (`started_ip`, `user_agent`, ...) را هم می‌کشد و در ۱۰۰۰ سطر چند مگابایت
    اضافه از دیتابیس می‌خواند. برای همین فقط ستون‌های لازم را می‌خوانیم —
    ولی دقت: `user__full_name` یک property است، پس نام و نام خانوادگیِ خام
    را می‌گیریم.
    """
    params = filters or {}
    qs = ExamAttempt.objects.select_related("user", "mosque").only(
        "id",
        "tracking_code",
        "status",
        "total_questions",
        "correct_count",
        "wrong_count",
        "unanswered_count",
        "accuracy_percent",
        "duration_seconds",
        "duration_limit_seconds",
        "base_score",
        "time_bonus_score",
        "total_score",
        "completed_at",
        "started_at",
        "user__id",
        "user__first_name",
        "user__last_name",
        "user__phone_number",
        "user__national_id",
        "mosque__id",
        "mosque__name",
        "mosque__code",
        "mosque__neighborhood",
    )

    status_raw = str(params.get("status", "")).strip()
    if status_raw in STATUS_VALUES:
        qs = qs.filter(status=status_raw)
    elif status_raw != "all":
        # پیش‌فرض: فقط جلسه‌های پایان‌یافته. جلسهٔ در جریان هنوز امتیازِ نهایی
        # ندارد و اگر در فهرست بیاید، ادمین رتبهٔ غلط می‌بیند.
        qs = qs.filter(status__in=ACTIVE_STATUSES)

    mosque_id = params.get("mosque_id")
    if isinstance(mosque_id, int):
        qs = qs.filter(mosque_id=mosque_id)

    min_score = params.get("min_score")
    if isinstance(min_score, (int, float)):
        qs = qs.filter(total_score__gte=float(min_score))
    max_score = params.get("max_score")
    if isinstance(max_score, (int, float)):
        qs = qs.filter(total_score__lte=float(max_score))

    search = str(params.get("search", "")).strip()
    if search:
        qs = qs.filter(
            Q(tracking_code__icontains=search)
            | Q(user__first_name__icontains=search)
            | Q(user__last_name__icontains=search)
            | Q(user__phone_number__icontains=search)
            | Q(user__national_id__icontains=search)
            | Q(mosque__name__icontains=search)
        )

    ordering_raw = str(params.get("ordering", "")).strip()
    order_fields: list[str] = []
    for token in ordering_raw.split(",") if ordering_raw else []:
        mapped = ORDERING_FIELD_MAP.get(token.strip())
        if mapped:
            order_fields.append(mapped)

    if order_fields:
        # `id` آخر می‌آید تا ترتیبِ مساوی‌ها هم پایدار بماند.
        return qs.order_by(*order_fields, "id")
    return qs.order_by(*DEFAULT_ORDERING)


def build_ranking_row(attempt: ExamAttempt, *, rank: int) -> dict[str, Any]:
    """یک سطرِ آمادهٔ نمایش/اکسل از یک کارنامه.

    خروجی دو بخش دارد: `cells` (برای HTML) و `excel_row` (فهرستِ خام با همان
    ترتیبِ `RANKING_EXPORT_HEADERS`). هر دو از یک منبع می‌آیند تا جدول و فایل
    هیچ‌وقت از هم جدا نشوند.
    """
    user = attempt.user
    mosque = attempt.mosque
    status_label = Status(attempt.status).label if attempt.status else ""

    cells = {
        "rank": rank,
        "tracking_code": attempt.tracking_code,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "full_name": user.full_name,
        "national_id": user.national_id,
        "phone_number": user.phone_number,
        "mosque_name": mosque.name if mosque else "",
        "mosque_neighborhood": mosque.neighborhood if mosque else "",
        "correct_count": attempt.correct_count,
        "wrong_count": attempt.wrong_count,
        "unanswered_count": attempt.unanswered_count,
        "accuracy_percent": round(float(attempt.accuracy_percent), 1),
        "duration_seconds": attempt.duration_seconds,
        "total_score": round(float(attempt.total_score), 2),
        "status": attempt.status,
        "status_label": status_label,
    }

    excel_row = [
        rank,
        attempt.tracking_code,
        user.first_name,
        user.last_name,
        user.national_id,
        user.phone_number,
        mosque.name if mosque else "",
        mosque.neighborhood if mosque else "",
        attempt.correct_count,
        attempt.wrong_count,
        attempt.unanswered_count,
        round(float(attempt.accuracy_percent), 1),
        attempt.duration_seconds,
        round(float(attempt.total_score), 2),
        status_label,
    ]

    return {"cells": cells, "excel_row": excel_row}


__all__ = [
    "ACTIVE_STATUSES",
    "DEFAULT_ORDERING",
    "ORDERING_FIELD_MAP",
    "RANKING_CHUNK_SIZE",
    "RANKING_EXPORT_HEADERS",
    "STATUS_VALUES",
    "build_ranking_row",
    "ranking_queryset",
]

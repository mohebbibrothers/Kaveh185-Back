"""مقادیر ثابت و فهرست ۱۷ مسجد پیش‌فرض حوزه مقاومت بسیج ۱۸۵ شهید کاوه."""

from __future__ import annotations

from django.db import models


class MosqueTier(models.TextChoices):
    """سطح مشارکت مسجد در رقابت فرهنگی هفته بسیج."""

    GOLD = "gold", "پیشتاز طلایی"
    SILVER = "silver", "پرچمدار نقره‌ای"
    BRONZE = "bronze", "فعال برنزی"
    RISING = "rising", "در حال اوج‌گیری"


DEFAULT_KAVEH185_MOSQUES: tuple[dict[str, str | int], ...] = (
    {
        "code": "MSQ-01",
        "name": "مسجد جامع صاحب‌الزمان (عج)",
        "neighborhood": "منطقه ۱ — حوزه ۱۸۵ شهید کاوه",
        "display_order": 1,
        "target_participants": 500,
    },
    {
        "code": "MSQ-02",
        "name": "مسجد حضرت امیرالمؤمنین (ع)",
        "neighborhood": "منطقه ۲ — حوزه ۱۸۵ شهید کاوه",
        "display_order": 2,
        "target_participants": 500,
    },
    {
        "code": "MSQ-03",
        "name": "مسجد حضرت فاطمةالزهرا (س)",
        "neighborhood": "منطقه ۳ — حوزه ۱۸۵ شهید کاوه",
        "display_order": 3,
        "target_participants": 500,
    },
    {
        "code": "MSQ-04",
        "name": "مسجد امام حسن مجتبی (ع)",
        "neighborhood": "منطقه ۴ — حوزه ۱۸۵ شهید کاوه",
        "display_order": 4,
        "target_participants": 500,
    },
    {
        "code": "MSQ-05",
        "name": "مسجد سیدالشهدا (ع)",
        "neighborhood": "منطقه ۵ — حوزه ۱۸۵ شهید کاوه",
        "display_order": 5,
        "target_participants": 500,
    },
    {
        "code": "MSQ-06",
        "name": "مسجد امام سجاد (ع)",
        "neighborhood": "منطقه ۶ — حوزه ۱۸۵ شهید کاوه",
        "display_order": 6,
        "target_participants": 500,
    },
    {
        "code": "MSQ-07",
        "name": "مسجد امام محمد باقر (ع)",
        "neighborhood": "منطقه ۷ — حوزه ۱۸۵ شهید کاوه",
        "display_order": 7,
        "target_participants": 500,
    },
    {
        "code": "MSQ-08",
        "name": "مسجد امام جعفر صادق (ع)",
        "neighborhood": "منطقه ۸ — حوزه ۱۸۵ شهید کاوه",
        "display_order": 8,
        "target_participants": 500,
    },
    {
        "code": "MSQ-09",
        "name": "مسجد امام موسی کاظم (ع)",
        "neighborhood": "منطقه ۹ — حوزه ۱۸۵ شهید کاوه",
        "display_order": 9,
        "target_participants": 500,
    },
    {
        "code": "MSQ-10",
        "name": "مسجد امام رضا (ع)",
        "neighborhood": "منطقه ۱۰ — حوزه ۱۸۵ شهید کاوه",
        "display_order": 10,
        "target_participants": 500,
    },
    {
        "code": "MSQ-11",
        "name": "مسجد امام جواد (ع)",
        "neighborhood": "منطقه ۱۱ — حوزه ۱۸۵ شهید کاوه",
        "display_order": 11,
        "target_participants": 500,
    },
    {
        "code": "MSQ-12",
        "name": "مسجد امام هادی (ع)",
        "neighborhood": "منطقه ۱۲ — حوزه ۱۸۵ شهید کاوه",
        "display_order": 12,
        "target_participants": 500,
    },
    {
        "code": "MSQ-13",
        "name": "مسجد امام حسن عسکری (ع)",
        "neighborhood": "منطقه ۱۳ — حوزه ۱۸۵ شهید کاوه",
        "display_order": 13,
        "target_participants": 500,
    },
    {
        "code": "MSQ-14",
        "name": "مسجد حضرت ابوالفضل العباس (ع)",
        "neighborhood": "منطقه ۱۴ — حوزه ۱۸۵ شهید کاوه",
        "display_order": 14,
        "target_participants": 500,
    },
    {
        "code": "MSQ-15",
        "name": "مسجد حضرت زینب کبری (س)",
        "neighborhood": "منطقه ۱۵ — حوزه ۱۸۵ شهید کاوه",
        "display_order": 15,
        "target_participants": 500,
    },
    {
        "code": "MSQ-16",
        "name": "مسجد شهدا (پایگاه شهید کاوه)",
        "neighborhood": "منطقه ۱۶ — حوزه ۱۸۵ شهید کاوه",
        "display_order": 16,
        "target_participants": 500,
    },
    {
        "code": "MSQ-17",
        "name": "مسجد النبی (ص)",
        "neighborhood": "منطقه ۱۷ — حوزه ۱۸۵ شهید کاوه",
        "display_order": 17,
        "target_participants": 500,
    },
)

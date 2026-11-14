# ساختار پروژه — کاوه ۱۸۵ (Kaveh185)

> این فایل **به‌صورت خودکار** تولید شده است. دستی ویرایشش نکنید.
> بازتولید: `make structure` — بررسی عدم انحراف در CI: `make structure-check`

این سند نقشهٔ معماری واقعی مخزن **Kaveh185-Back** (سامانه مسابقه بزرگ فرهنگی و کتابخوانی
هفته بسیج — حوزه مقاومت بسیج ۱۸۵ شهید کاوه) را نشان می‌دهد و در هر اجرای CI با ساختار
واقعی کد تطبیق داده می‌شود.

## اپلیکیشن‌ها

مجموع: **8 اپ** · 16 مدل · 7 مایگریشن · 50 ویو · 52 مسیر

| اپ | مدل | مایگریشن | ویو | مسیر |
|---|---:|---:|---:|---:|
| `audit_logs` | 1 | 2 | 4 | 4 |
| `authentication` | 4 | 1 | 19 | 20 |
| `command_center` | 0 | 0 | 1 | 1 |
| `core` | 4 | 1 | 1 | 2 |
| `exam` | 5 | 1 | 13 | 13 |
| `mosques` | 1 | 1 | 5 | 5 |
| `notifications` | 1 | 1 | 3 | 3 |
| `reporting` | 0 | 0 | 4 | 4 |

## قرارداد لایه‌ها

هر اپ دامنه‌ای از تفکیک سخت‌گیرانهٔ مسئولیت‌ها پیروی می‌کند:

| فایل | مسئولیت |
|---|---|
| `models.py` | مدل‌های داده و قیود یکپارچگی دیتابیس |
| `selectors.py` | خواندن داده و کوئری‌های بهینه‌شده (بدون side effect) |
| `services.py` | منطق کسب‌وکار، تراکنش‌های اتمی و نوشتن |
| `serializers.py` | قرارداد اعتبارسنجی ورودی و خروجی |
| `views.py` | لایهٔ مرز HTTP و ارکستریشن |
| `filters.py` | فیلترهای پیشرفته و چندبعدی queryset |
| `permissions.py` | کنترل دسترسی نقش‌محور (RBAC) و Step-Up MFA |
| `tasks.py` | تسک‌های پس‌زمینه و Celery |
| `throttles.py` | محدودسازی نرخ و محافظت در برابر سوءاستفاده |
| `choices.py` | مقادیر ثابت و ماشین‌های حالت دامنه |
| `validators.py` | اعتبارسنج‌های قابل استفادهٔ مجدد (کدملی، موبایل، تاریخ جلالی) |
| `excel.py` | موتور تولید گزارش اکسل چندبرگی بازتولیدپذیر |
| `urls.py` | قرارداد مسیرهای API |

قواعدی که با گیت تست معماری (`tests/test_architecture_discipline.py`) به‌صورت خودکار اعمال می‌شوند:

- تمام ماژول‌های کد تولیدی (`apps/` و `config/`) باید دارای docstring سطح ماژول باشند.
- تمام کلاس‌ها و توابع سطح ماژول در کد تولیدی باید دارای docstring باشند.
- `views.py` حق ندارد مستقیماً روی manager یا queryset مدل عملیات نوشتن انجام دهد؛ تمام تغییرات باید از لایهٔ `services.py` عبور کنند.
- لایه‌های دامنه (`models.py`, `services.py`, `selectors.py`) نباید وابستگی معکوس به لایهٔ HTTP داشته باشند.
- استفاده از `print`، بدنهٔ خالی `pass`، زمان بدون منطقهٔ زمانی و `random` غیرامن در کد تولیدی ممنوع است.

## درخت دایرکتوری اپ‌ها (`apps/`)

```text
Kaveh185-Back/apps/
├── audit_logs/
│   ├── management/
│   ├── migrations/
│   ├── tests/
│   ├── __init__.py
│   ├── admin.py
│   ├── apps.py
│   ├── chain.py
│   ├── choices.py  # مقادیر ثابت و ماشین‌های حالت دامنه
│   ├── exporters.py
│   ├── filters.py  # فیلترهای پیشرفته و چندبعدی queryset
│   ├── models.py  # مدل‌های داده و قیود یکپارچگی دیتابیس
│   ├── selectors.py  # خواندن داده و کوئری‌های بهینه‌شده (بدون side effect)
│   ├── serializers.py  # قرارداد اعتبارسنجی ورودی و خروجی
│   ├── services.py  # منطق کسب‌وکار، تراکنش‌های اتمی و نوشتن
│   ├── urls.py  # قرارداد مسیرهای API
│   └── views.py  # لایهٔ مرز HTTP و ارکستریشن
├── authentication/
│   ├── management/
│   ├── migrations/
│   ├── tests/
│   ├── __init__.py
│   ├── admin.py
│   ├── anti_abuse.py
│   ├── apps.py
│   ├── choices.py  # مقادیر ثابت و ماشین‌های حالت دامنه
│   ├── constants.py
│   ├── deprecation.py
│   ├── filters.py  # فیلترهای پیشرفته و چندبعدی queryset
│   ├── jwt_auth.py
│   ├── managers.py
│   ├── models.py  # مدل‌های داده و قیود یکپارچگی دیتابیس
│   ├── otp.py
│   ├── permissions.py  # کنترل دسترسی نقش‌محور (RBAC) و Step-Up MFA
│   ├── selectors.py  # خواندن داده و کوئری‌های بهینه‌شده (بدون side effect)
│   ├── serializers.py  # قرارداد اعتبارسنجی ورودی و خروجی
│   ├── services.py  # منطق کسب‌وکار، تراکنش‌های اتمی و نوشتن
│   ├── throttles.py  # محدودسازی نرخ و محافظت در برابر سوءاستفاده
│   ├── totp.py
│   ├── urls.py  # قرارداد مسیرهای API
│   ├── validators.py  # اعتبارسنج‌های قابل استفادهٔ مجدد (کدملی، موبایل، تاریخ جلالی)
│   └── views.py  # لایهٔ مرز HTTP و ارکستریشن
├── command_center/
│   ├── migrations/
│   ├── tests/
│   ├── __init__.py
│   ├── apps.py
│   ├── selectors.py  # خواندن داده و کوئری‌های بهینه‌شده (بدون side effect)
│   ├── serializers.py  # قرارداد اعتبارسنجی ورودی و خروجی
│   ├── urls.py  # قرارداد مسیرهای API
│   └── views.py  # لایهٔ مرز HTTP و ارکستریشن
├── core/
│   ├── health/
│   ├── migrations/
│   ├── tests/
│   ├── __init__.py
│   ├── admin.py
│   ├── apps.py
│   ├── cache.py
│   ├── cache_invalidation.py
│   ├── cache_policy.py
│   ├── choices.py  # مقادیر ثابت و ماشین‌های حالت دامنه
│   ├── client_ip.py
│   ├── crypto.py
│   ├── docs_gate.py
│   ├── exceptions.py
│   ├── idempotency.py
│   ├── jalali.py
│   ├── metrics.py
│   ├── metrics_views.py
│   ├── middleware.py
│   ├── models.py  # مدل‌های داده و قیود یکپارچگی دیتابیس
│   ├── outbox.py
│   ├── pagination.py
│   ├── performance.py
│   ├── performance_contracts.py
│   ├── responses.py
│   ├── tasks.py  # تسک‌های پس‌زمینه و Celery
│   ├── urls.py  # قرارداد مسیرهای API
│   ├── uuid7.py
│   └── views.py  # لایهٔ مرز HTTP و ارکستریشن
├── exam/
│   ├── management/
│   ├── migrations/
│   ├── tests/
│   ├── __init__.py
│   ├── admin.py
│   ├── apps.py
│   ├── choices.py  # مقادیر ثابت و ماشین‌های حالت دامنه
│   ├── filters.py  # فیلترهای پیشرفته و چندبعدی queryset
│   ├── models.py  # مدل‌های داده و قیود یکپارچگی دیتابیس
│   ├── scoring.py
│   ├── selectors.py  # خواندن داده و کوئری‌های بهینه‌شده (بدون side effect)
│   ├── serializers.py  # قرارداد اعتبارسنجی ورودی و خروجی
│   ├── services.py  # منطق کسب‌وکار، تراکنش‌های اتمی و نوشتن
│   ├── throttles.py  # محدودسازی نرخ و محافظت در برابر سوءاستفاده
│   ├── urls.py  # قرارداد مسیرهای API
│   ├── validators.py  # اعتبارسنج‌های قابل استفادهٔ مجدد (کدملی، موبایل، تاریخ جلالی)
│   └── views.py  # لایهٔ مرز HTTP و ارکستریشن
├── mosques/
│   ├── management/
│   ├── migrations/
│   ├── tests/
│   ├── __init__.py
│   ├── admin.py
│   ├── apps.py
│   ├── choices.py  # مقادیر ثابت و ماشین‌های حالت دامنه
│   ├── filters.py  # فیلترهای پیشرفته و چندبعدی queryset
│   ├── models.py  # مدل‌های داده و قیود یکپارچگی دیتابیس
│   ├── selectors.py  # خواندن داده و کوئری‌های بهینه‌شده (بدون side effect)
│   ├── serializers.py  # قرارداد اعتبارسنجی ورودی و خروجی
│   ├── services.py  # منطق کسب‌وکار، تراکنش‌های اتمی و نوشتن
│   ├── urls.py  # قرارداد مسیرهای API
│   ├── validators.py  # اعتبارسنج‌های قابل استفادهٔ مجدد (کدملی، موبایل، تاریخ جلالی)
│   └── views.py  # لایهٔ مرز HTTP و ارکستریشن
├── notifications/
│   ├── migrations/
│   ├── tests/
│   ├── __init__.py
│   ├── admin.py
│   ├── apps.py
│   ├── choices.py  # مقادیر ثابت و ماشین‌های حالت دامنه
│   ├── models.py  # مدل‌های داده و قیود یکپارچگی دیتابیس
│   ├── providers.py
│   ├── selectors.py  # خواندن داده و کوئری‌های بهینه‌شده (بدون side effect)
│   ├── serializers.py  # قرارداد اعتبارسنجی ورودی و خروجی
│   ├── services.py  # منطق کسب‌وکار، تراکنش‌های اتمی و نوشتن
│   ├── urls.py  # قرارداد مسیرهای API
│   └── views.py  # لایهٔ مرز HTTP و ارکستریشن
├── reporting/
│   ├── migrations/
│   ├── tests/
│   ├── __init__.py
│   ├── apps.py
│   ├── excel_exporter.py
│   ├── selectors.py  # خواندن داده و کوئری‌های بهینه‌شده (بدون side effect)
│   ├── serializers.py  # قرارداد اعتبارسنجی ورودی و خروجی
│   ├── urls.py  # قرارداد مسیرهای API
│   └── views.py  # لایهٔ مرز HTTP و ارکستریشن
└── __init__.py
```

## زیرساخت مشترک (`apps/core`)

```text
apps/core/
├── health/
│   ├── __init__.py
│   ├── checks.py
│   ├── serializers.py  # قرارداد اعتبارسنجی ورودی و خروجی
│   ├── throttles.py  # محدودسازی نرخ و محافظت در برابر سوءاستفاده
│   ├── urls.py  # قرارداد مسیرهای API
│   └── views.py  # لایهٔ مرز HTTP و ارکستریشن
├── migrations/
│   ├── 0001_initial.py
│   └── __init__.py
├── tests/
│   ├── __init__.py
│   └── test_core_kernel.py
├── __init__.py
├── admin.py
├── apps.py
├── cache.py
├── cache_invalidation.py
├── cache_policy.py
├── choices.py  # مقادیر ثابت و ماشین‌های حالت دامنه
├── client_ip.py
├── crypto.py
├── docs_gate.py
├── exceptions.py
├── idempotency.py
├── jalali.py
├── metrics.py
├── metrics_views.py
├── middleware.py
├── models.py  # مدل‌های داده و قیود یکپارچگی دیتابیس
├── outbox.py
├── pagination.py
├── performance.py
├── performance_contracts.py
├── responses.py
├── tasks.py  # تسک‌های پس‌زمینه و Celery
├── urls.py  # قرارداد مسیرهای API
├── uuid7.py
└── views.py  # لایهٔ مرز HTTP و ارکستریشن
```

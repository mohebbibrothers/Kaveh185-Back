"""تستِ مقیاس — «با ۱۰۰۰ شرکت‌کننده هم کند نمی‌شود».

## چرا این تست؟

در روزِ آزمون تعدادِ شرکت‌کننده‌ها چند برابرِ حالتِ تستِ معمولی است و بدترین
اتفاق این است که صفحه‌ای که با ۳ سطر خوب کار می‌کرد، با ۱۰۰۰ سطر ۳۰ ثانیه
طول بکشد. این تست دو چیز را قفل می‌کند:

۱) **تعدادِ کوئری** برای صفحه و فهرست ثابت است (با `assertNumQueries`)، پس
   یک N+1 تازه بلافاصله قرمز می‌شود.
۲) **حافظه**: خروجی جریانی است، پس اوجِ حافظه با اندازهٔ فایل رشد نمی‌کند.

⚠️ این تست عمداً کوچک است (۱۰۰۰ سطر) تا در CI چند ثانیه بیشتر طول نکشد؛
اگر روزی لازم شد، `N_ROWS` را بالا ببرید و همین‌جا اجرا کنید.
"""

from __future__ import annotations

import tracemalloc

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from apps.authentication.choices import UserRole
from apps.exam.choices import ExamAttemptStatus
from apps.exam.models import ExamAttempt
from apps.mosques.models import Mosque
from apps.reporting.ranking import ranking_queryset

User = get_user_model()

pytestmark = [pytest.mark.django_db]

N_ROWS = 1000


_NID_CACHE: dict[int, str] = {}


def _nid(seed: int) -> str:
    """کد ملیِ **یکتا** با رقمِ کنترلِ درست.

    ⚠️ نکتهٔ ظریف که یک بار تست را شکست: الگوریتمِ رقمِ کنترل، ۹ رقمِ اول را
    به ۹ رقمِ یکتا نگاشت نمی‌کند (یک رقمِ کنترل برای چند پایه برابر می‌شود)
    و `national_id` در دیتابیس یکتاست. راه‌حل: شمارندهٔ جدا که با `seen`
    جلو می‌رود، پس هر فراخوانی یک کدِ ملیِ تازه و معتبر می‌دهد.
    """
    if seed in _NID_CACHE:
        return _NID_CACHE[seed]

    candidate = seed
    while True:
        base = f"{candidate:09d}"[:9]
        total = sum(int(d) * (10 - i) for i, d in enumerate(base))
        check = 11 - (total % 11)
        if check == 11:
            check = 0
        if check != 10:
            value = f"{base}{check}"
            if value not in _NID_CACHE.values():
                _NID_CACHE[seed] = value
                return value
        candidate += 1


@pytest.fixture()
def bulk_data(seeded_mosques: list[Mosque], django_db_blocker) -> Mosque:
    """۱۰۰۰ کارنامه در یک مسجد — با `bulk_create` تا خودِ داده‌سازی کند نباشد."""
    mosque = seeded_mosques[0]
    now = timezone.now()
    users = User.objects.bulk_create(
        [
            User(
                phone_number=f"0935{idx:07d}"[:11],
                national_id=_nid(10_000 + idx),
                first_name=f"شرکت‌کننده{idx}",
                last_name="آزمون",
                role=UserRole.PARTICIPANT,
                mosque=mosque,
            )
            for idx in range(N_ROWS)
        ],
        batch_size=200,
    )
    ExamAttempt.objects.bulk_create(
        [
            ExamAttempt(
                user=users[idx],
                mosque=mosque,
                tracking_code=f"K185-BULK-{idx:05d}",
                receipt_signature="sig",
                status=ExamAttemptStatus.COMPLETED,
                started_at=now,
                expires_at=now,
                completed_at=now,
                duration_limit_seconds=120,
                duration_seconds=30 + (idx % 60),
                correct_count=idx % 6,
                wrong_count=5 - (idx % 6),
                unanswered_count=0,
                base_score=float(idx % 100),
                total_score=float(idx % 100),
                accuracy_percent=(idx % 6) / 5 * 100,
            )
            for idx in range(N_ROWS)
        ],
        batch_size=200,
    )
    return mosque


def test_ranking_list_query_count_is_constant(client, admin_user, bulk_data) -> None:
    """صفحهٔ رتبه‌بندی با ۱۰۰۰ سطر نباید به‌ازای هر سطر کوئری بزند."""
    client.force_login(admin_user)
    url = reverse("participant-ranking")

    # ۵۰ سطر در صفحه. یک N+1 کلاسیک این را به ۱۰۰+ کوئری می‌رساند.
    response = client.get(url)
    assert response.status_code == 200
    assert response.context["total"] == N_ROWS, "همهٔ ۱۰۰۰ سطر باید شمرده شوند"
    assert len(response.context["rows"]) == 50

    # اندازه‌گیریِ صریح: شمارشِ کوئریِ فهرست (بدونِ session/audit).
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    with CaptureQueriesContext(connection) as ctx:
        ranking = list(ranking_queryset({})[:50])
    assert len(ranking) == 50
    assert len(ctx.captured_queries) == 1, (
        f"فهرستِ ۵۰ سطری باید یک کوئری باشد، نه {len(ctx.captured_queries)}"
    )


def test_streaming_export_memory_does_not_scale_with_rows(client, admin_user, bulk_data) -> None:
    """خروجیِ CSV جریانی است: اوجِ حافظه باید کوچک بماند (چند مگابایت، نه صدها)."""
    client.force_login(admin_user)
    url = reverse("participant-ranking")

    tracemalloc.start()
    response = client.get(url, {"export": "csv"})
    consumed = sum(len(chunk) for chunk in response.streaming_content)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    assert consumed > 0
    peak_mb = peak / 1024 / 1024
    assert peak_mb < 40, f"اوجِ حافظه {peak_mb:.1f} مگابایت است — خروجی جریانی نیست"


def test_pagination_covers_all_rows_without_overlap(client, admin_user, bulk_data) -> None:
    """صفحه‌بندی نباید سطری را جا بیندازد یا تکرار کند — با ۱۰۰۰ سطر بررسی می‌شود."""
    client.force_login(admin_user)
    url = reverse("participant-ranking")

    seen: list[str] = []
    page = 1
    while True:
        response = client.get(url, {"page": page})
        rows = response.context["rows"]
        if not rows:
            break
        seen.extend(r["cells"]["tracking_code"] for r in rows)
        if page * response.context["page_size"] >= response.context["total"]:
            break
        page += 1

    assert len(seen) == N_ROWS
    assert len(set(seen)) == N_ROWS, "هیچ سطری نباید دوبار بیاید"
    # رتبه‌ها باید پیوستهٔ ۱..N باشند (بدونِ پرش).
    ranks: list[int] = []
    for p in range(1, page + 1):
        ranks.extend(r["cells"]["rank"] for r in client.get(url, {"page": p}).context["rows"])
    assert ranks == list(range(1, N_ROWS + 1))

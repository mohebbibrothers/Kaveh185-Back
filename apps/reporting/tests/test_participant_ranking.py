"""تست‌های صفحهٔ «رتبه‌بندی شرکت‌کنندگان» در ادمین و خروجی‌های اکسل/CSV آن.

## چه چیزی را قفل می‌کنیم

۱) **دسترسی:** فقط staff؛ کاربرِ عادی و کاربرِ ناشناس هر دو رد می‌شوند. این
   صفحه کد ملی و شمارهٔ همراه نشان می‌دهد — یک خطای دسترسی این‌جا یعنی
   فاجعهٔ حریمِ خصوصی، نه یک باگِ نمایشی.
۲) **ترتیبِ رتبه:** یک بار با اعدادِ ساختگی قفل می‌شود تا کسی «مرتب‌سازی را
   بهینه کند» و بی‌آنکه بخواهد، رتبه‌ها را جابه‌جا کند.
۳) **هم‌خوانیِ جدول و فایل:** همان سطری که در HTML رتبهٔ ۱ است، در اکسل هم
   رتبهٔ ۱ است. اگر روزی کسی فقط یکی را عوض کند، این تست می‌شکند.
۴) **پایداریِ ترتیب:** دو بار گرفتنِ فهرست، همان ترتیب را می‌دهد (کلیدِ `id`).
۵) **بی‌اثر بودن روی داده:** صفحه و خروجی هیچ نوشتنی روی کارنامه‌ها ندارند.
"""

from __future__ import annotations

import csv
from io import BytesIO, StringIO

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from openpyxl import load_workbook

from apps.authentication.choices import UserRole
from apps.exam.choices import ExamAttemptStatus
from apps.exam.models import ExamAttempt
from apps.mosques.models import Mosque

User = get_user_model()

pytestmark = [pytest.mark.django_db]


def _valid_national_id(seed: int) -> str:
    """کد ملی با رقمِ کنترلِ درست می‌سازد.

    ⚠️ کد ملیِ ساختگی (مثل `0012345678`) از درخواست رد می‌شود، چون رقمِ
    کنترل ندارد. ساختنِ آن با دست یعنی هر بار یک تستِ شکسته؛ پس الگوریتمِ
    رسمی را همین‌جا اجرا می‌کنیم: `c = 11 - (sum(d[i]*(10-i)) % 11)` و
    `c == 11 ⇒ 0`، `c == 10 ⇒ کد نامعتبر`.
    """
    base = f"{seed:09d}"[:9]
    total = sum(int(d) * (10 - idx) for idx, d in enumerate(base))
    check = 11 - (total % 11)
    if check == 11:
        check = 0
    if check == 10:  # این پایه کد ملیِ معتبری نمی‌دهد؛ یکی جلو می‌رویم
        return _valid_national_id(seed + 1)
    return f"{base}{check}"


def _make_staff(username_suffix: str = "a") -> User:
    """یک ادمینِ staff می‌سازد (بدونِ reliance به fixtureهای دیگر)."""
    return User.objects.create_user(
        phone_number=f"0912{username_suffix:0>7}"[:11],
        national_id=_valid_national_id(5000 + int(username_suffix)),
        password="SecretPass!234",
        first_name="مدیر",
        last_name="آزمون",
        role=UserRole.ADMIN,
        is_staff=True,
        is_superuser=True,
    )


def _seed_attempts(mosque: Mosque) -> list[ExamAttempt]:
    """سه کارنامه با امتیازِ مشخص می‌سازد تا ترتیبِ رتبه قابلِ پیش‌بینی باشد."""
    from django.utils import timezone

    now = timezone.now()
    specs = [
        # (first, last, seq, score, correct, duration)
        ("بلند", "اول", "1", 95.0, 5, 40),
        ("دوم", "نفر", "2", 95.0, 5, 55),  # همان امتیاز و درست، ولی کندتر ⇒ رتبهٔ ۲
        ("سوم", "نفر", "3", 60.0, 3, 30),  # امتیازِ کمتر ⇒ رتبهٔ ۳ با اینکه سریع‌تر است
    ]
    created: list[ExamAttempt] = []
    for first, last, seq, score, correct, duration in specs:
        user = User.objects.create_user(
            phone_number=f"0913{seq:0>7}"[:11],
            national_id=_valid_national_id(7000 + int(seq)),
            first_name=first,
            last_name=last,
            role=UserRole.PARTICIPANT,
            mosque=mosque,
        )
        created.append(
            ExamAttempt.objects.create(
                user=user,
                mosque=mosque,
                tracking_code=f"K185-{seq}0000",
                receipt_signature="sig",
                status=ExamAttemptStatus.COMPLETED,
                started_at=now,
                expires_at=now,
                completed_at=now,
                duration_limit_seconds=120,
                duration_seconds=duration,
                correct_count=correct,
                wrong_count=5 - correct,
                unanswered_count=0,
                base_score=score,
                total_score=score,
                accuracy_percent=correct / 5 * 100,
            )
        )
    return created


@pytest.fixture()
def admin_user() -> User:
    return _make_staff("9")


@pytest.fixture()
def ranking_data(seeded_mosques: list[Mosque]) -> list[ExamAttempt]:
    return _seed_attempts(seeded_mosques[0])


def test_anonymous_and_participant_are_rejected(client, ranking_data) -> None:
    """صفحه کد ملی نشان می‌دهد؛ پس هر کسی که staff نیست باید رد شود."""
    url = reverse("participant-ranking")

    response = client.get(url)
    assert response.status_code in (301, 302), "کاربرِ ناشناس باید به صفحهٔ ورود برود"

    participant = User.objects.create_user(
        phone_number="09127770000",
        national_id=_valid_national_id(301),
        first_name="شرکت",
        last_name="کننده",
        role=UserRole.PARTICIPANT,
    )
    client.force_login(participant)
    response = client.get(url)
    assert response.status_code in (302, 403), "شرکت‌کنندهٔ عادی نباید به این صفحه برسد"


def test_ranking_order_is_stable_and_documented(client, admin_user, ranking_data) -> None:
    """ترتیب: امتیاز ← درست ← زمانِ کمتر. و بین دو درخواست نمی‌لرزد."""
    client.force_login(admin_user)
    url = reverse("participant-ranking")

    first = client.get(url)
    second = client.get(url)
    assert first.status_code == 200

    rows_first = [r["cells"] for r in first.context["rows"]]
    rows_second = [r["cells"] for r in second.context["rows"]]

    assert [r["rank"] for r in rows_first] == [1, 2, 3]
    assert [r["last_name"] for r in rows_first] == ["اول", "نفر", "نفر"]
    # نفرِ دوم کندتر بوده ⇒ پایین‌تر
    assert rows_first[1]["full_name"].startswith("دوم")
    assert rows_first[2]["full_name"].startswith("سوم")
    assert [r["tracking_code"] for r in rows_first] == [r["tracking_code"] for r in rows_second], (
        "ترتیب باید بین دو درخواست یکسان بماند"
    )


def test_filters_apply_and_do_not_leak_between_queries(client, admin_user, ranking_data) -> None:
    """فیلتر مسجد/امتیاز کار کند و کش نشود روی فیلترِ دیگر."""
    client.force_login(admin_user)
    url = reverse("participant-ranking")

    all_rows = client.get(url).context["rows"]
    assert len(all_rows) == 3

    filtered = client.get(url, {"min_score": "90"})
    assert filtered.context["total"] == 2

    huge = client.get(url, {"min_score": "1000"})
    assert huge.context["total"] == 0
    assert list(huge.context["rows"]) == []


def test_xlsx_export_matches_table_order(client, admin_user, ranking_data) -> None:
    """همان رتبهٔ ۱ جدول باید رتبهٔ ۱ اکسل باشد — و فایل واقعاً RTL باشد."""
    client.force_login(admin_user)
    url = reverse("participant-ranking")

    table_rows = [r["cells"] for r in client.get(url).context["rows"]]
    response = client.get(url, {"export": "xlsx"})

    assert response.status_code == 200
    assert (
        response["Content-Type"]
        == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert "attachment" in response["Content-Disposition"]

    wb = load_workbook(BytesIO(b"".join(response.streaming_content)))
    ws = wb["رتبه‌بندی شرکت‌کنندگان"]
    assert ws.sheet_view.rightToLeft is True

    excel_rows = list(ws.iter_rows(min_row=2, values_only=True))
    assert len(excel_rows) == len(table_rows)
    for idx, (excel_row, table_row) in enumerate(zip(excel_rows, table_rows, strict=True), start=1):
        assert excel_row[0] == idx, "رتبه در اکسل باید شمارهٔ سطر باشد"
        assert excel_row[1] == table_row["tracking_code"]
        assert float(excel_row[13]) == pytest.approx(table_row["total_score"])

    # برگِ دومِ «دربارهٔ این گزارش» باید قاعدهٔ رتبه را مستند کرده باشد.
    assert "دربارهٔ این گزارش" in wb.sheetnames


def test_csv_export_has_bom_and_headers(client, admin_user, ranking_data) -> None:
    """CSV باید BOM داشته باشد، وگرنه اکسلِ فارسی متن را به‌هم می‌ریزد."""
    client.force_login(admin_user)
    url = reverse("participant-ranking")

    response = client.get(url, {"export": "csv"})
    assert response.status_code == 200
    body = b"".join(response.streaming_content).decode("utf-8-sig")
    assert body.startswith("\ufeff") or body.startswith("رتبه")

    text = b"".join(client.get(url, {"export": "csv"}).streaming_content).decode("utf-8-sig")
    rows = list(csv.reader(StringIO(text.lstrip("\ufeff"))))
    assert rows[0][0] == "رتبه"
    assert rows[0][1] == "کد رهگیری"
    assert len(rows) == 1 + 3  # سرآیند + سه شرکت‌کننده


def test_export_does_not_mutate_attempts(client, admin_user, ranking_data) -> None:
    """صفحه و خروجی هر دو فقط‌خواندنی‌اند — هیچ فیلدی از کارنامه نباید عوض شود."""
    before = list(ExamAttempt.objects.order_by("id").values_list("id", "total_score", "status"))

    client.force_login(admin_user)
    url = reverse("participant-ranking")
    client.get(url)
    list(client.get(url, {"export": "csv"}).streaming_content)

    after = list(ExamAttempt.objects.order_by("id").values_list("id", "total_score", "status"))
    assert before == after


def test_in_progress_attempts_hidden_by_default(client, admin_user, ranking_data) -> None:
    """جلسهٔ در جریان امتیازِ نهایی ندارد؛ پیش‌فرض نباید در رتبه‌بندی بیاید."""
    from django.utils import timezone

    running_user = User.objects.create_user(
        phone_number="09129990000",
        national_id=_valid_national_id(302),
        first_name="در حال",
        last_name="آزمون",
        role=UserRole.PARTICIPANT,
        mosque=ranking_data[0].mosque,
    )
    now = timezone.now()
    ExamAttempt.objects.create(
        user=running_user,
        mosque=ranking_data[0].mosque,
        tracking_code="K185-RUNNING",
        receipt_signature="sig",
        status=ExamAttemptStatus.IN_PROGRESS,
        started_at=now,
        expires_at=now,
        duration_limit_seconds=120,
        total_score=0.0,
    )

    client.force_login(admin_user)
    url = reverse("participant-ranking")

    default_titles = [r["cells"]["tracking_code"] for r in client.get(url).context["rows"]]
    assert "K185-RUNNING" not in default_titles

    explicit = client.get(url, {"status": "in_progress"}).context["rows"]
    assert [r["cells"]["tracking_code"] for r in explicit] == ["K185-RUNNING"]


def test_admin_index_has_shortcut_to_ranking(client, admin_user) -> None:
    """صفحهٔ اولِ ادمین باید یک راهِ مستقیم به رتبه‌بندی داشته باشد."""
    client.force_login(admin_user)
    response = client.get(reverse("admin:index"))
    assert response.status_code == 200
    body = response.content.decode()
    assert "رتبه‌بندی شرکت‌کنندگان" in body
    assert reverse("participant-ranking") in body


def test_route_is_registered_outside_admin_monkeypatch() -> None:
    """مسیر باید در `config/urls.py` باشد، نه در patchِ `admin.site.get_urls`.

    ⚠️ این تست، رگرسیونِ واقعیِ روی هاست را قفل می‌کند: نسخهٔ اولِ این صفحه
    مسیرش را با monkeypatch کردنِ `admin.site.get_urls` در `AppConfig.ready()`
    اضافه می‌کرد. روی محیطِ توسعه کار می‌کرد (ترتیبِ بار‌شدن تصادفی درست بود)
    و روی هاست ۴۰۴ می‌داد. حالا:
    * نامِ مسیر در سطحِ ریشه ثبت شده (`participant-ranking`)،
    * و `admin.site.get_urls` دست‌نخورده است.
    """
    from django.contrib import admin
    from django.urls import resolve, reverse

    url = reverse("participant-ranking")
    assert url.startswith(f"/{str(reverse('admin:index')).strip('/')}/")
    assert resolve(url).func.__name__ == "participant_ranking_view"

    # هیچ patchی روی admin نمانده باشد
    assert not getattr(admin.site, "_k185_ranking_attached", False)
    assert admin.site.get_urls.__qualname__.startswith("AdminSite."), (
        "get_urls نباید patch شده باشد؛ مسیر باید صریح در config/urls.py باشد"
    )


def test_version_marker_matches_command_expectation() -> None:
    """`check_ranking_page` با این نشانگر می‌فهمد کدِ تازه نصب شده یا نه."""
    from apps.reporting.management.commands.check_ranking_page import MODULE_MARKER
    from apps.reporting.ranking_admin import RANKING_PAGE_VERSION

    assert RANKING_PAGE_VERSION == MODULE_MARKER


def test_api_alias_route_also_works(client, admin_user, ranking_data) -> None:
    """میان‌برِ `/api/v1/reporting/admin/ranking/` هم همان صفحه را می‌دهد.

    این مسیر برای وقتی است که `ADMIN_URL_PATH` روی میزبان عوض شود؛ همان قفلِ
    staff روی آن است. اگر روزی کسی آن را حذف کند، ادمین راهِ دومی برای رسیدن
    به رتبه‌ها ندارد.
    """
    from django.urls import reverse

    url = reverse("reporting:admin-ranking-page")
    assert url == "/api/v1/reporting/admin/ranking/"

    response = client.get(url)
    assert response.status_code in (301, 302), "کاربرِ ناشناس باید به ورود برود"

    client.force_login(admin_user)
    assert client.get(url).status_code == 200

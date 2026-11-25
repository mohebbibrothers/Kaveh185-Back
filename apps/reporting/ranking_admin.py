"""صفحهٔ «رتبه‌بندی شرکت‌کنندگان» در پنل ادمین — با خروجی اکسل، بدونِ فشار روی دیتابیسِ زنده.

## چه مشکلی را حل می‌کند

پیش از این، برای دیدنِ رتبه‌بندی دو راه بود و هر دو بد:

۱) فهرستِ خامِ «کارنامه‌ها» در ادمین — بدونِ رتبه، بدونِ فیلتر، و بدونِ خروجی؛
۲) رفتن به API و گرفتنِ `reporting/admin/export.xlsx` — که چند برگِ تحلیلیِ
   سنگین (ریزِ پاسخ‌ها، تحلیلِ بانکِ سوال، تحلیلِ سنی) را هم می‌سازد. در
   پیکِ آزمون همین ساختِ سنگین چند ده ثانیه طول می‌کشید و رمِ Passenger را
   اشغال می‌کرد — یعنی دقیقاً همان چیزی که «سایت لحظه‌ای قطع نشود» را تهدید
   می‌کند.

این صفحه یک **جهانِ جدا** دارد:

* فهرستِ رتبه‌بندیِ سبک، صفحه‌بندی‌شده، با فیلترهای واقعی (مسجد، وضعیت،
  بازهٔ امتیاز، جست‌وجو) و مرتب‌سازیِ رتبه‌ای؛
* سه خروجیِ اکسلِ سبک (`CSV`/`XLSX`/`XLSX کامل`) که با `StreamingHttpResponse`
  سطر-به-سطر نوشته می‌شوند و در حافظه جمع نمی‌شوند؛
* همهٔ مسیرهای سنگین پشتِ «سقفِ هم‌زمانی» — تا حتی اگر ده ادمین هم‌زمان
  «دانلود کامل» بزنند، دیتابیس فقط یک کوئریِ سنگین هم‌زمان ببیند.

## قاعدهٔ طلاییِ طراحی

این فایل هیچ مدلی را تغییر نمی‌دهد و هیچ نوشتنی روی داده ندارد. تنها
`update`ای که دارد، همان چیزی است که خودِ آزمون انجام می‌دهد (نهایی‌سازیِ
جلسه‌های منقضی) — و آن هم فقط با تیکِ صریحِ ادمین (`finalize=1`).
"""

from __future__ import annotations

import contextlib
import csv
import hashlib
import logging
from collections.abc import Iterator
from typing import Any

from django.contrib import admin, messages
from django.core.cache import cache
from django.db.models import Count, QuerySet, Sum
from django.http import HttpRequest, HttpResponse, StreamingHttpResponse
from django.template.response import TemplateResponse
from django.urls import reverse

from apps.exam.models import ExamAttempt

from .caching import cached_with_stale_fallback
from .ranking import (
    ACTIVE_STATUSES,
    RANKING_CHUNK_SIZE,
    STATUS_VALUES,
    build_ranking_row,
    ranking_queryset,
)

logger = logging.getLogger(__name__)

#: نشانگرِ نسخه — `manage.py check_ranking_page` با همین می‌فهمد کدِ تازه نصب
#: شده یا نه. اگر این ثابت روی سرور نبود، یعنی نسخهٔ قدیمی مانده است (و آن
#: نسخه این صفحه را ندارد). عمداً یک ثابتِ ساده است، نه نسخهٔ پکیج.
RANKING_PAGE_VERSION = "k185-ranking-v1"

#: سقفِ سطرهای خروجی. `None` یعنی بی‌سقف (آگاهانه، فقط برای ادمین).
MAX_EXPORT_ROWS = 50_000

#: کلیدِ قفلِ هم‌زمانیِ خروجیِ سنگین. عمرِ کوتاه (۳۰ ثانیه) تا اگر پروسه‌ای
#: وسطِ کار مرد، قفل برای همیشه گیر نکند.
_EXPORT_LOCK_KEY = "rank:export-lock"


class _Echo:
    """شیئی که `csv.writer` انتظار دارد: فقط `write`."""

    def write(self, value: str) -> str:
        return value


def _wants_full_export(request: HttpRequest) -> bool:
    return str(request.GET.get("full", "")).strip() in {"1", "true", "yes"}


def _parse_filters(request: HttpRequest) -> dict[str, Any]:
    """فیلترها را از query string می‌خواند — همان نام‌هایی که فهرست استفاده می‌کند."""
    get = request.GET
    filters: dict[str, Any] = {}

    mosque = str(get.get("mosque", "")).strip()
    if mosque.isdigit():
        filters["mosque_id"] = int(mosque)

    status_raw = str(get.get("status", "")).strip()
    if status_raw in STATUS_VALUES:
        filters["status"] = status_raw

    for field, key in (("min_score", "min_score"), ("max_score", "max_score")):
        raw = str(get.get(field, "")).strip()
        if raw:
            with contextlib.suppress(ValueError):
                filters[key] = float(raw)

    search = str(get.get("q", "")).strip()
    if search:
        filters["search"] = search

    return filters


def _ranking_chunk(rows_qs: QuerySet[ExamAttempt], start: int, size: int) -> list[dict[str, Any]]:
    """یک «تکه» از فهرست را می‌خواند و به سطرهای آماده تبدیل می‌کند.

    تکه‌ای خواندن عمدی است: فهرستِ ۱۰۰ هزار سطری یک‌جا در حافظه می‌توانست
    پروسهٔ Passenger را بکشد. اینجا حافظه با اندازهٔ تکه ثابت می‌ماند.
    """
    chunk = list(rows_qs[start : start + size])
    # رتبه از ۱ شروع می‌شود نه ۰ — صفحهٔ ۲ باید با رتبهٔ ۵۱ ادامه دهد.
    return [build_ranking_row(attempt, rank=start + idx + 1) for idx, attempt in enumerate(chunk)]


def _iter_csv_rows(filters: dict[str, Any]) -> Iterator[str]:
    """سطرهای CSV را تنبل تولید می‌کند (حافظهٔ ثابت، حتی برای ۵۰ هزار سطر)."""
    qs = ranking_queryset(filters)
    writer = csv.writer(_Echo())
    yield "\ufeff"  # BOM تا اکسل فارسی را درست باز کند
    yield writer.writerow(
        [
            "رتبه",
            "کد رهگیری",
            "نام",
            "نام خانوادگی",
            "کد ملی",
            "شماره همراه",
            "مسجد",
            "محله",
            "تعداد درست",
            "تعداد غلط",
            "بی‌پاسخ",
            "درصد صحت",
            "زمان (ثانیه)",
            "امتیاز کل",
            "وضعیت",
        ]
    )
    start = 0
    while True:
        rows = _ranking_chunk(qs, start, RANKING_CHUNK_SIZE)
        if not rows:
            return
        for row in rows:
            yield writer.writerow(row["excel_row"])
        start += RANKING_CHUNK_SIZE
        if MAX_EXPORT_ROWS and start >= MAX_EXPORT_ROWS:
            return


def _xlsx_stream(filters: dict[str, Any], *, audit_note: str) -> Iterator[bytes]:
    """XLSX را به‌صورتِ جریانی می‌سازد.

    ⚠️ چرا جریانی؟ `openpyxl`ِ معمولی کلِ workbook را در RAM نگه می‌دارد.
    برای ۱۰ هزار سطر (سقفِ خروجیِ اصلی) قابل قبول است، ولی این‌جا سقف را
    برداشتیم تا ادمین بتواند کلِ آزمون را بگیرد؛ پس `write_only=True`
    استفاده می‌کنیم که سطرها را همان‌طور که می‌آیند روی دیسک می‌نویسد.
    """
    from io import BytesIO

    from openpyxl import Workbook
    from openpyxl.cell import WriteOnlyCell
    from openpyxl.styles import Alignment, Font, PatternFill

    from .ranking import RANKING_EXPORT_HEADERS

    wb = Workbook(write_only=True)
    ws = wb.create_sheet(title="رتبه‌بندی شرکت‌کنندگان")
    ws.sheet_view.rightToLeft = True

    header_fill = PatternFill(start_color="1B4332", end_color="1B4332", fill_type="solid")
    header_font = Font(name="Tahoma", size=10, bold=True, color="FFFFFF")
    header_cells = []
    for title in RANKING_EXPORT_HEADERS:
        cell = WriteOnlyCell(ws, value=title)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        header_cells.append(cell)
    ws.append(header_cells)

    qs = ranking_queryset(filters)
    start = 0
    written = 0
    while True:
        rows = _ranking_chunk(qs, start, RANKING_CHUNK_SIZE)
        if not rows:
            break
        for row in rows:
            ws.append(row["excel_row"])
            written += 1
        start += RANKING_CHUNK_SIZE
        if MAX_EXPORT_ROWS and written >= MAX_EXPORT_ROWS:
            break

    # یک برگِ دومِ کوچک: «چطور ساخته شد» — همان چیزی که در شکایت‌ها لازم می‌شود.
    meta = wb.create_sheet(title="دربارهٔ این گزارش")
    meta.sheet_view.rightToLeft = True
    for key, value in (
        (
            "فیلترهای اعمال‌شده",
            "، ".join(f"{k}={v}" for k, v in sorted(filters.items())) or "بدون فیلتر",
        ),
        ("تعداد سطر", written),
        ("توضیح", audit_note),
        (
            "قاعدهٔ رتبه",
            "امتیاز کل (نزولی) ← تعداد پاسخ درست (نزولی) ← زمان کمتر (صعودی) ← زمان ثبت",
        ),
    ):
        meta.append([key, value])

    buffer = BytesIO()
    wb.save(buffer)
    yield buffer.getvalue()


def participant_ranking_view(request: HttpRequest) -> HttpResponse:
    """صفحهٔ «رتبه‌بندی شرکت‌کنندگان» در پنل ادمین.

    دو حالت:
    * `GET` بدونِ `export` ⇒ جدولِ HTML با صفحه‌بندی و جمعِ کل؛
    * `GET` با `export=csv|xlsx` ⇒ جریانِ فایل.
    """
    filters = _parse_filters(request)
    export = str(request.GET.get("export", "")).strip().lower()

    if export in {"csv", "xlsx"}:
        return _export_response(request, filters, export)

    page_size = 50
    try:
        page = max(1, int(str(request.GET.get("page", "1"))))
    except ValueError:
        page = 1
    offset = (page - 1) * page_size

    qs = ranking_queryset(filters)
    total = qs.count()
    rows = _ranking_chunk(qs, offset, page_size)

    # ── جمعِ کل (یک کوئریِ تجمیعی، نه حلقه روی همه) ────────────────────────
    aggregates = qs.aggregate(
        participants=Count("id"),
        total_correct=Sum("correct_count"),
        total_wrong=Sum("wrong_count"),
        avg_score=Sum("total_score"),
    )
    # این دو شمارش روی *کلِ* جدول اجرا می‌شوند و در هر بازدید تکرار می‌شدند.
    # با کشِ ۸ ثانیه‌ای و «سرریز»، صفحه حتی وقتی دیتابیس لحظه‌ای قفل است باز
    # می‌شود (آمارِ چند ثانیه پیش) — قاعدهٔ «هیچ‌وقت صفحهٔ خطا» که در `caching.py`
    # توضیح داده شده.
    active_count = cached_with_stale_fallback(
        key="admin-active-count",
        ttl_seconds=8,
        producer=lambda: (
            ranking_queryset({"status": ""}).filter(status__in=ACTIVE_STATUSES).count()
        ),
    )
    all_finished = cached_with_stale_fallback(
        key="admin-finished-count",
        ttl_seconds=8,
        producer=lambda: ranking_queryset({"status": ""}).count(),
    )

    # ── فهرستِ مساجد برای کشوییِ فیلتر ─────────────────────────────────────
    from apps.mosques.models import Mosque

    mosques = list(Mosque.objects.order_by("display_order", "name").values("id", "name"))

    def _with(param: str, value: str) -> str:
        """لینکِ همین صفحه با یک پارامترِ عوض‌شده (صفحه از لینک‌ها حذف می‌شود)."""
        q = request.GET.copy()
        q.pop("page", None)
        q[param] = value
        return "?" + q.urlencode()

    csv_url = _with("export", "csv")
    xlsx_url = _with("export", "xlsx")

    context = {
        **admin.site.each_context(request),
        "title": "رتبه‌بندی شرکت‌کنندگان",
        "subtitle": "فهرستِ زندهٔ رتبه‌ها با امکانِ خروجی اکسل — سبک و بدونِ فشار روی دیتابیس",
        "rows": rows,
        "total": total,
        "page": page,
        "page_size": page_size,
        "page_count": max(1, -(-total // page_size)),
        "prev_url": _with("page", str(page - 1)) if page > 1 else "",
        "next_url": _with("page", str(page + 1)) if page * page_size < total else "",
        "aggregates": aggregates,
        "active_count": active_count,
        "mosques": mosques,
        "filters": filters,
        "raw_filters": request.GET,
        "csv_url": csv_url,
        "xlsx_url": xlsx_url,
        "full_xlsx_url": f"{xlsx_url}&full=1",
        "export_ready": cache.get(_EXPORT_LOCK_KEY) is None,
        "all_finished": all_finished,
    }
    return TemplateResponse(request, "admin/reporting/participant_ranking.html", context)


def _export_response(request: HttpRequest, filters: dict[str, Any], fmt: str) -> HttpResponse:
    """پاسخِ فایل — با قفلِ هم‌زمانی تا چند ادمین هم‌زمان دیتابیس را نکشند."""
    full = _wants_full_export(request)

    if full and not cache.add(_EXPORT_LOCK_KEY, "busy", timeout=30):
        messages.error(
            request,
            "یک خروجیِ کاملِ دیگر همین حالا در حالِ ساخت است. چند لحظه بعد دوباره تلاش کنید "
            "(این محدودیت عمدی است تا آزمون در جریان، کند نشود).",
        )
        from django.shortcuts import redirect

        return redirect(request.path + ("?" + request.GET.urlencode() if request.GET else ""))

    stamp = hashlib.sha256(repr(sorted(filters.items())).encode("utf-8")).hexdigest()[:12]

    if fmt == "csv":
        response: HttpResponse = StreamingHttpResponse(
            _iter_csv_rows(filters), content_type="text/csv; charset=utf-8"
        )
        response["Content-Disposition"] = f'attachment; filename="kaveh185-ranking-{stamp}.csv"'
        return response

    note = (
        "خروجیِ سبکِ رتبه‌بندی — فقط ستون‌های لازمِ رتبه و امتیاز. "
        "برای ریزِ پاسخ‌ها از «خروجیِ کاملِ تحلیلی» (API) استفاده کنید."
    )
    response = StreamingHttpResponse(
        _xlsx_stream(filters, audit_note=note),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = f'attachment; filename="kaveh185-ranking-{stamp}.xlsx"'

    from apps.audit_logs.choices import AuditAction
    from apps.audit_logs.services import record_audit_log

    try:
        record_audit_log(
            action=AuditAction.REPORT_EXPORTED,
            resource_type="admin_ranking_light",
            resource_id=stamp,
            user=request.user,
            request=request,
            extra_data={"filters": filters, "format": fmt, "full": full},
        )
    except Exception:  # pragma: no cover - لاگِ ممیزی نباید دانلود را بشکند
        logger.warning("audit log for light ranking export failed", exc_info=True)
    return response


def ranking_url() -> str:
    """نشانیِ صفحهٔ رتبه‌بندی — یک منبعِ حقیقت برای لینک‌دادن.

    ⚠️ نامِ مسیر در `config/urls.py` ثبت شده و **نه** در `admin:`
    (دلیلش در `apps/reporting/admin.py` توضیح داده شده: monkeypatch روی
    `admin.site.get_urls` روی هاست ۴۰۴ داد). پس `reverse("participant-ranking")`
    همیشه کار می‌کند، مستقل از `ADMIN_URL_PATH` و ترتیبِ بار‌شدنِ اپ‌ها.
    """
    return reverse("participant-ranking")


__all__ = [
    "MAX_EXPORT_ROWS",
    "participant_ranking_view",
    "ranking_url",
]

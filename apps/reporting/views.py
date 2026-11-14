"""ویوهای نازک HTTP برای داشبورد آماری زنده، کاوشگر چندفیلتره قرعه‌کشی حضوری و خروجی اکسل چندبرگی."""

from __future__ import annotations

from django.http import HttpResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit_logs.choices import AuditAction
from apps.audit_logs.services import record_audit_log
from apps.authentication.permissions import IsAdminRole
from apps.core.pagination import StandardLimitOffsetPagination
from apps.core.responses import success_response

from .excel_exporter import generate_multi_sheet_participants_excel
from .selectors import (
    execute_verifiable_lottery_draw,
    get_admin_participant_detail,
    get_admin_participant_detail_by_tracking_code,
    get_filtered_exam_attempts_queryset,
    get_live_analytics_dashboard,
    serialize_admin_participant_row,
)
from .serializers import (
    AdminAnalyticsDashboardSerializer,
    AdminLotteryDrawInputSerializer,
    AdminLotteryDrawOutputSerializer,
    AdminParticipantExplorerItemSerializer,
)

EXPLORER_FILTER_PARAMETERS = [
    OpenApiParameter(
        name="mosque_ids",
        type=str,
        required=False,
        description="فیلتر یک یا چند مسجد هم‌زمان با کاما (مثلاً `1,3,7`)",
    ),
    OpenApiParameter(
        name="mosque_id",
        type=int,
        required=False,
        description="فیلتر شناسه تک‌مسجد",
    ),
    OpenApiParameter(
        name="exact_correct",
        type=int,
        required=False,
        description="تعداد دقیق پاسخ درست (۰ تا ۵)",
    ),
    OpenApiParameter(
        name="min_correct",
        type=int,
        required=False,
        description="حداقل تعداد پاسخ درست",
    ),
    OpenApiParameter(
        name="max_correct",
        type=int,
        required=False,
        description="حداکثر تعداد پاسخ درست",
    ),
    OpenApiParameter(
        name="min_wrong",
        type=int,
        required=False,
        description="حداقل تعداد پاسخ غلط",
    ),
    OpenApiParameter(
        name="max_wrong",
        type=int,
        required=False,
        description="حداکثر تعداد پاسخ غلط",
    ),
    OpenApiParameter(
        name="min_unanswered",
        type=int,
        required=False,
        description="حداقل تعداد سوالات بی‌پاسخ",
    ),
    OpenApiParameter(
        name="max_unanswered",
        type=int,
        required=False,
        description="حداکثر تعداد سوالات بی‌پاسخ",
    ),
    OpenApiParameter(
        name="min_score",
        type=float,
        required=False,
        description="حداقل امتیاز کل نهایی",
    ),
    OpenApiParameter(
        name="max_score",
        type=float,
        required=False,
        description="حداکثر امتیاز کل نهایی",
    ),
    OpenApiParameter(
        name="min_duration",
        type=int,
        required=False,
        description="حداقل مدت زمان آزمون (ثانیه)",
    ),
    OpenApiParameter(
        name="max_duration",
        type=int,
        required=False,
        description="حداکثر مدت زمان آزمون (ثانیه)",
    ),
    OpenApiParameter(
        name="min_age",
        type=int,
        required=False,
        description="حداقل سن شرکت‌کننده به سال (مثلاً `12`)",
    ),
    OpenApiParameter(
        name="max_age",
        type=int,
        required=False,
        description="حداکثر سن شرکت‌کننده به سال (مثلاً `25`)",
    ),
    OpenApiParameter(
        name="birth_date_from",
        type=str,
        required=False,
        description="تاریخ تولد از (شمسی `1380/01/01` یا میلادی `2001-03-21`)",
    ),
    OpenApiParameter(
        name="birth_date_to",
        type=str,
        required=False,
        description="تاریخ تولد تا (شمسی یا میلادی)",
    ),
    OpenApiParameter(
        name="status",
        type=str,
        required=False,
        description="وضعیت آزمون (`finished`, `completed`, `timed_out`, `in_progress`)",
    ),
    OpenApiParameter(
        name="search",
        type=str,
        required=False,
        description="جستجو روی نام، نام خانوادگی، موبایل، کد ملی یا کد رهگیری",
    ),
    OpenApiParameter(
        name="ordering",
        type=str,
        required=False,
        description=(
            "مرتب‌سازی چندستونه پویا با کاما؛ فیلدهای مجاز: "
            "`-total_score`, `total_score`, `-correct_count`, `correct_count`, "
            "`duration_seconds`, `-duration_seconds`, `age`, `-age`, `birth_date`, `-birth_date`, "
            "`mosque_name`, `-mosque_name`, `-completed_at`"
        ),
    ),
    OpenApiParameter(
        name="include_answers",
        type=bool,
        required=False,
        description="آیا ریز پاسخ ۵ سوال هر نفر هم در فهرست بازگردانده شود؟ (پیش‌فرض: `true`)",
    ),
]


class AdminLiveAnalyticsDashboardAPIView(APIView):
    """داشبورد آماری زنده از وضعیت ثبت‌نام، مشارکت مساجد، رده‌های سنی و دشواری سوالات."""

    permission_classes = [IsAuthenticated, IsAdminRole]

    @extend_schema(
        tags=["Admin - Reporting, Lottery Explorer & Excel"],
        summary="داشبورد آماری زنده (کلی، به تفکیک ۱۷ مسجد، رده سنی و تحلیل سوالات)",
        responses={200: AdminAnalyticsDashboardSerializer},
    )
    def get(self, request: Request) -> Response:
        """بازگرداندن آمار جامع لحظه‌ای سامانه."""
        del request
        payload = get_live_analytics_dashboard()
        return success_response(data=payload)


class AdminParticipantExplorerAPIView(APIView):
    """کاوشگر چندفیلتره و چندمرتب‌ساز شرکت‌کنندگان ویژهٔ مراسم قرعه‌کشی حضوری و بررسی مدیریتی."""

    permission_classes = [IsAuthenticated, IsAdminRole]

    @extend_schema(
        tags=["Admin - Reporting, Lottery Explorer & Excel"],
        summary="کاوشگر پیشرفته شرکت‌کنندگان با فیلتر هم‌زمان مسجد، نمره، زمان و سن (ویژه قرعه‌کشی)",
        parameters=EXPLORER_FILTER_PARAMETERS,
        responses={200: AdminParticipantExplorerItemSerializer(many=True)},
    )
    def get(self, request: Request) -> Response:
        """فیلتر، مرتب‌سازی و صفحه‌بندی کارنامه‌ها همراه با ریز سوالات و پاسخ‌های هر نفر."""
        params = dict(request.query_params.items())
        include_answers = str(params.get("include_answers", "true")).lower() not in {"false", "0"}

        qs = get_filtered_exam_attempts_queryset(params)
        paginator = StandardLimitOffsetPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        offset = paginator.get_offset(request)

        items = [
            serialize_admin_participant_row(
                att,
                rank=offset + idx,
                include_answers=include_answers,
            )
            for idx, att in enumerate(page, start=1)
        ]
        return paginator.get_paginated_response(items)


class AdminParticipantDetailAPIView(APIView):
    """مشاهدهٔ پروندهٔ کامل یک شرکت‌کننده به همراه ریز ۵ سوال و گزینه‌های انتخابی توسط ادمین."""

    permission_classes = [IsAuthenticated, IsAdminRole]

    @extend_schema(
        tags=["Admin - Reporting, Lottery Explorer & Excel"],
        summary="مشاهده مشخصات کامل، خلاصه کارنامه و ریز پاسخ‌های ۵ سوال یک شرکت‌کننده (ادمین)",
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request: Request, user_id: int) -> Response:
        """بازگرداندن پروندهٔ کامل شرکت‌کننده و ریز پاسخنامه."""
        del request
        payload = get_admin_participant_detail(user_id=user_id)
        return success_response(data=payload)


class AdminParticipantByTrackingCodeAPIView(APIView):
    """مشاهدهٔ پرونده و ریز ۵ سوال یک شرکت‌کننده با کد رهگیری قرعه‌کشی (`tracking_code`)."""

    permission_classes = [IsAuthenticated, IsAdminRole]

    @extend_schema(
        tags=["Admin - Reporting, Lottery Explorer & Excel"],
        summary="مشاهده پرونده و ریز ۵ سوال شرکت‌کننده با کد رهگیری قرعه‌کشی (ادمین)",
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request: Request, tracking_code: str) -> Response:
        """بازگرداندن پروندهٔ کامل شرکت‌کننده و ریز ۵ سوال با کد رهگیری."""
        del request
        payload = get_admin_participant_detail_by_tracking_code(tracking_code=tracking_code)
        return success_response(data=payload)


class AdminLotteryDrawAPIView(APIView):
    """موتور اجرای قرعه‌کشی زنده و قابل‌راستی‌آزمایی رمزنگاری‌شده ویژهٔ مراسم حضوری هفته بسیج."""

    permission_classes = [IsAuthenticated, IsAdminRole]

    @extend_schema(
        tags=["Admin - Reporting, Lottery Explorer & Excel"],
        summary="اجرای قرعه‌کشی زنده (CSPRNG + گواهی SHA-256) با اعمال تمام فیلترهای ترکیبی",
        parameters=EXPLORER_FILTER_PARAMETERS,
        request=AdminLotteryDrawInputSerializer,
        responses={200: AdminLotteryDrawOutputSerializer},
    )
    def post(self, request: Request) -> Response:
        """انتخاب تصادفی رمزنگاری‌شدهٔ برندگان اصلی و رزرو از میان جامعهٔ آماری فیلترشده."""
        serializer = AdminLotteryDrawInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        vdata = serializer.validated_data

        merged_params: dict[str, str | int | float] = dict(request.query_params.items())
        for filter_key in (
            "mosque_ids",
            "mosque_id",
            "exact_correct",
            "min_correct",
            "max_correct",
            "min_score",
            "max_score",
            "min_duration",
            "max_duration",
            "min_age",
            "max_age",
        ):
            val = vdata.get(filter_key)
            if val is not None and str(val).strip() != "":
                merged_params[filter_key] = val

        result = execute_verifiable_lottery_draw(
            params=merged_params,
            winners_count=int(vdata.get("winners_count") or 3),
            reserves_count=int(
                vdata.get("reserves_count") if vdata.get("reserves_count") is not None else 2
            ),
            ceremony_title=str(vdata.get("ceremony_title") or ""),
            client_seed=str(vdata.get("client_seed") or ""),
        )

        record_audit_log(
            action=AuditAction.REPORT_EXPORTED,
            resource_type="lottery_draw",
            resource_id=result["cryptographic_proof"]["draw_proof_sha256"][:16],
            user=request.user,
            request=request,
            extra_data={
                "ceremony_title": result["ceremony_title"],
                "eligible_pool_count": result["eligible_pool_count"],
                "winners_tracking_codes": [w["tracking_code"] for w in result["winners"]],
                "reserves_tracking_codes": [r["tracking_code"] for r in result["reserves"]],
                "draw_proof_sha256": result["cryptographic_proof"]["draw_proof_sha256"],
                "applied_filters": merged_params,
            },
        )
        return success_response(
            data=result,
            message="قرعه‌کشی زنده با گواهی اثبات رمزنگاری‌شده با موفقیت انجام شد.",
        )


class AdminExcelExportAPIView(APIView):
    """خروجی اکسل ۷ برگی راست‌به‌چپ (`.xlsx`) با قابلیت اعمال تمام فیلترهای قرعه‌کشی حضوری."""

    permission_classes = [IsAuthenticated, IsAdminRole]

    @extend_schema(
        tags=["Admin - Reporting, Lottery Explorer & Excel"],
        summary="دریافت فایل اکسل ۷ برگی راست‌به‌چپ (RTL .xlsx) برای قرعه‌کشی حضوری و گزارش کامل",
        parameters=EXPLORER_FILTER_PARAMETERS,
        responses={200: OpenApiTypes.BINARY},
    )
    def get(self, request: Request) -> HttpResponse:
        """تولید و دانلود فایل اکسل چندبرگی همراه با ثبت در زنجیرهٔ لاگ ممیزی و هدر SHA-256."""
        params = dict(request.query_params.items())
        attempts = list(get_filtered_exam_attempts_queryset(params)[:10000])
        excel_bytes, sha256_hex = generate_multi_sheet_participants_excel(
            attempts=attempts,
            applied_filters=params,
        )

        record_audit_log(
            action=AuditAction.REPORT_EXPORTED,
            resource_type="excel_report",
            resource_id="participants_7sheet_xlsx",
            user=request.user,
            request=request,
            extra_data={
                "rows_count": len(attempts),
                "filters": params,
                "sha256": sha256_hex,
            },
        )

        resp = HttpResponse(
            excel_bytes,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        resp["Content-Disposition"] = 'attachment; filename="kaveh185-participants-report.xlsx"'
        resp["X-Report-SHA256"] = sha256_hex
        resp["X-Report-Rows"] = str(len(attempts))
        return resp

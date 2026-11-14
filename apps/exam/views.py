"""ویوهای نازک HTTP برای وضعیت آزمون، شروع/ادامه آزمون ۵ سواله، ثبت پاسخ، کارنامه و مدیریت بانک سوال."""

from __future__ import annotations

from typing import Any

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.authentication.permissions import IsAdminRole, IsVerifiedParticipant
from apps.core.exceptions import ConflictDomainError
from apps.core.idempotency import idempotent_endpoint
from apps.core.pagination import StandardLimitOffsetPagination
from apps.core.responses import success_response

from .choices import ExamAttemptStatus
from .selectors import (
    build_active_attempt_payload,
    build_report_card_payload,
    get_admin_question_by_id,
    get_admin_questions_queryset,
    get_attempt_by_tracking_code,
    get_or_create_exam_configuration,
    get_public_exam_status,
    get_public_landing_bootstrap,
)
from .serializers import (
    ActiveAttemptOutputSerializer,
    AdminBulkQuestionInputSerializer,
    AdminExamConfigurationSerializer,
    AdminQuestionSerializer,
    FinishExamInputSerializer,
    PublicExamStatusSerializer,
    ReportCardOutputSerializer,
    SubmitAnswerInputSerializer,
)
from .services import (
    create_question_with_options,
    deactivate_question,
    finish_exam_attempt,
    get_current_active_attempt_or_finalize,
    regrade_all_attempts,
    seed_default_questions,
    start_or_resume_exam,
    submit_question_answer,
    update_exam_configuration,
    update_question_with_options,
)
from .throttles import ExamAnswerRateThrottle, ExamStartRateThrottle


class PublicExamStatusAPIView(APIView):
    """نمایش وضعیت بازهٔ زمانی شرکت در آزمون (`upcoming`, `open`, `ended`) برای تمام کاربران."""

    permission_classes = [AllowAny]
    authentication_classes: list[Any] = []

    @extend_schema(
        tags=["Exam (Public & Participant)"],
        summary="وضعیت بازه زمانی آزمون (به زودی / فعال / پایان مهلت)",
        responses={200: PublicExamStatusSerializer},
    )
    def get(self, request: Request) -> Response:
        """بازگرداندن وضعیت لحظه‌ای پنجرهٔ زمانی آزمون و تنظیمات عمومی مسابقه."""
        del request
        payload = get_public_exam_status()
        return success_response(data=payload)


class PublicLandingBootstrapAPIView(APIView):
    """بستهٔ یکپارچهٔ صفحهٔ اول مسابقه (وضعیت آزمون + فهرست کشویی ۱۷ مسجد + رنکینگ زندهٔ مساجد)."""

    permission_classes = [AllowAny]
    authentication_classes: list[Any] = []

    @extend_schema(
        tags=["Exam (Public & Participant)"],
        summary="دریافت یکپارچهٔ تمام داده‌های صفحه اول و فرم ثبت‌نام در یک درخواست (Single-Request Bootstrap)",
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request: Request) -> Response:
        """بازگرداندن وضعیت آزمون، لیست کشویی مساجد و لیدربورد زنده در یک پاسخ واحد."""
        del request
        payload = get_public_landing_bootstrap()
        return success_response(
            data=payload,
            message="داده‌های یکپارچهٔ صفحهٔ اول مسابقه کاوه ۱۸۵ با موفقیت دریافت شد.",
        )


class ExamStartAPIView(APIView):
    """شروع آزمون ۵ سواله جدید (با تصادفی‌سازی سوالات و گزینه‌ها) یا ادامهٔ آزمون در حال اجرا."""

    permission_classes = [IsAuthenticated, IsVerifiedParticipant]
    throttle_classes = [ExamStartRateThrottle]

    @extend_schema(
        tags=["Exam (Public & Participant)"],
        summary="ورود به آزمون ۵ سواله (شروع تایمر یا ادامه آزمون باز)",
        request=None,
        responses={200: ActiveAttemptOutputSerializer, 201: ActiveAttemptOutputSerializer},
    )
    @idempotent_endpoint
    def post(self, request: Request) -> Response:
        """ایجاد جلسهٔ آزمون ۵ سواله با تصادفی‌سازی دوگانه یا بازگرداندن جلسهٔ فعال."""
        attempt, created = start_or_resume_exam(user=request.user, request=request)
        payload = build_active_attempt_payload(attempt)
        msg = (
            "آزمون شما آغاز شد. به ۵ سوال چهارگزینه‌ای به ترتیب پاسخ دهید."
            if created
            else "جلسهٔ فعال آزمون شما بازیابی شد."
        )
        return success_response(
            data=payload,
            message=msg,
            status_code=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class ExamCurrentAttemptAPIView(APIView):
    """دریافت وضعیت فعلی جلسهٔ آزمون در حال اجرای کاربر همراه با تایمر سرور."""

    permission_classes = [IsAuthenticated, IsVerifiedParticipant]

    @extend_schema(
        tags=["Exam (Public & Participant)"],
        summary="دریافت سوالات و زمان باقی‌مانده آزمون جاری کاربر",
        responses={200: ActiveAttemptOutputSerializer},
    )
    def get(self, request: Request) -> Response:
        """بازگرداندن سوالات و پاسخ‌های ذخیره‌شده؛ یا صدور خودکار کارنامه در صورت اتمام تایمر."""
        attempt = get_current_active_attempt_or_finalize(user=request.user, request=request)
        if attempt.status in {ExamAttemptStatus.COMPLETED, ExamAttemptStatus.TIMED_OUT}:
            return success_response(
                data={
                    "status": attempt.status,
                    "is_finished": True,
                    "report_card": build_report_card_payload(attempt),
                },
                message="زمان آزمون به پایان رسیده و کارنامه صادر شده است.",
            )
        return success_response(
            data={
                "status": attempt.status,
                "is_finished": False,
                "attempt": build_active_attempt_payload(attempt),
            }
        )


class ExamSubmitAnswerAPIView(APIView):
    """ثبت پاسخ یک سوال در حین آزمون (ذخیرهٔ خودکار بدون امکان رد کردن سوال قبلی و بدون افشای کلید)."""

    permission_classes = [IsAuthenticated, IsVerifiedParticipant]
    throttle_classes = [ExamAnswerRateThrottle]

    @extend_schema(
        tags=["Exam (Public & Participant)"],
        summary="ثبت پاسخ سوال (Auto-Save بدون افشای درست یا غلط بودن)",
        request=SubmitAnswerInputSerializer,
        responses={200: ActiveAttemptOutputSerializer},
    )
    def post(self, request: Request) -> Response:
        """ثبت گزینهٔ انتخابی کاربر برای سوال شماره‌گذاری‌شده."""
        serializer = SubmitAnswerInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        attempt = submit_question_answer(
            user=request.user,
            question_number=int(serializer.validated_data["question_number"]),
            selected_position=int(serializer.validated_data["selected_position"]),
            request=request,
        )
        return success_response(
            data=build_active_attempt_payload(attempt),
            message="پاسخ سوال با موفقیت ذخیره شد.",
        )


class ExamFinishAPIView(APIView):
    """پایان آزمون و دریافت کارنامهٔ نهایی (بدون افشای اینکه کدام سوال درست یا غلط بوده است)."""

    permission_classes = [IsAuthenticated, IsVerifiedParticipant]

    @extend_schema(
        tags=["Exam (Public & Participant)"],
        summary="پایان آزمون و صدور کارنامه نهایی + ارسال پیامک تشکر",
        request=FinishExamInputSerializer,
        responses={200: ReportCardOutputSerializer},
    )
    @idempotent_endpoint
    def post(self, request: Request) -> Response:
        """نهایی‌سازی آزمون، محاسبهٔ امتیاز، به‌روزرسانی رتبهٔ مسجد و ارسال پیامک تشکر."""
        serializer = FinishExamInputSerializer(data=request.data or {})
        serializer.is_valid(raise_exception=True)
        attempt = finish_exam_attempt(
            user=request.user,
            answers=serializer.validated_data.get("answers"),
            request=request,
        )
        return success_response(
            data=build_report_card_payload(attempt),
            message="آزمون شما با موفقیت ثبت نهایی شد و کارنامه صادر گردید.",
        )


class ExamReportCardAPIView(APIView):
    """مشاهدهٔ کارنامهٔ نهایی شرکت‌کننده (فقط آمار کلی بدون افشای کلید سوالات)."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Exam (Public & Participant)"],
        summary="دریافت کارنامه نهایی شرکت‌کننده جاری",
        responses={200: ReportCardOutputSerializer},
    )
    def get(self, request: Request) -> Response:
        """بازگرداندن کارنامهٔ کاربر؛ اگر تایمر آزمون باز تمام شده باشد ابتدا خودکار نهایی می‌شود."""
        attempt = get_current_active_attempt_or_finalize(user=request.user, request=request)
        if attempt.status == ExamAttemptStatus.IN_PROGRESS:
            raise ConflictDomainError(
                "آزمون شما هنوز در حال اجراست و به پایان نرسیده است.",
                code="exam_still_in_progress",
                errors={"remaining_seconds": attempt.remaining_seconds()},
            )
        return success_response(data=build_report_card_payload(attempt))


class PublicReceiptVerifyAPIView(APIView):
    """استعلام عمومی اصالت رسید دیجیتال کارنامه با کد رهگیری (`KV185-XXXXXXXX`)."""

    permission_classes = [AllowAny]
    authentication_classes: list[Any] = []

    @extend_schema(
        tags=["Exam (Public & Participant)"],
        summary="استعلام عمومی اصالت رسید کارنامه با کد رهگیری",
        responses={200: ReportCardOutputSerializer},
    )
    def get(self, request: Request, tracking_code: str) -> Response:
        """بررسی اصالت کد رهگیری و بازگرداندن اطلاعات خلاصهٔ رسید شرکت در مسابقه."""
        del request
        attempt = get_attempt_by_tracking_code(tracking_code)
        return success_response(data=build_report_card_payload(attempt))


class AdminExamConfigurationAPIView(APIView):
    """مشاهده و ویرایش زندهٔ تنظیمات آزمون (بازه زمانی، تایمر، OTP، امتیازدهی و پیامک) توسط ادمین."""

    permission_classes = [IsAuthenticated, IsAdminRole]

    @extend_schema(
        tags=["Admin - Exam & Question Bank"],
        summary="دریافت تنظیمات کامل آزمون توسط ادمین",
        responses={200: AdminExamConfigurationSerializer},
    )
    def get(self, request: Request) -> Response:
        """بازگرداندن تنظیمات فعلی آزمون."""
        del request
        config = get_or_create_exam_configuration()
        return success_response(data=AdminExamConfigurationSerializer(config).data)

    @extend_schema(
        tags=["Admin - Exam & Question Bank"],
        summary="به‌روزرسانی زنده تنظیمات آزمون توسط ادمین",
        request=AdminExamConfigurationSerializer,
        responses={200: AdminExamConfigurationSerializer},
    )
    def patch(self, request: Request) -> Response:
        """ویرایش تنظیمات آزمون و باطل‌سازی فوری کش وضعیت عمومی آزمون."""
        config = get_or_create_exam_configuration()
        serializer = AdminExamConfigurationSerializer(config, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        updated = update_exam_configuration(
            data=serializer.validated_data,
            request=request,
        )
        return success_response(
            data=AdminExamConfigurationSerializer(updated).data,
            message="تنظیمات آزمون با موفقیت به‌روزرسانی شد.",
        )


class AdminQuestionListCreateAPIView(APIView):
    """فهرست و افزودن سوالات چهارگزینه‌ای در بانک سوال توسط ادمین."""

    permission_classes = [IsAuthenticated, IsAdminRole]

    @extend_schema(
        tags=["Admin - Exam & Question Bank"],
        summary="فهرست بانک سوالات چهارگزینه‌ای همراه با آمار پاسخگویی (ادمین)",
        parameters=[
            OpenApiParameter(name="search", type=str, required=False),
            OpenApiParameter(name="difficulty", type=str, required=False),
            OpenApiParameter(name="is_active", type=str, required=False),
        ],
        responses={200: AdminQuestionSerializer(many=True)},
    )
    def get(self, request: Request) -> Response:
        """بازگرداندن فهرست صفحه‌بندی‌شدهٔ سوالات بانک سوال."""
        qs = get_admin_questions_queryset(
            search=str(request.query_params.get("search", "")),
            difficulty=str(request.query_params.get("difficulty", "")),
            is_active=str(request.query_params.get("is_active", "")),
        )
        paginator = StandardLimitOffsetPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        serializer = AdminQuestionSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    @extend_schema(
        tags=["Admin - Exam & Question Bank"],
        summary="افزودن سوال چهارگزینه‌ای جدید به بانک سوال (ادمین)",
        request=AdminQuestionSerializer,
        responses={201: AdminQuestionSerializer},
    )
    def post(self, request: Request) -> Response:
        """ایجاد یک سوال چهارگزینه‌ای جدید با ۴ گزینه و ۱ کلید صحیح."""
        question = create_question_with_options(
            data=dict(request.data),
            created_by=request.user,
            request=request,
        )
        loaded = get_admin_question_by_id(question.id)
        return success_response(
            data=AdminQuestionSerializer(loaded).data,
            message="سوال چهارگزینه‌ای جدید با موفقیت به بانک سوال اضافه شد.",
            status_code=status.HTTP_201_CREATED,
        )


class AdminQuestionDetailAPIView(APIView):
    """مشاهده، ویرایش (با بازتصحیح خودکار کارنامه‌ها در صورت تغییر کلید) و حذف نرم سوال."""

    permission_classes = [IsAuthenticated, IsAdminRole]

    @extend_schema(
        tags=["Admin - Exam & Question Bank"],
        summary="جزئیات یک سوال چهارگزینه‌ای در بانک سوال (ادمین)",
        responses={200: AdminQuestionSerializer},
    )
    def get(self, request: Request, question_id: int) -> Response:
        """بازگرداندن جزئیات سوال و ۴ گزینهٔ آن."""
        del request
        question = get_admin_question_by_id(question_id)
        return success_response(data=AdminQuestionSerializer(question).data)

    @extend_schema(
        tags=["Admin - Exam & Question Bank"],
        summary="ویرایش سوال یا کلید صحیح (همراه با بازتصحیح خودکار کارنامه‌ها)",
        request=AdminQuestionSerializer,
        responses={200: AdminQuestionSerializer},
    )
    def patch(self, request: Request, question_id: int) -> Response:
        """ویرایش سوال؛ اگر گزینهٔ صحیح تغییر کند تمام کارنامه‌ها به‌صورت خودکار بازتصحیح می‌شوند."""
        question = get_admin_question_by_id(question_id)
        updated = update_question_with_options(
            question=question,
            data=dict(request.data),
            request=request,
            auto_regrade=True,
        )
        loaded = get_admin_question_by_id(updated.id)
        return success_response(
            data=AdminQuestionSerializer(loaded).data,
            message="سوال با موفقیت ویرایش شد و کارنامه‌ها به‌روزرسانی شدند.",
        )

    @extend_schema(
        tags=["Admin - Exam & Question Bank"],
        summary="غیرفعال‌سازی نرم سوال در بانک سوال (ادمین)",
        responses={200: OpenApiTypes.OBJECT},
    )
    def delete(self, request: Request, question_id: int) -> Response:
        """حذف نرم (غیرفعال‌سازی) یک سوال از چرخهٔ انتخاب سوالات جدید."""
        question = get_admin_question_by_id(question_id)
        deactivate_question(question=question, request=request)
        return success_response(
            data={"id": question.id, "is_active": False},
            message="سوال با موفقیت غیرفعال شد.",
        )


class AdminQuestionBulkImportAPIView(APIView):
    """ورود دسته‌ای (Bulk Import) سوالات چهارگزینه‌ای توسط ادمین."""

    permission_classes = [IsAuthenticated, IsAdminRole]

    @extend_schema(
        tags=["Admin - Exam & Question Bank"],
        summary="درج دسته‌ای سوالات چهارگزینه‌ای در بانک سوال (ادمین)",
        request=AdminBulkQuestionInputSerializer,
        responses={201: OpenApiTypes.OBJECT},
    )
    def post(self, request: Request) -> Response:
        """ایجاد چندین سوال چهارگزینه‌ای در یک درخواست."""
        raw_questions = list(request.data.get("questions") or [])
        created_ids: list[int] = []
        for q_payload in raw_questions:
            q = create_question_with_options(
                data=dict(q_payload),
                created_by=request.user,
                request=request,
            )
            created_ids.append(q.id)
        return success_response(
            data={"created_count": len(created_ids), "question_ids": created_ids},
            message=f"{len(created_ids)} سوال چهارگزینه‌ای با موفقیت ثبت شد.",
            status_code=status.HTTP_201_CREATED,
        )


class AdminQuestionSeedDefaultsAPIView(APIView):
    """بارگذاری بانک سوالات نمونهٔ هفته بسیج و سیره شهید کاوه توسط ادمین."""

    permission_classes = [IsAuthenticated, IsAdminRole]

    @extend_schema(
        tags=["Admin - Exam & Question Bank"],
        summary="بارگذاری بانک سوالات پیش‌فرض هفته بسیج و شهید کاوه",
        request=None,
        responses={200: OpenApiTypes.OBJECT},
    )
    def post(self, request: Request) -> Response:
        """ایجاد سوالات نمونهٔ پیش‌فرض برای آماده‌سازی سریع بانک سوال."""
        result = seed_default_questions(request=request)
        return success_response(
            data=result,
            message="بانک سوالات نمونهٔ هفته بسیج با موفقیت بارگذاری شد.",
        )


class AdminRegradeAllAttemptsAPIView(APIView):
    """بازتصحیح دستی تمامی کارنامه‌های ثبت‌شده بر اساس آخرین کلید بانک سوال و فرمول امتیازدهی."""

    permission_classes = [IsAuthenticated, IsAdminRole]

    @extend_schema(
        tags=["Admin - Exam & Question Bank"],
        summary="بازتصحیح خودکار تمامی کارنامه‌ها بر اساس آخرین کلید سوالات (ادمین)",
        request=None,
        responses={200: OpenApiTypes.OBJECT},
    )
    def post(self, request: Request) -> Response:
        """بازمحاسبهٔ تعداد درست/غلط و امتیاز ترکیبی تمام شرکت‌کنندگان."""
        result = regrade_all_attempts(request=request)
        return success_response(
            data=result,
            message="تمامی کارنامه‌ها با موفقیت بازتصحیح شدند.",
        )

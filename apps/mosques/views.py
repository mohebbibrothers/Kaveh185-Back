"""ویوهای عمومی و مدیریتی مساجد حوزه مقاومت بسیج ۱۸۵ شهید کاوه."""

from __future__ import annotations

from typing import Any

from drf_spectacular.utils import extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.authentication.permissions import IsAdminUser
from apps.core.responses import created_response, deleted_response, success_response

from .selectors import (
    get_active_mosques_dropdown,
    get_admin_mosque_by_id,
    get_admin_mosques_queryset,
    get_mosque_leaderboard_snapshot,
)
from .serializers import (
    AdminMosqueSerializer,
    MosqueDropdownSerializer,
    MosqueLeaderboardSnapshotSerializer,
)
from .services import create_mosque, deactivate_mosque, seed_default_mosques, update_mosque


class PublicMosqueListAPIView(APIView):
    """فهرست کشویی مساجد فعال برای انتخاب در فرم ثبت‌نام شرکت‌کنندگان."""

    permission_classes = [AllowAny]
    authentication_classes: list[Any] = []

    @extend_schema(
        tags=["Mosques & Leaderboard"],
        summary="لیست کشویی مساجد فعال حوزه ۱۸۵ شهید کاوه (فرم ثبت‌نام)",
        responses={200: MosqueDropdownSerializer(many=True)},
    )
    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """واکشی فهرست مساجد فعال از کش SWR."""
        del request, args, kwargs
        items = get_active_mosques_dropdown()
        return success_response(
            data=items,
            message="فهرست مساجد فعال حوزه ۱۸۵ شهید کاوه با موفقیت دریافت شد.",
        )


class PublicMosqueLeaderboardAPIView(APIView):
    """رنکینگ لحظه‌ای مساجد بر اساس تعداد شرکت‌کنندگان در آزمون هفته بسیج."""

    permission_classes = [AllowAny]
    authentication_classes: list[Any] = []

    @extend_schema(
        tags=["Mosques & Leaderboard"],
        summary="رنکینگ و جدول رقابت لحظه‌ای مشارکت مساجد",
        responses={200: MosqueLeaderboardSnapshotSerializer},
    )
    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """محاسبه و نمایش رتبهٔ هر مسجد بر اساس تعداد مشارکت‌کنندگان."""
        del request, args, kwargs
        snapshot = get_mosque_leaderboard_snapshot()
        return success_response(
            data=snapshot,
            message="جدول رنکینگ لحظه‌ای مشارکت مساجد با موفقیت دریافت شد.",
        )


class AdminMosqueListCreateAPIView(APIView):
    """فهرست کامل و ایجاد مسجد جدید توسط ادمین."""

    permission_classes = [IsAdminUser]

    @extend_schema(
        tags=["Admin - Mosques"],
        summary="فهرست تمام مساجد (مخصوص ادمین)",
        responses={200: AdminMosqueSerializer(many=True)},
    )
    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """مشاهدهٔ تمام مساجد (فعال و غیرفعال) با امکان جست‌وجو."""
        del args, kwargs
        search = str(request.query_params.get("q") or request.query_params.get("search") or "")
        is_active = str(request.query_params.get("is_active") or "")
        qs = get_admin_mosques_queryset(search=search, is_active=is_active)
        return success_response(
            data=AdminMosqueSerializer(qs, many=True).data,
            message="فهرست مدیریتی مساجد دریافت شد.",
        )

    @extend_schema(
        tags=["Admin - Mosques"],
        summary="ایجاد مسجد جدید توسط ادمین",
        request=AdminMosqueSerializer,
        responses={201: AdminMosqueSerializer},
    )
    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """ثبت مسجد جدید در سامانه."""
        del args, kwargs
        serializer = AdminMosqueSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        mosque = create_mosque(data=serializer.validated_data, request=request)
        return created_response(
            data=AdminMosqueSerializer(mosque).data,
            message="مسجد جدید با موفقیت ایجاد شد.",
        )


class AdminMosqueDetailAPIView(APIView):
    """مشاهده، ویرایش و غیرفعال‌سازی یک مسجد توسط ادمین."""

    permission_classes = [IsAdminUser]

    @extend_schema(
        tags=["Admin - Mosques"],
        summary="مشاهدهٔ جزئیات یک مسجد (مخصوص ادمین)",
        responses={200: AdminMosqueSerializer},
    )
    def get(self, request: Request, mosque_id: int, *args: Any, **kwargs: Any) -> Response:
        """واکشی مسجد با شناسه."""
        del request, args, kwargs
        mosque = get_admin_mosque_by_id(mosque_id)
        return success_response(
            data=AdminMosqueSerializer(mosque).data,
            message="جزئیات مسجد دریافت شد.",
        )

    @extend_schema(
        tags=["Admin - Mosques"],
        summary="ویرایش اطلاعات مسجد توسط ادمین",
        request=AdminMosqueSerializer,
        responses={200: AdminMosqueSerializer},
    )
    def patch(self, request: Request, mosque_id: int, *args: Any, **kwargs: Any) -> Response:
        """به‌روزرسانی فیلدهای مسجد."""
        del args, kwargs
        mosque = get_admin_mosque_by_id(mosque_id)
        serializer = AdminMosqueSerializer(mosque, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        updated = update_mosque(mosque=mosque, data=serializer.validated_data, request=request)
        return success_response(
            data=AdminMosqueSerializer(updated).data,
            message="اطلاعات مسجد با موفقیت به‌روزرسانی شد.",
        )

    @extend_schema(
        tags=["Admin - Mosques"],
        summary="غیرفعال‌سازی (حذف نرم) مسجد توسط ادمین",
        responses={200: {"type": "object"}},
    )
    def delete(self, request: Request, mosque_id: int, *args: Any, **kwargs: Any) -> Response:
        """غیرفعال‌سازی نرم یک مسجد."""
        del args, kwargs
        mosque = get_admin_mosque_by_id(mosque_id)
        deactivate_mosque(mosque=mosque, request=request)
        return deleted_response(message="مسجد با موفقیت غیرفعال شد.")


class AdminMosqueSeedDefaultsAPIView(APIView):
    """بارگذاری خودکار ۱۷ مسجد پیش‌فرض حوزه مقاومت بسیج ۱۸۵ شهید کاوه."""

    permission_classes = [IsAdminUser]

    @extend_schema(
        tags=["Admin - Mosques"],
        summary="بارگذاری ۱۷ مسجد پیش‌فرض حوزه ۱۸۵ شهید کاوه",
        request=None,
        responses={200: {"type": "object"}},
    )
    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """فراخوانی سرویس ایجاد ۱۷ مسجد پیش‌فرض."""
        del args, kwargs
        result = seed_default_mosques(request=request)
        return success_response(
            data=result,
            message="بارگذاری ۱۷ مسجد پیش‌فرض حوزه ۱۸۵ شهید کاوه با موفقیت انجام شد.",
        )

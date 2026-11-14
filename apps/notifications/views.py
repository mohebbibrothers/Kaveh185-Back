"""ویوهای نازک HTTP برای مشاهدهٔ لاگ پیامک‌ها، پردازش صف Outbox و ارسال پیامک تستی توسط ادمین."""

from __future__ import annotations

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.authentication.permissions import IsAdminRole
from apps.core.outbox import relay_pending_outbox
from apps.core.pagination import StandardLimitOffsetPagination
from apps.core.responses import success_response

from .choices import SMSCategory
from .selectors import get_sms_delivery_logs_queryset
from .serializers import AdminSendTestSMSInputSerializer, SMSDeliveryLogSerializer
from .services import send_sms_message


class AdminSMSDeliveryLogListAPIView(APIView):
    """مشاهدهٔ فهرست لاگ پیامک‌های ارسالی (OTP و پیامک تشکر) توسط ادمین."""

    permission_classes = [IsAuthenticated, IsAdminRole]

    @extend_schema(
        tags=["Admin - Notifications & SMS"],
        summary="فهرست لاگ پیامک‌های ارسالی (OTP و تشکر پایان آزمون)",
        parameters=[
            OpenApiParameter(name="category", type=str, required=False),
            OpenApiParameter(name="status", type=str, required=False),
            OpenApiParameter(name="search", type=str, required=False),
        ],
        responses={200: SMSDeliveryLogSerializer(many=True)},
    )
    def get(self, request: Request) -> Response:
        """بازگرداندن فهرست صفحه‌بندی‌شدهٔ لاگ پیامک‌ها."""
        qs = get_sms_delivery_logs_queryset(
            category=str(request.query_params.get("category", "")),
            status=str(request.query_params.get("status", "")),
            search=str(request.query_params.get("search", "")),
        )
        paginator = StandardLimitOffsetPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        serializer = SMSDeliveryLogSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


class AdminSendTestSMSAPIView(APIView):
    """ارسال پیامک تستی یا اطلاع‌رسانی توسط ادمین."""

    permission_classes = [IsAuthenticated, IsAdminRole]

    @extend_schema(
        tags=["Admin - Notifications & SMS"],
        summary="ارسال پیامک تستی یا اطلاع‌رسانی توسط ادمین",
        request=AdminSendTestSMSInputSerializer,
        responses={201: SMSDeliveryLogSerializer},
    )
    def post(self, request: Request) -> Response:
        """ارسال پیامک به شماره موبایل مشخص‌شده."""
        serializer = AdminSendTestSMSInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        log = send_sms_message(
            recipient_phone=serializer.validated_data["recipient_phone"],
            message_text=serializer.validated_data["message_text"],
            category=SMSCategory.ANNOUNCEMENT,
        )
        return success_response(
            data=SMSDeliveryLogSerializer(log).data,
            message="پیامک با موفقیت پردازش شد.",
            status_code=status.HTTP_201_CREATED,
        )


class AdminFlushOutboxAPIView(APIView):
    """پردازش دستی صف پیام‌های Outbox در انتظار ارسال توسط ادمین."""

    permission_classes = [IsAuthenticated, IsAdminRole]

    @extend_schema(
        tags=["Admin - Notifications & SMS"],
        summary="پردازش و ارسال پیام‌های در انتظار در صف Outbox",
        request=None,
        responses={200: OpenApiTypes.OBJECT},
    )
    def post(self, request: Request) -> Response:
        """پردازش پیام‌های در صف Outbox."""
        del request
        stats = relay_pending_outbox(limit=100)
        return success_response(
            data=stats,
            message="صف پیام‌های Outbox پردازش شد.",
        )

"""ویوی نازک HTTP برای مرکز فرماندهی یکپارچه ادمین."""

from __future__ import annotations

from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.authentication.permissions import IsAdminRole
from apps.core.responses import success_response

from .selectors import get_command_center_snapshot
from .serializers import CommandCenterSnapshotSerializer


class AdminCommandCenterSnapshotAPIView(APIView):
    """نمای یکپارچه ۳۶۰ درجه از وضعیت سامانه برای داشبورد اصلی مدیریت."""

    permission_classes = [IsAuthenticated, IsAdminRole]

    @extend_schema(
        tags=["Admin - Command Center"],
        summary="نمای یکپارچه مرکز فرماندهی ادمین در یک درخواست",
        responses={200: CommandCenterSnapshotSerializer},
    )
    def get(self, request: Request) -> Response:
        """بازگرداندن خلاصهٔ کامل عملیاتی، آماری و امنیتی سامانه."""
        del request
        payload = get_command_center_snapshot()
        return success_response(data=payload)

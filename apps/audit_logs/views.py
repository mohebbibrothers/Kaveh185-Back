"""ویوهای مدیریتی مشاهده، بررسی یکپارچگی و خروجی فارنزیک لاگ‌های حسابرسی."""

from __future__ import annotations

from typing import Any

from drf_spectacular.utils import extend_schema
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.authentication.permissions import IsAdminUser
from apps.core.pagination import StandardResultsSetPagination
from apps.core.responses import success_response

from .chain import verify_audit_chain
from .choices import AuditAction
from .exporters import build_forensic_audit_package
from .selectors import get_audit_log_by_id, get_audit_logs_queryset
from .serializers import AuditChainVerificationSerializer, AuditLogSerializer
from .services import record_audit_log


class AdminAuditLogListAPIView(APIView):
    """فهرست صفحه‌بندی‌شده و قابل فیلتر لاگ‌های حسابرسی مخصوص ادمین."""

    permission_classes = [IsAdminUser]

    @extend_schema(
        tags=["Admin - Audit & Forensics"],
        summary="فهرست لاگ‌های حسابرسی (مخصوص ادمین)",
        responses={200: AuditLogSerializer(many=True)},
    )
    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """واکشی و صفحه‌بندی لاگ‌های حسابرسی."""
        del args, kwargs
        qs = get_audit_logs_queryset(params=request.query_params.dict())
        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        serializer = AuditLogSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


class AdminAuditLogDetailAPIView(APIView):
    """جزئیات کامل یک رکورد حسابرسی."""

    permission_classes = [IsAdminUser]

    @extend_schema(
        tags=["Admin - Audit & Forensics"],
        summary="دریافت جزئیات یک لاگ حسابرسی",
        responses={200: AuditLogSerializer},
    )
    def get(self, request: Request, audit_log_id: int, *args: Any, **kwargs: Any) -> Response:
        """واکشی رکورد حسابرسی با شناسه."""
        del request, args, kwargs
        row = get_audit_log_by_id(audit_log_id)
        return success_response(
            data=AuditLogSerializer(row).data,
            message="جزئیات رکورد حسابرسی دریافت شد.",
        )


class AdminAuditChainVerifyAPIView(APIView):
    """راستی‌آزمایی زنجیرهٔ هش ضددستکاری لاگ‌های حسابرسی."""

    permission_classes = [IsAdminUser]

    @extend_schema(
        tags=["Admin - Audit & Forensics"],
        summary="بررسی سلامت و عدم دستکاری زنجیرهٔ هش حسابرسی",
        responses={200: AuditChainVerificationSerializer},
    )
    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """اجرای بررسی پیوستگی زنجیرهٔ هش."""
        del request, args, kwargs
        result = verify_audit_chain()
        return success_response(
            data=result,
            message="یکپارچگی زنجیرهٔ حسابرسی بررسی شد.",
        )


class AdminAuditExportAPIView(APIView):
    """خروجی بستهٔ فارنزیک امضاشده با SHA-256 از لاگ‌های حسابرسی."""

    permission_classes = [IsAdminUser]

    @extend_schema(
        tags=["Admin - Audit & Forensics"],
        summary="خروجی بستهٔ فارنزیک لاگ‌های حسابرسی",
        responses={200: {"type": "object"}},
    )
    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """تولید بستهٔ فارنزیک و ثبت رخداد خروجی در زنجیرهٔ حسابرسی."""
        del args, kwargs
        record_audit_log(
            action=AuditAction.AUDIT_EXPORTED,
            resource_type="audit_log",
            resource_id="package",
            request=request,
            reason="درخواست خروجی فارنزیک توسط ادمین",
        )
        package = build_forensic_audit_package()
        return success_response(
            data=package,
            message="بستهٔ فارنزیک لاگ‌های حسابرسی با موفقیت تولید شد.",
            headers={
                "X-Audit-Package-SHA256": package["package_sha256"],
                "X-Export-SHA256": package["package_sha256"],
            },
        )

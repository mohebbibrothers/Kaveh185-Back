"""مسیرهای API مربوط به لاگ‌های حسابرسی و بررسی فارنزیک."""

from __future__ import annotations

from django.urls import path

from .views import (
    AdminAuditChainVerifyAPIView,
    AdminAuditExportAPIView,
    AdminAuditLogDetailAPIView,
    AdminAuditLogListAPIView,
)

app_name = "audit_logs"

urlpatterns = [
    path("admin/logs/", AdminAuditLogListAPIView.as_view(), name="admin-audit-logs"),
    path("admin/logs/export/", AdminAuditExportAPIView.as_view(), name="admin-audit-export"),
    path("admin/logs/verify/", AdminAuditChainVerifyAPIView.as_view(), name="admin-audit-verify"),
    path(
        "admin/logs/<int:audit_log_id>/",
        AdminAuditLogDetailAPIView.as_view(),
        name="admin-audit-detail",
    ),
]

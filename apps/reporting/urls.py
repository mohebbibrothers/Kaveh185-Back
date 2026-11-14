"""مسیرهای API گزارش‌گیری، کاوشگر چندفیلتره قرعه‌کشی حضوری و خروجی اکسل چندبرگی."""

from __future__ import annotations

from django.urls import path

from .views import (
    AdminExcelExportAPIView,
    AdminLiveAnalyticsDashboardAPIView,
    AdminParticipantDetailAPIView,
    AdminParticipantExplorerAPIView,
)

app_name = "reporting"

urlpatterns = [
    path("admin/dashboard/", AdminLiveAnalyticsDashboardAPIView.as_view(), name="admin-dashboard"),
    path(
        "admin/participants/", AdminParticipantExplorerAPIView.as_view(), name="admin-participants"
    ),
    path(
        "admin/participants/<int:user_id>/",
        AdminParticipantDetailAPIView.as_view(),
        name="admin-participant-detail",
    ),
    path("admin/export.xlsx", AdminExcelExportAPIView.as_view(), name="admin-export-xlsx"),
]

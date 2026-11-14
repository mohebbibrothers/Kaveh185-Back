"""مسیرهای API گزارش‌گیری، کاوشگر چندفیلتره قرعه‌کشی حضوری، قرعه‌کشی زنده و خروجی اکسل چندبرگی."""

from __future__ import annotations

from django.urls import path

from .views import (
    AdminExcelExportAPIView,
    AdminLiveAnalyticsDashboardAPIView,
    AdminLotteryDrawAPIView,
    AdminParticipantByTrackingCodeAPIView,
    AdminParticipantDetailAPIView,
    AdminParticipantExplorerAPIView,
)

app_name = "reporting"

urlpatterns = [
    path("admin/dashboard/", AdminLiveAnalyticsDashboardAPIView.as_view(), name="admin-dashboard"),
    path("dashboard/", AdminLiveAnalyticsDashboardAPIView.as_view(), name="dashboard-alias"),
    path(
        "admin/participants/", AdminParticipantExplorerAPIView.as_view(), name="admin-participants"
    ),
    path("lottery/", AdminParticipantExplorerAPIView.as_view(), name="lottery-explorer-alias"),
    path("admin/lottery/draw/", AdminLotteryDrawAPIView.as_view(), name="admin-lottery-draw"),
    path("lottery/draw/", AdminLotteryDrawAPIView.as_view(), name="lottery-draw-alias"),
    path(
        "admin/participants/<int:user_id>/",
        AdminParticipantDetailAPIView.as_view(),
        name="admin-participant-detail",
    ),
    path(
        "admin/participants/by-tracking/<str:tracking_code>/",
        AdminParticipantByTrackingCodeAPIView.as_view(),
        name="admin-participant-by-tracking",
    ),
    path("admin/export.xlsx", AdminExcelExportAPIView.as_view(), name="admin-export-xlsx"),
    path("export.xlsx", AdminExcelExportAPIView.as_view(), name="export-xlsx-alias"),
]

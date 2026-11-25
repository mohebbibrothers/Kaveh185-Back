"""مسیرهای API گزارش‌گیری، کاوشگر چندفیلتره قرعه‌کشی حضوری، قرعه‌کشی زنده و خروجی اکسل چندبرگی."""

from __future__ import annotations

from django.contrib import admin as django_admin
from django.urls import path

from .ranking_admin import participant_ranking_view
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
    # ── میان‌برِ اضطراریِ صفحهٔ رتبه‌بندی ────────────────────────────────
    # مسیرِ رسمی `/secure-kaveh185-admin/participant-ranking/` است (در
    # `config/urls.py`). این یکی همان صفحه را زیرِ API هم سرو می‌کند، برای
    # وقتی `ADMIN_URL_PATH` روی میزبان عوض شده باشد یا کاربر آدرس را گم کند.
    # همان قفلِ `admin_view` روی آن است، پس فقط staff می‌بیند.
    path(
        "admin/ranking/",
        django_admin.site.admin_view(participant_ranking_view),
        name="admin-ranking-page",
    ),
    path("admin/export.xlsx", AdminExcelExportAPIView.as_view(), name="admin-export-xlsx"),
    path("export.xlsx", AdminExcelExportAPIView.as_view(), name="export-xlsx-alias"),
]

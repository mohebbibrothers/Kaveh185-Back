"""مسیر API مرکز فرماندهی یکپارچه ادمین."""

from __future__ import annotations

from django.urls import path

from .views import AdminCommandCenterSnapshotAPIView

app_name = "command_center"

urlpatterns = [
    path("", AdminCommandCenterSnapshotAPIView.as_view(), name="snapshot"),
    path("overview/", AdminCommandCenterSnapshotAPIView.as_view(), name="overview"),
]

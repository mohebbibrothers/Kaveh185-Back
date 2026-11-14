"""مسیرهای API مساجد و جدول رنکینگ مشارکت."""

from __future__ import annotations

from django.urls import path

from .views import (
    AdminMosqueDetailAPIView,
    AdminMosqueListCreateAPIView,
    AdminMosqueSeedDefaultsAPIView,
    PublicMosqueLeaderboardAPIView,
    PublicMosqueListAPIView,
)

app_name = "mosques"

urlpatterns = [
    path("", PublicMosqueListAPIView.as_view(), name="public-mosques"),
    path("leaderboard/", PublicMosqueLeaderboardAPIView.as_view(), name="public-leaderboard"),
    path("admin/", AdminMosqueListCreateAPIView.as_view(), name="admin-mosques"),
    path(
        "admin/seed-defaults/", AdminMosqueSeedDefaultsAPIView.as_view(), name="admin-mosques-seed"
    ),
    path("admin/<int:mosque_id>/", AdminMosqueDetailAPIView.as_view(), name="admin-mosque-detail"),
]

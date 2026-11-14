"""مسیرهای بررسی سلامت سرویس زیر `/api/v1/health/`."""

from __future__ import annotations

from django.urls import path

from .views import HealthDetailedAPIView, HealthPingAPIView, HealthReadyAPIView

app_name = "health"

urlpatterns = [
    path("", HealthPingAPIView.as_view(), name="health-ping"),
    path("live/", HealthPingAPIView.as_view(), name="health-live"),
    path("ready/", HealthReadyAPIView.as_view(), name="health-ready"),
    path("detailed/", HealthDetailedAPIView.as_view(), name="health-detailed"),
    path("deep/", HealthDetailedAPIView.as_view(), name="health-deep"),
]

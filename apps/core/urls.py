"""مسیرهای متادیتای زیرساخت مشترک."""

from __future__ import annotations

from django.urls import path

from .views import ServiceMetaAPIView

app_name = "core"

urlpatterns = [
    path("", ServiceMetaAPIView.as_view(), name="service-meta-root"),
    path("meta/", ServiceMetaAPIView.as_view(), name="service-meta"),
]

"""مسیرهای عمومی گالری (زیر `/api/v1/gallery/`)."""

from __future__ import annotations

from django.urls import path

from .views import GalleryAPIView, LeaderGalleryAPIView, MartyrsAPIView

app_name = "gallery"

urlpatterns = [
    path("", GalleryAPIView.as_view(), name="all"),
    path("leader/", LeaderGalleryAPIView.as_view(), name="leader"),
    path("martyrs/", MartyrsAPIView.as_view(), name="martyrs"),
]

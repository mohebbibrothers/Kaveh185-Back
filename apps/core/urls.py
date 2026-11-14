"""مسیرهای متادیتای زیرساخت مشترک و بستهٔ یکپارچهٔ صفحه اول."""

from __future__ import annotations

from django.urls import path

from apps.exam.views import PublicLandingBootstrapAPIView

from .views import ServiceMetaAPIView

app_name = "core"

urlpatterns = [
    path("", ServiceMetaAPIView.as_view(), name="service-meta-root"),
    path("meta/", ServiceMetaAPIView.as_view(), name="service-meta"),
    path("bootstrap/", PublicLandingBootstrapAPIView.as_view(), name="public-bootstrap"),
]

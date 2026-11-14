"""مسیریابی مرکزی URLهای سامانه کاوه ۱۸۵ (`/api/v1/...`)."""

from __future__ import annotations

from django.conf import settings
from django.contrib import admin
from django.urls import include, path

from apps.core.docs_gate import (
    GatedSpectacularAPIView,
    GatedSpectacularRedocView,
    GatedSpectacularSwaggerView,
)
from apps.core.metrics_views import PrometheusMetricsView

admin_url = str(getattr(settings, "ADMIN_URL_PATH", "secure-kaveh185-admin/")).lstrip("/")
if not admin_url.endswith("/"):
    admin_url += "/"

urlpatterns = [
    path(admin_url, admin.site.urls),
    # پروب‌های سلامت، متریک‌ها و متادیتای نسخه
    path("api/v1/health/", include("apps.core.health.urls")),
    path("api/v1/metrics/", PrometheusMetricsView.as_view(), name="prometheus-metrics"),
    path("api/v1/core/", include("apps.core.urls")),
    # مستندات OpenAPI 3.0 (Swagger UI و ReDoc)
    path("api/v1/schema/", GatedSpectacularAPIView.as_view(), name="schema"),
    path("api/v1/docs/", GatedSpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/v1/redoc/", GatedSpectacularRedocView.as_view(url_name="schema"), name="redoc"),
    # دامنه‌های اصلی سامانه کاوه ۱۸۵
    path("api/v1/auth/", include("apps.authentication.urls")),
    path("api/v1/mosques/", include("apps.mosques.urls")),
    path("api/v1/exam/", include("apps.exam.urls")),
    path("api/v1/reporting/", include("apps.reporting.urls")),
    path("api/v1/notifications/", include("apps.notifications.urls")),
    path("api/v1/audit-logs/", include("apps.audit_logs.urls")),
    path("api/v1/admin/command-center/", include("apps.command_center.urls")),
]

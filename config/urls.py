"""مسیریابی مرکزی URLهای سامانه کاوه ۱۸۵ (`/api/v1/...`)."""

from __future__ import annotations

from django.conf import settings
from django.contrib import admin
from django.http import FileResponse, Http404, HttpRequest
from django.urls import include, path, re_path

from apps.core.docs_gate import (
    GatedSpectacularAPIView,
    GatedSpectacularRedocView,
    GatedSpectacularSwaggerView,
)
from apps.core.media import serve_media
from apps.core.metrics_views import PrometheusMetricsView
from apps.core.responses import not_found_response
from apps.core.views import APIRootDiscoveryView

admin_url = str(getattr(settings, "ADMIN_URL_PATH", "secure-kaveh185-admin/")).lstrip("/")
if not admin_url.endswith("/"):
    admin_url += "/"


# ── رسانه ────────────────────────────────────────────────────────────────
def serve_media_or_404(request: HttpRequest, path: str) -> FileResponse:
    """سرو رسانه؛ اگر `MEDIA_ROOT` تنظیم نشده باشد، ۴۰۴ صریح (نه خطای ۵۰۰)."""
    if not getattr(settings, "MEDIA_ROOT", None):
        raise Http404("ریشهٔ رسانه تنظیم نشده است.")
    return serve_media(request, path)


urlpatterns = [
    # ریشهٔ دامنه دیگر JSON نمی‌دهد: `/` صفحهٔ اول خودِ سایت است و در صورت
    # نبودِ فرانت، `FrontendMiddleware` صفحهٔ ۵۰۳ فارسی می‌دهد.
    # نما Discovery به همان مسیر صریح `api/v1/` منتقل شد.
    path("api/v1/", APIRootDiscoveryView.as_view(), name="api-v1-discovery"),
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
    path("api/v1/gallery/", include("apps.gallery.urls")),
    path("api/v1/audit-logs/", include("apps.audit_logs.urls")),
    path("api/v1/admin/command-center/", include("apps.command_center.urls")),
    # ── رسانه ────────────────────────────────────────────────────────────
    # مستقل از `DEBUG`: روی هاست `DEBUG=False` است و بدون این خط، تصاویر
    # ادمین (گالری/شهدا) با ۴۰۴ برمی‌گردند. نمای اختصاصی، فقط تصویر و PDF.
    re_path(
        r"^media/(?P<path>.*)$",
        serve_media_or_404,
        name="media",
    ),
    path(
        "api/v1/command-center/",
        include(("apps.command_center.urls", "command_center"), namespace="command_center_alias"),
    ),
]


# ── ۴۰۴ استاندارد ────────────────────────────────────────────────────────
def _handler404(request: object, exception: object = None) -> object:
    """۴۰۴ JSON برای `/api/`؛ ۴۰۴ معمولی برای بقیه.

    تفکیک لازم است چون دو مصرف‌کنندهٔ متفاوت داریم:
      • کلاینت API انتظار پاکت JSON دارد؛ HTML یعنی `JSON.parse` می‌شکند
        و پیام گمراه‌کنندهٔ «خطای نامشخص» نشان داده می‌شود.
      • کاربر انسانی روی مسیرهای سایت باید صفحهٔ ۴۰۴ خودِ فرانت را ببیند
        (که `apps/core/frontend.py` سرو می‌کند، با وضعیت واقعی ۴۰۴).

    امضای `(request, exception)` اجباری است: جنگو در حالت DEBUG با
    آرگومان دوم صدا می‌زند و بدون آن `TypeError` می‌دهد.
    """
    path = getattr(request, "path_info", "") or ""
    if path.startswith("/api/"):
        return not_found_response(path=path)
    return default_page_not_found(request, exception)


from django.views.defaults import page_not_found as default_page_not_found  # noqa: E402

handler404 = _handler404

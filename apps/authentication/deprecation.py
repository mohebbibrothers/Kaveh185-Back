"""مدیریت هدرهای استاندارد منسوخ‌سازی (`Deprecation`, `Sunset`, `Link`) مطابق RFC 8594."""

from __future__ import annotations

import logging
from typing import Final

from decouple import config
from rest_framework.request import Request
from rest_framework.response import Response

from apps.core.client_ip import get_client_ip

logger = logging.getLogger("apps.authentication")

DEPRECATION_HEADER: Final[str] = "Deprecation"
SUNSET_HEADER: Final[str] = "Sunset"
SUCCESSOR_LINK_HEADER: Final[str] = "Link"

LEGACY_AUTH_SUNSET: Final[str] = config(
    "AUTH_LEGACY_SUNSET", default="Wed, 31 Dec 2026 23:59:59 GMT"
)


def build_deprecation_headers(*, successor: str | None = None) -> dict[str, str]:
    """ساخت هدرهای استاندارد RFC 8594 برای مسیرهای قدیمی که جایگزین نسخه‌دار دارند."""
    headers: dict[str, str] = {DEPRECATION_HEADER: "true"}
    if LEGACY_AUTH_SUNSET:
        headers[SUNSET_HEADER] = LEGACY_AUTH_SUNSET
    if successor:
        headers[SUCCESSOR_LINK_HEADER] = f'<{successor}>; rel="successor-version"'
    return headers


def add_deprecation_headers(response: Response, *, successor: str | None = None) -> Response:
    """افزودن هدرهای منسوخ‌سازی به پاسخ DRF."""
    for key, val in build_deprecation_headers(successor=successor).items():
        response[key] = val
    return response


def log_legacy_endpoint_usage(
    *,
    endpoint_name: str,
    request: Request,
    successor: str | None = None,
) -> None:
    """ثبت لاگ هشدار هنگام استفاده از مسیرهای Legacy برای رصد مهاجرت فرانت‌اند."""
    user = getattr(request, "user", None)
    user_id = getattr(user, "pk", None) if getattr(user, "is_authenticated", False) else None
    ip_addr = get_client_ip(request)
    logger.warning(
        "Legacy auth endpoint used endpoint=%s user_id=%s ip=%s successor=%s",
        endpoint_name,
        user_id,
        ip_addr,
        successor,
    )

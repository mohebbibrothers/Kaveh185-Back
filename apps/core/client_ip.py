"""استخراج امن IP واقعی کلاینت و پیشوند شبکه با محافظت در برابر جعل هدرهای پراکسی."""

from __future__ import annotations

import ipaddress
from typing import Any

from django.conf import settings


def get_client_ip(request: Any) -> str:
    """استخراج IP کلاینت با بررسی اعتبار پراکسی معکوس (Trusted Proxy)."""
    meta = getattr(request, "META", {}) or {}
    trust_xff = bool(getattr(settings, "TRUST_X_FORWARDED_FOR", True))
    if trust_xff:
        xff = str(meta.get("HTTP_X_FORWARDED_FOR", "")).strip()
        if xff:
            first_ip = xff.split(",")[0].strip()
            try:
                ipaddress.ip_address(first_ip)
                return first_ip
            except ValueError:
                pass
    real_ip = str(meta.get("HTTP_X_REAL_IP", "")).strip()
    if trust_xff and real_ip:
        try:
            ipaddress.ip_address(real_ip)
            return real_ip
        except ValueError:
            pass
    remote_addr = str(meta.get("REMOTE_ADDR", "127.0.0.1")).strip() or "127.0.0.1"
    try:
        ipaddress.ip_address(remote_addr)
        return remote_addr
    except ValueError:
        return "127.0.0.1"


def get_network_prefix(ip_str: str) -> str:
    """استخراج پیشوند شبکه (`/24` برای IPv4 و `/48` برای IPv6) برای نمایش ایمن نشست‌ها."""
    try:
        addr = ipaddress.ip_address(ip_str)
    except ValueError:
        return ""
    prefix = 24 if addr.version == 4 else 48
    return str(ipaddress.ip_network(f"{addr}/{prefix}", strict=False))

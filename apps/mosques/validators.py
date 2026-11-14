"""اعتبارسنج‌های دامنهٔ مساجد."""

from __future__ import annotations

import re

from apps.core.exceptions import ValidationDomainError

_MOSQUE_CODE_RE = re.compile(r"^[A-Za-z0-9_-]{2,32}$")


def validate_mosque_code(code: str) -> str:
    """بررسی صحت ساختار کد یکتای مسجد."""
    cleaned = str(code or "").strip().upper()
    if not _MOSQUE_CODE_RE.match(cleaned):
        raise ValidationDomainError(
            "کد مسجد باید شامل ۲ تا ۳۲ کاراکتر انگلیسی، عدد یا خط تیره باشد.",
            code="invalid_mosque_code",
        )
    return cleaned

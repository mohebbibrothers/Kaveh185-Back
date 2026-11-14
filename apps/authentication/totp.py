"""پیاده‌سازی استاندارد RFC 6238 برای تأیید دومرحله‌ای (TOTP) و کدهای بازیابی ادمین."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote


def generate_totp_secret() -> str:
    """تولید راز ۲۰ بایتی با کدگذاری Base32 استاندارد برای اپلیکیشن‌های Authenticator."""
    raw = secrets.token_bytes(20)
    return base64.b32encode(raw).decode("ascii").rstrip("=")


def compute_totp_code(secret_b32: str, *, timestamp: float | None = None, step: int = 30) -> str:
    """محاسبهٔ کد ۶ رقمی TOTP طبق استاندارد RFC 6238 برای زمان مشخص."""
    padded = secret_b32.strip().upper()
    rem = len(padded) % 8
    if rem:
        padded += "=" * (8 - rem)
    key = base64.b32decode(padded, casefold=True)
    ts = int(timestamp if timestamp is not None else time.time())
    counter = ts // step
    counter_bytes = struct.pack(">Q", counter)
    digest = hmac.new(key, counter_bytes, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    truncated = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    code = truncated % 1_000_000
    return f"{code:06d}"


def verify_totp_code(
    secret_b32: str,
    candidate: str,
    *,
    timestamp: float | None = None,
    window: int = 1,
) -> bool:
    """بررسی کد ۶ رقمی TOTP با تحمل پنجرهٔ زمانی `±window` گام ۳۰ ثانیه‌ای."""
    clean = str(candidate or "").strip()
    if len(clean) != 6 or not clean.isdigit():
        return False
    base_ts = timestamp if timestamp is not None else time.time()
    for offset in range(-window, window + 1):
        expected = compute_totp_code(secret_b32, timestamp=base_ts + (offset * 30))
        if hmac.compare_digest(expected, clean):
            return True
    return False


def build_otpauth_uri(*, secret_b32: str, account_label: str, issuer: str = "Kaveh185") -> str:
    """ساخت URI استاندارد `otpauth://totp/...` برای اسکن در Google/Microsoft Authenticator."""
    safe_issuer = quote(issuer)
    safe_label = quote(account_label)
    return f"otpauth://totp/{safe_issuer}:{safe_label}?secret={secret_b32}&issuer={safe_issuer}&digits=6&period=30"


def generate_recovery_codes(count: int = 8) -> tuple[list[str], list[str]]:
    """تولید کدهای بازیابی یک‌بارمصرف (نمایش به کاربر + لیست هش‌های SHA-256 برای ذخیره)."""
    plain_codes: list[str] = []
    hashed_codes: list[str] = []
    for _ in range(count):
        code = f"{secrets.token_hex(2).upper()}-{secrets.token_hex(2).upper()}"
        plain_codes.append(code)
        hashed_codes.append(hashlib.sha256(code.encode("utf-8")).hexdigest())
    return plain_codes, hashed_codes

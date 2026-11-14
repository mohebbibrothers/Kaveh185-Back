"""تولید و بررسی کد یک‌بارمصرف پیامکی (OTP) با هش نمک‌دار و مقایسهٔ زمان‌ثابت."""

from __future__ import annotations

import hashlib
import hmac
import secrets

from .constants import OTP_LENGTH


def generate_otp_code(length: int = OTP_LENGTH) -> str:
    """تولید کد عددی تصادفی از نظر رمزنگاری امن با استفاده از ماژول `secrets`."""
    digits = "0123456789"
    return "".join(secrets.choice(digits) for _ in range(length))


def generate_otp_salt() -> str:
    """تولید نمک ۱۶ بایتی تصادفی (۳۲ کاراکتر هگز) برای هر رکورد OTP."""
    return secrets.token_hex(16)


def hash_otp_code(code: str, salt: str) -> str:
    """محاسبهٔ هش SHA-256 کد OTP همراه با نمک اختصاصی."""
    payload = f"{salt}:{code.strip()}".encode()
    return hashlib.sha256(payload).hexdigest()


def verify_otp_hash(*, candidate_code: str, salt: str, expected_hash: str) -> bool:
    """مقایسهٔ زمان‌ثابت (`hmac.compare_digest`) برای جلوگیری از حملات زمان‌سنجی (Timing Attack)."""
    candidate_hash = hash_otp_code(candidate_code, salt)
    return hmac.compare_digest(candidate_hash, expected_hash)

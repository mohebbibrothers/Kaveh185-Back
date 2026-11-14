"""رمزنگاری اطلاعات هویتی حساس (PII) با AES-GCM و ایندکس‌گذاری کور HMAC-SHA256.

چرا این ماژول وجود دارد:
    در سامانهٔ کاوه ۱۸۵، کدملی و شماره تماس کاربران دریافت می‌شود. برای رعایت
    استاندارد ASVS L2 و حفاظت در برابر نشت احتمالی بکاپ دیتابیس:
    ۱) مقدار حساس با AES-256-GCM و nonce تصادفی ۹۶ بیتی رمزنگاری می‌شود.
    ۲) برای جست‌وجوی دقیق و بررسی یکتایی سریع در سطح دیتابیس بدون رمزگشایی،
       یک Blind Index با HMAC-SHA256 ساخته می‌شود.
    ۳) توابع پوشاندن (Masking) برای نمایش ایمن در کارنامه و لاگ‌ها فراهم شده است.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from django.conf import settings


def _derive_aes_key() -> bytes:
    """استخراج کلید ۳۲ بایتی معتبر برای AES-256-GCM از تنظیمات پروژه."""
    raw = getattr(settings, "FIELD_ENCRYPTION_KEY", "") or settings.SECRET_KEY
    return hashlib.sha256(str(raw).encode("utf-8")).digest()


def _derive_hmac_key() -> bytes:
    """استخراج کلید مجزا برای HMAC Blind Index از تنظیمات پروژه."""
    raw = getattr(settings, "FIELD_HASH_KEY", "") or f"hmac:{settings.SECRET_KEY}"
    return hashlib.sha256(str(raw).encode("utf-8")).digest()


def encrypt_pii(plaintext: str) -> str:
    """رمزنگاری متن حساس با AES-256-GCM و خروجی Base64 استاندارد (`v1:<b64>`)."""
    if not plaintext:
        return ""
    aesgcm = AESGCM(_derive_aes_key())
    nonce = secrets.token_bytes(12)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), associated_data=b"kaveh185-pii")
    encoded = base64.urlsafe_b64encode(nonce + ciphertext).decode("ascii")
    return f"v1:{encoded}"


def decrypt_pii(token: str) -> str:
    """رمزگشایی توکن تولیدشده توسط `encrypt_pii`."""
    if not token:
        return ""
    if not token.startswith("v1:"):
        return token
    payload = token[3:]
    raw = base64.urlsafe_b64decode(payload.encode("ascii"))
    nonce, ciphertext = raw[:12], raw[12:]
    aesgcm = AESGCM(_derive_aes_key())
    decrypted = aesgcm.decrypt(nonce, ciphertext, associated_data=b"kaveh185-pii")
    return decrypted.decode("utf-8")


def blind_index(value: str, *, purpose: str = "default") -> str:
    """تولید ایندکس کور قطعی با HMAC-SHA256 برای جست‌وجو و قید یکتایی."""
    normalized = value.strip()
    if not normalized:
        return ""
    msg = f"{purpose}:{normalized}".encode()
    return hmac.new(_derive_hmac_key(), msg, hashlib.sha256).hexdigest()


def mask_national_id(national_id: str) -> str:
    """پوشاندن کدملی برای نمایش ایمن عمومی (نمایش فقط ۳ رقم اول و ۲ رقم آخر)."""
    clean = national_id.strip()
    if len(clean) != 10:
        return "***"
    return f"{clean[:3]}*****  {clean[-2:]}".replace(" ", "")


def mask_phone(phone: str) -> str:
    """پوشاندن شماره موبایل برای نمایش ایمن عمومی (مثلاً `0912***4567`)."""
    clean = phone.strip()
    if len(clean) < 7:
        return "***"
    return f"{clean[:4]}***{clean[-4:]}"

"""تولیدکنندهٔ یکنواخت UUIDv7 مطابق RFC 9562 برای کلیدها و شناسه‌های ردیابی.

چرا UUIDv7:
    برخلاف UUIDv4 که کاملاً تصادفی است و باعث تکهتکهشدن ایندکس B-Tree دیتابیس
    می‌شود، UUIDv7 پیشوند زمانی ۴۸ بیتی (میلی‌ثانیهٔ یونیکس) دارد و با یک شمارندهٔ
    یکنواخت درون‌پردازشی ترکیب می‌شود تا ترتیب زمانی درج رکوردها همیشه حفظ گردد.
"""

from __future__ import annotations

import secrets
import threading
import time
import uuid

_LOCK = threading.Lock()
_LAST_MS = 0
_COUNTER = 0
_RAND_A_MAX = 0xFFF
_VERSION_7 = 0x7
_VARIANT_RFC4122 = 0b10


def uuid7() -> uuid.UUID:
    """تولید یک UUIDv7 یکنواخت و ایمن در برابر تداخل رشته‌ها (Thread-Safe)."""
    global _LAST_MS, _COUNTER
    now_ms = int(time.time() * 1000)

    with _LOCK:
        if now_ms > _LAST_MS:
            _LAST_MS = now_ms
            _COUNTER = secrets.randbits(12)
        else:
            now_ms = _LAST_MS
            _COUNTER = (_COUNTER + 1) & _RAND_A_MAX
            if _COUNTER == 0:
                _LAST_MS += 1
                now_ms = _LAST_MS

        rand_a = _COUNTER
        ts_ms = now_ms

    rand_b = secrets.randbits(62)

    value = (ts_ms & 0xFFFFFFFFFFFF) << 80
    value |= (_VERSION_7 & 0xF) << 76
    value |= (rand_a & _RAND_A_MAX) << 64
    value |= (_VARIANT_RFC4122 & 0x3) << 62
    value |= rand_b & ((1 << 62) - 1)
    return uuid.UUID(int=value)


def uuid7_hex() -> str:
    """بازگرداندن نمایش ۳۲ کاراکتری بدون خط تیره از یک UUIDv7 تازه."""
    return uuid7().hex


def uuid7_time_ms(value: uuid.UUID) -> int:
    """استخراج مهر زمان (میلی‌ثانیهٔ یونیکس) از درون یک UUIDv7."""
    return value.int >> 80

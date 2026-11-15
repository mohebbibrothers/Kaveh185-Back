"""قفلِ تنظیمات کلید رمزنگاری PII.

چرا این تست وجود دارد:
    `apps/core/crypto.py` کلید را از `settings.FIELD_ENCRYPTION_KEY` می‌خواند،
    ولی `config/settings/base.py` تنها `PII_ENCRYPTION_KEY` را ست می‌کرد.
    نتیجه این بود که مقدار `.env` هرگز به کار نمی‌رفت و رمزنگاری بی‌سروصدا
    به `SECRET_KEY` برمی‌گشت. این باگ هیچ خطایی نمی‌داد؛ فقط داده‌های هویتی
    را به یک کلید تنها گره می‌زد. تست زیر همان اتصال را قفل می‌کند.
"""

from __future__ import annotations

import pytest
from django.conf import settings

from apps.core.crypto import blind_index, decrypt_pii, encrypt_pii


def test_field_encryption_key_is_bridged_from_pii_setting() -> None:
    """کلید رمزنگاری باید همان PII_ENCRYPTION_KEY باشد، نه SECRET_KEY."""
    assert hasattr(settings, "PII_ENCRYPTION_KEY")
    assert settings.FIELD_ENCRYPTION_KEY == settings.PII_ENCRYPTION_KEY


def test_field_hash_key_is_bridged_from_blind_index_setting() -> None:
    """کلید ایندکس کور باید همان PII_BLIND_INDEX_KEY باشد."""
    assert settings.FIELD_HASH_KEY == settings.PII_BLIND_INDEX_KEY


def test_encryption_and_blind_index_can_be_independent(settings: object) -> None:
    """اگر دو کلید جدا تنظیم شوند، کلیدهای مشتق‌شده هم باید جدا باشند.

    توجه: در محیط تستِ پیش‌فرض، هر دو کلید به SECRET_KEY برمی‌گردند و
    مشتق‌شده‌ها یکی می‌شوند — این طبیعی است. آنچه باید تضمین شود این است که
    وقتی دو مقدار متفاوت داده می‌شود، جداسازی دامنهٔ کلید واقعاً رخ دهد.
    """
    from apps.core.crypto import _derive_aes_key, _derive_hmac_key

    settings.FIELD_ENCRYPTION_KEY = "clave-aes-distinta-aaaaaaaaaaaaaaaa"  # type: ignore[attr-defined]
    settings.FIELD_HASH_KEY = "clave-hmac-distinta-bbbbbbbbbbbbbbbb"  # type: ignore[attr-defined]
    assert _derive_aes_key() != _derive_hmac_key()


def test_same_key_material_yields_same_derivation(settings: object) -> None:
    """اگر یک مقدار برای هر دو داده شود، اشتقاق‌ها یکی می‌شوند (رفتار مستند)."""
    from apps.core.crypto import _derive_aes_key, _derive_hmac_key

    settings.FIELD_ENCRYPTION_KEY = "unica-clave-misma-cccccccccccccccc"  # type: ignore[attr-defined]
    settings.FIELD_HASH_KEY = "unica-clave-misma-cccccccccccccccc"  # type: ignore[attr-defined]
    assert _derive_aes_key() == _derive_hmac_key()


@pytest.mark.parametrize("value", ["0013542419", "09121234567", "x"])
def test_round_trip_with_configured_key(value: str) -> None:
    """رمزگذاری و رمزگشایی با کلیدِ پیکربندی‌شده باید رفت‌وبرگشت کند."""
    assert decrypt_pii(encrypt_pii(value)) == value


def test_blind_index_is_stable_and_not_plaintext() -> None:
    """ایندکس کور باید پایدار و غیرقابل بازگشت باشد."""
    a = blind_index("0013542419")
    b = blind_index("0013542419")
    assert a == b
    assert "0013542419" not in a

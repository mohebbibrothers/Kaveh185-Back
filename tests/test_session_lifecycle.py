"""تست‌های چرخهٔ نشست ورود — «توکن من هنوز معتبر است؟»

چرا مهم است؟
───────────
رفرستوکن‌ها بی‌نشست‌اند یعنی هیچ راهی برای بیرون کردن یک دستگاه نیست.
اینجا قفل می‌کنیم که: نشست لغوشده همان لحظه بی‌اعتبار شود، نشستی که
کاربرش غیرفعال شده معتبر نماند، و `last_seen_at` با فاصلهٔ مشخص تازه شود
نه در هر درخواست (که یک نوشتن در دیتابیس روی هر کلیک است).
"""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.authentication.constants import SESSION_TOUCH_INTERVAL_SECONDS
from apps.authentication.models import AuthSession
from apps.authentication.services import validate_and_touch_session

pytestmark = pytest.mark.django_db

User = get_user_model()


def _user(phone: str = "09125550000") -> User:
    return User.objects.create_user(
        phone_number=phone,
        national_id="0009900012",
        first_name="سینا",
        last_name="نشست",
        birth_date="1370-01-01",
    )


def _sid(label: str) -> str:
    """شناسهٔ نشست، UUID واقعی — مدل مقدار غیر-UUID را نمی‌پذیرد."""
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, label))


def _session(user, *, sid: str, revoked: bool = False) -> AuthSession:
    return AuthSession.objects.create(
        user=user,
        session_uid=sid,
        refresh_jti="jti-1",
        is_revoked=revoked,
        last_seen_at=timezone.now(),
    )


class _Claims(dict):
    """شبیه‌سازی payload توکن JWT (پشتیبانی از .get)."""


def test_valid_session_is_returned() -> None:
    """نشست زندهٔ کاربر فعال برمی‌گردد."""
    user = _user()
    _session(user, sid=_sid("ok"))
    assert validate_and_touch_session(user=user, token_claims=_Claims(sid=_sid("ok"))) is not None


def test_revoked_session_is_rejected() -> None:
    """نشست لغوشده همان لحظه بی‌اعتبار است (خروج از دستگاه)."""
    user = _user()
    _session(user, sid=_sid("revoked"), revoked=True)
    assert validate_and_touch_session(user=user, token_claims=_Claims(sid=_sid("revoked"))) is None


def test_unknown_sid_is_rejected() -> None:
    """`sid` ناشناخته پذیرفته نمی‌شود."""
    user = _user()
    assert validate_and_touch_session(user=user, token_claims=_Claims(sid=_sid("ghost"))) is None


def test_missing_sid_is_rejected() -> None:
    """توکن بدون `sid` (مثلاً توکن قدیمی) معتبر شمرده نمی‌شود."""
    user = _user()
    assert validate_and_touch_session(user=user, token_claims=_Claims()) is None


def test_inactive_user_is_rejected() -> None:
    """کاربر غیرفعال‌شده، حتی با نشست زنده، رد می‌شود."""
    user = _user()
    _session(user, sid=_sid("off"))
    user.is_active = False
    user.save(update_fields=["is_active"])
    assert validate_and_touch_session(user=user, token_claims=_Claims(sid=_sid("off"))) is None


def test_touch_respects_interval() -> None:
    """`last_seen_at` فقط پس از گذشتن فاصلهٔ تعیین‌شده تازه می‌شود."""
    user = _user()
    session = _session(user, sid=_sid("touch"))
    # تازه لمس شده ⇒ نوشتن دوباره نباید رخ دهد
    validate_and_touch_session(user=user, token_claims=_Claims(sid=_sid("touch")))
    session.refresh_from_db()
    first = session.last_seen_at

    # عقب بردن ساعت، سپس درخواست بعدی باید تازه‌اش کند
    AuthSession.objects.filter(pk=session.pk).update(
        last_seen_at=timezone.now() - timedelta(seconds=SESSION_TOUCH_INTERVAL_SECONDS + 5)
    )
    validate_and_touch_session(user=user, token_claims=_Claims(sid=_sid("touch")))
    session.refresh_from_db()
    assert session.last_seen_at > first


def test_none_user_is_safe() -> None:
    """کاربر `None` (درخواست بی‌توکن) خطا نمی‌دهد."""
    assert validate_and_touch_session(user=None, token_claims=_Claims(sid=_sid("anon"))) is None

"""سرویس‌های ثبت‌نام شرکت‌کنندگان، احراز هویت دوحالته، مدیریت نشست‌ها، MFA و ریسک."""

from __future__ import annotations

import hashlib
from datetime import date, timedelta
from typing import Any

from django.conf import settings
from django.db import models, transaction
from django.utils import timezone
from rest_framework_simplejwt.tokens import RefreshToken

from apps.audit_logs.choices import AuditAction
from apps.audit_logs.services import record_audit_log
from apps.core.client_ip import get_client_ip, get_network_prefix
from apps.core.crypto import decrypt_pii, encrypt_pii
from apps.core.exceptions import (
    ConflictDomainError,
    ForbiddenDomainError,
    NotFoundDomainError,
    UnauthorizedDomainError,
    ValidationDomainError,
)
from apps.core.outbox import enqueue_outbox
from apps.mosques.models import Mosque
from apps.mosques.selectors import get_active_mosque_by_id
from apps.mosques.services import increment_mosque_registered_count

from .anti_abuse import enforce_otp_anti_abuse
from .choices import OTPPurpose, RiskSeverity, RiskSignalType, UserRole
from .constants import (
    OTP_MAX_VERIFY_ATTEMPTS,
    OTP_TTL_SECONDS,
    SESSION_TOUCH_INTERVAL_SECONDS,
)
from .models import AuthRiskSignal, AuthSession, OTPChallenge, User
from .otp import generate_otp_code, generate_otp_salt, hash_otp_code, verify_otp_hash
from .totp import (
    build_otpauth_uri,
    generate_recovery_codes,
    generate_totp_secret,
    verify_totp_code,
)
from .validators import (
    normalize_and_validate_national_id,
    normalize_and_validate_phone,
    parse_and_validate_birth_date,
)

_BROWSERS = (
    ("Edg/", "Edge"),
    ("OPR/", "Opera"),
    ("Firefox/", "Firefox"),
    ("Chrome/", "Chrome"),
    ("Safari/", "Safari"),
)
_SYSTEMS = (
    ("Android", "Android"),
    ("iPhone", "iOS"),
    ("iPad", "iPadOS"),
    ("Windows", "Windows"),
    ("Mac OS X", "macOS"),
    ("Linux", "Linux"),
)


def describe_device(user_agent: str) -> str:
    """استخراج برچسب کوتاه مرورگر و سیستم‌عامل از روی User-Agent."""
    ua = str(user_agent or "")
    browser = next((label for token, label in _BROWSERS if token in ua), "مرورگر وب")
    os_label = next((label for token, label in _SYSTEMS if token in ua), "")
    return f"{browser} · {os_label}" if os_label else browser


def issue_tokens_and_session(
    *,
    user: User,
    request: Any = None,
    mfa_verified: bool = False,
) -> dict[str, Any]:
    """ایجاد رکورد `AuthSession` و صدور توکن‌های JWT (`access` و `refresh`) مقید به `sid`."""
    ip_addr = get_client_ip(request) if request is not None else "127.0.0.1"
    meta = getattr(request, "META", {}) if request is not None else {}
    user_agent = str(meta.get("HTTP_USER_AGENT", ""))[:300]
    now = timezone.now()

    session = AuthSession.objects.create(
        user=user,
        device_label=describe_device(user_agent),
        user_agent=user_agent,
        ip_address=ip_addr,
        network_prefix=get_network_prefix(ip_addr),
        last_seen_at=now,
        mfa_verified_at=now if mfa_verified else None,
        is_revoked=False,
    )

    refresh = RefreshToken.for_user(user)
    refresh["sid"] = session.sid_str
    refresh["role"] = user.role

    access = refresh.access_token
    access["sid"] = session.sid_str
    access["role"] = user.role

    session.refresh_jti = str(refresh.get("jti", ""))
    session.save(update_fields=["refresh_jti", "updated_at"])

    return {
        "access": str(access),
        "refresh": str(refresh),
        "session_uid": session.sid_str,
        "session": session,
    }


def validate_and_touch_session(*, user: Any, token_claims: Any) -> AuthSession | None:
    """اعتبارسنجی زنده بودن نشست (`sid`) در هر درخواست احرازشده و لمس `last_seen_at`."""
    if not user or not getattr(user, "is_active", False):
        return None
    sid = token_claims.get("sid") if hasattr(token_claims, "get") else None
    if not sid:
        return None
    try:
        session = AuthSession.objects.filter(
            user=user,
            session_uid=sid,
            is_revoked=False,
        ).first()
    except Exception:
        return None

    if session is None:
        return None

    now = timezone.now()
    if (now - session.last_seen_at).total_seconds() >= SESSION_TOUCH_INTERVAL_SECONDS:
        AuthSession.objects.filter(pk=session.pk).update(last_seen_at=now)
        session.last_seen_at = now
    return session


def register_or_enter_participant(
    *,
    first_name: str,
    last_name: str,
    national_id: str,
    phone_number: str,
    birth_date: str | date,
    mosque_id: int,
    request: Any = None,
) -> dict[str, Any]:
    """ثبت‌نام یکپارچهٔ شرکت‌کننده با کنترل سخت‌گیرانهٔ یکتایی کدملی و شماره تماس.

    قواعد کلیدی:
    ۱) کدملی و شماره تماس هر دو اعتبارسنجی و نرمال‌سازی می‌شوند.
    ۲) هیچ کاربری نمی‌تواند با یک شماره تلفن و کدملی‌های متفاوت یا با یک کدملی و
       شماره تلفن‌های متفاوت ثبت‌نام کند (`409 Conflict`).
    ۳) اگر همان کاربر (تطابق هم‌زمان کدملی و شماره تلفن) قبلاً ثبت‌نام کرده باشد:
       - در صورتی که هنوز آزمونی شروع نکرده باشد، اطلاعاتش به‌روز می‌شود.
       - اگر آزمونش در جریان یا تمام‌شده باشد، مسجد و هویتش قفل است تا تقلب نشود.
    ۴) بر اساس تنظیم زندهٔ ادمین (`require_otp_before_exam`)، یا بلافاصله توکن ورود به
       آزمون صادر می‌شود (پیش‌فرض برای سهولت حداکثری مشارکت مردم)، یا کد OTP پیامک می‌گردد.
    """
    from apps.exam.choices import ExamAttemptStatus
    from apps.exam.models import ExamAttempt
    from apps.exam.selectors import get_or_create_exam_configuration

    norm_phone = normalize_and_validate_phone(phone_number)
    norm_nid = normalize_and_validate_national_id(national_id)
    parsed_birth = parse_and_validate_birth_date(birth_date)
    clean_first = str(first_name or "").strip()
    clean_last = str(last_name or "").strip()
    if not clean_first or not clean_last:
        raise ValidationDomainError("وارد کردن نام و نام خانوادگی الزامی است.")

    mosque = get_active_mosque_by_id(int(mosque_id))

    with transaction.atomic():
        by_phone = User.objects.select_for_update().filter(phone_number=norm_phone).first()
        by_nid = User.objects.select_for_update().filter(national_id=norm_nid).first()

        if by_phone is not None and by_phone.national_id != norm_nid:
            raise ConflictDomainError(
                "این شماره تماس قبلاً با کد ملی دیگری در سامانه ثبت شده است. "
                "امکان شرکت با یک شماره تماس و کد ملی متفاوت وجود ندارد.",
                code="phone_already_registered",
                errors={"phone_number": ["این شماره تماس متعلق به کد ملی دیگری است."]},
            )

        if by_nid is not None and by_nid.phone_number != norm_phone:
            raise ConflictDomainError(
                "این کد ملی قبلاً با شماره تماس دیگری در سامانه ثبت شده است. "
                "امکان شرکت با یک کد ملی و شماره تماس متفاوت وجود ندارد.",
                code="national_id_already_registered",
                errors={"national_id": ["این کد ملی با شماره تماس دیگری ثبت شده است."]},
            )

        created_new = False
        if by_phone is None:
            user = User.objects.create_user(
                phone_number=norm_phone,
                national_id=norm_nid,
                first_name=clean_first,
                last_name=clean_last,
                birth_date=parsed_birth,
                mosque=mosque,
                role=UserRole.PARTICIPANT,
                is_phone_verified=False,
            )
            increment_mosque_registered_count(mosque.id)
            created_new = True
            record_audit_log(
                action=AuditAction.USER_REGISTERED,
                resource_type="user",
                resource_id=user.pk,
                user=user,
                request=request,
                changes={
                    "mosque_id": mosque.id,
                    "mosque_name": mosque.name,
                },
            )
        else:
            user = by_phone
            existing_attempt = ExamAttempt.objects.filter(user=user).first()
            if existing_attempt is not None and existing_attempt.status in {
                ExamAttemptStatus.COMPLETED,
                ExamAttemptStatus.TIMED_OUT,
            }:
                raise ConflictDomainError(
                    "شما قبلاً در این آزمون شرکت کرده‌اید و هر نفر فقط یک بار مجاز به شرکت در آزمون است.",
                    code="exam_already_completed",
                    errors={
                        "tracking_code": existing_attempt.tracking_code,
                    },
                )
            # اگر هنوز آزمونی شروع نشده، اجازهٔ اصلاح نام/تاریخ تولد/مسجد پیش از شروع آزمون وجود دارد
            if existing_attempt is None:
                old_mosque_id = user.mosque_id
                user.first_name = clean_first
                user.last_name = clean_last
                user.birth_date = parsed_birth
                user.mosque = mosque
                user.save(
                    update_fields=["first_name", "last_name", "birth_date", "mosque", "updated_at"]
                )
                if old_mosque_id != mosque.id:
                    if old_mosque_id:
                        Mosque.all_objects.filter(
                            pk=old_mosque_id,
                            registered_count__gt=0,
                        ).update(registered_count=models.F("registered_count") - 1)
                    increment_mosque_registered_count(mosque.id)

        exam_config = get_or_create_exam_configuration()
        if exam_config.require_otp_before_exam:
            otp_info = create_and_send_otp(
                phone_number=user.phone_number,
                purpose=OTPPurpose.REGISTER,
                request=request,
            )
            return {
                "otp_required": True,
                "created_new": created_new,
                "user": user,
                "otp": otp_info,
                "tokens": None,
            }

        if not user.is_phone_verified:
            user.is_phone_verified = True
            user.save(update_fields=["is_phone_verified", "updated_at"])

        tokens = issue_tokens_and_session(user=user, request=request)
        record_audit_log(
            action=AuditAction.USER_LOGGED_IN,
            resource_type="user",
            resource_id=user.pk,
            user=user,
            request=request,
            extra_data={"mode": "fast_direct", "created_new": created_new},
        )
        return {
            "otp_required": False,
            "created_new": created_new,
            "user": user,
            "otp": None,
            "tokens": tokens,
        }


def create_and_send_otp(
    *,
    phone_number: str,
    purpose: Any = OTPPurpose.LOGIN,
    request: Any = None,
) -> dict[str, Any]:
    """ایجاد رکورد `OTPChallenge` و ثبت پیامک در Transactional Outbox."""
    norm_phone = normalize_and_validate_phone(phone_number)
    ip_addr = get_client_ip(request) if request is not None else "127.0.0.1"
    enforce_otp_anti_abuse(phone_number=norm_phone, ip_address=ip_addr)

    code = generate_otp_code()
    salt = generate_otp_salt()
    code_hash = hash_otp_code(code, salt)
    expires_at = timezone.now() + timedelta(seconds=OTP_TTL_SECONDS)

    challenge = OTPChallenge.objects.create(
        phone_number=norm_phone,
        purpose=purpose,
        code_salt=salt,
        code_hash=code_hash,
        expires_at=expires_at,
        ip_address=ip_addr,
    )

    enqueue_outbox(
        topic="sms.otp",
        recipient=norm_phone,
        payload={
            "phone_number": norm_phone,
            "code": code,
            "purpose": purpose,
            "challenge_id": challenge.id,
        },
    )
    result_payload: dict[str, Any] = {
        "challenge_id": challenge.id,
        "phone_number": norm_phone,
        "expires_in_seconds": OTP_TTL_SECONDS,
    }
    if getattr(settings, "OTP_EXPOSE_DEBUG_CODE", False):
        result_payload["debug_code"] = code
        result_payload["debug_otp_code"] = code
    return result_payload


def verify_otp_and_issue_session(
    *,
    phone_number: str,
    code: str,
    request: Any = None,
) -> dict[str, Any]:
    """بررسی کد OTP، فعال‌سازی تأیید شماره تماس و صدور نشست و توکن JWT."""
    norm_phone = normalize_and_validate_phone(phone_number)
    now = timezone.now()

    with transaction.atomic():
        challenge = (
            OTPChallenge.objects.select_for_update()
            .filter(
                phone_number=norm_phone,
                is_verified=False,
                expires_at__gt=now,
            )
            .order_by("-created_at", "-id")
            .first()
        )
        if challenge is None:
            raise ValidationDomainError(
                "کد تایید منقضی شده یا درخواستی برای این شماره ثبت نشده است.",
                code="otp_expired_or_missing",
            )

        if challenge.attempts >= OTP_MAX_VERIFY_ATTEMPTS:
            raise ValidationDomainError(
                "تعداد تلاش‌های ناموفق برای این کد به سقف مجاز رسیده است. لطفاً کد جدید دریافت کنید.",
                code="otp_max_attempts_exceeded",
            )

        if not verify_otp_hash(
            candidate_code=str(code or ""),
            salt=challenge.code_salt,
            expected_hash=challenge.code_hash,
        ):
            challenge.attempts += 1
            challenge.save(update_fields=["attempts", "updated_at"])
            user_for_risk = User.objects.filter(phone_number=norm_phone).first()
            if challenge.attempts >= 3:
                record_risk_signal(
                    user=user_for_risk,
                    signal_type=RiskSignalType.EXCESSIVE_OTP_ATTEMPTS,
                    severity=RiskSeverity.MEDIUM,
                    request=request,
                    details={"phone_number": norm_phone, "attempts": challenge.attempts},
                )
            raise ValidationDomainError(
                "کد تایید واردشده صحیح نیست.",
                code="invalid_otp_code",
            )

        challenge.is_verified = True
        challenge.verified_at = now
        challenge.save(update_fields=["is_verified", "verified_at", "updated_at"])

        user = User.objects.select_for_update().filter(phone_number=norm_phone).first()
        if user is None:
            raise NotFoundDomainError(
                "ابتدا فرم اطلاعات هویتی و انتخاب مسجد را تکمیل نمایید.",
                code="user_not_registered",
            )
        if not user.is_active:
            raise ForbiddenDomainError("حساب کاربری شما غیرفعال شده است.", code="user_inactive")

        if not user.is_phone_verified:
            user.is_phone_verified = True
            user.save(update_fields=["is_phone_verified", "updated_at"])

        tokens = issue_tokens_and_session(user=user, request=request)
        record_audit_log(
            action=AuditAction.USER_LOGGED_IN,
            resource_type="user",
            resource_id=user.pk,
            user=user,
            request=request,
            extra_data={"mode": "otp_verified"},
        )
        return {
            "user": user,
            "tokens": tokens,
        }


def login_with_password(
    *,
    identifier: str,
    password: str,
    request: Any = None,
) -> dict[str, Any]:
    """ورود با رمز عبور (مخصوص مدیران و اپراتورها با شماره تماس یا کدملی)."""
    clean_id = str(identifier or "").strip()
    user: User | None = None
    try:
        norm_phone = normalize_and_validate_phone(clean_id)
        user = User.objects.filter(phone_number=norm_phone).first()
    except Exception:
        try:
            norm_nid = normalize_and_validate_national_id(clean_id)
            user = User.objects.filter(national_id=norm_nid).first()
        except Exception:
            user = None

    if user is None or not user.check_password(str(password or "")):
        record_risk_signal(
            user=user,
            signal_type=RiskSignalType.EXCESSIVE_OTP_ATTEMPTS,
            severity=RiskSeverity.MEDIUM,
            request=request,
            details={"identifier": clean_id},
        )
        raise UnauthorizedDomainError(
            "شماره تماس/کدملی یا رمز عبور اشتباه است.",
            code="invalid_credentials",
        )
    if not user.is_active:
        raise ForbiddenDomainError("حساب کاربری غیرفعال است.", code="user_inactive")

    tokens = issue_tokens_and_session(user=user, request=request)
    record_audit_log(
        action=AuditAction.USER_LOGGED_IN,
        resource_type="user",
        resource_id=user.pk,
        user=user,
        request=request,
        extra_data={"mode": "password"},
    )
    return {
        "user": user,
        "tokens": tokens,
    }


def revoke_session_by_id(
    *,
    user: User,
    session_id: int | str,
    reason: str = "user_revoked",
    request: Any = None,
) -> AuthSession:
    """ابطال یک نشست مشخص متعلق به کاربر."""
    qs = AuthSession.objects.filter(user=user, is_revoked=False)
    if str(session_id).isdigit():
        session = qs.filter(pk=int(session_id)).first()
    else:
        session = qs.filter(session_uid=session_id).first()

    if session is None:
        raise NotFoundDomainError(
            "نشست مورد نظر یافت نشد یا قبلاً باطل شده است.", code="session_not_found"
        )

    session.is_revoked = True
    session.revoked_at = timezone.now()
    session.revoked_reason = reason[:160]
    session.save(update_fields=["is_revoked", "revoked_at", "revoked_reason", "updated_at"])

    record_audit_log(
        action=AuditAction.SESSION_REVOKED,
        resource_type="auth_session",
        resource_id=session.sid_str,
        user=user,
        request=request,
        reason=reason,
    )
    return session


def revoke_all_sessions_for_user(
    *,
    target_user: User,
    actor: User | None = None,
    exclude_sid: str = "",
    reason: str = "logout_all",
    request: Any = None,
) -> int:
    """ابطال تمام نشست‌های فعال یک کاربر (توسط خود کاربر یا ادمین)."""
    qs = AuthSession.objects.filter(user=target_user, is_revoked=False)
    if exclude_sid:
        qs = qs.exclude(session_uid=exclude_sid)
    now = timezone.now()
    count = qs.update(
        is_revoked=True,
        revoked_at=now,
        revoked_reason=reason[:160],
        updated_at=now,
    )
    record_audit_log(
        action=AuditAction.SESSION_REVOKED,
        resource_type="user_sessions",
        resource_id=target_user.pk,
        user=actor or target_user,
        request=request,
        reason=reason,
        extra_data={"revoked_count": count},
    )
    return int(count)


def setup_user_totp(*, user: User) -> dict[str, str]:
    """تولید راز TOTP جدید برای فعال‌سازی تأیید دومرحله‌ای روی حساب ادمین."""
    secret = generate_totp_secret()
    user.mfa_secret_encrypted = encrypt_pii(secret)
    user.save(update_fields=["mfa_secret_encrypted", "updated_at"])
    uri = build_otpauth_uri(secret_b32=secret, account_label=user.phone_number)
    return {
        "secret": secret,
        "otpauth_uri": uri,
    }


def confirm_user_totp(*, user: User, code: str, request: Any = None) -> list[str]:
    """تأیید کد اولیهٔ TOTP، فعال‌سازی MFA و صدور کدهای بازیابی."""
    if not user.mfa_secret_encrypted:
        raise ValidationDomainError(
            "ابتدا درخواست راه‌اندازی TOTP را ارسال کنید.", code="mfa_not_initialized"
        )
    secret = decrypt_pii(user.mfa_secret_encrypted)
    if not verify_totp_code(secret, code):
        raise ValidationDomainError(
            "کد تأیید دومرحله‌ای واردشده معتبر نیست.", code="invalid_totp_code"
        )

    plain_codes, hashed_codes = generate_recovery_codes()
    user.mfa_enabled = True
    user.mfa_recovery_codes = hashed_codes
    user.save(update_fields=["mfa_enabled", "mfa_recovery_codes", "updated_at"])

    auth_session = getattr(request, "auth_session", None)
    if auth_session is not None:
        auth_session.mfa_verified_at = timezone.now()
        auth_session.save(update_fields=["mfa_verified_at", "updated_at"])

    record_audit_log(
        action=AuditAction.MFA_ENROLLED,
        resource_type="user",
        resource_id=user.pk,
        user=user,
        request=request,
    )
    return plain_codes


def verify_user_mfa(*, user: User, code: str, request: Any = None) -> bool:
    """تأیید کد TOTP یا کد بازیابی و تازه کردن مهر زمان Step-Up MFA روی نشست جاری."""
    if not user.mfa_enabled or not user.mfa_secret_encrypted:
        raise ValidationDomainError(
            "تأیید دومرحله‌ای برای این حساب فعال نشده است.", code="mfa_not_enabled"
        )

    clean_code = str(code or "").strip().upper()
    secret = decrypt_pii(user.mfa_secret_encrypted)
    verified = False

    if verify_totp_code(secret, clean_code):
        verified = True
    else:
        code_hash = hashlib.sha256(clean_code.encode("utf-8")).hexdigest()
        stored_hashes = list(user.mfa_recovery_codes or [])
        if code_hash in stored_hashes:
            stored_hashes.remove(code_hash)
            user.mfa_recovery_codes = stored_hashes
            user.save(update_fields=["mfa_recovery_codes", "updated_at"])
            verified = True

    if not verified:
        raise ValidationDomainError(
            "کد دومرحله‌ای یا کد بازیابی نامعتبر است.", code="invalid_mfa_code"
        )

    auth_session = getattr(request, "auth_session", None)
    if auth_session is not None:
        auth_session.mfa_verified_at = timezone.now()
        auth_session.save(update_fields=["mfa_verified_at", "updated_at"])

    record_audit_log(
        action=AuditAction.MFA_VERIFIED,
        resource_type="user",
        resource_id=user.pk,
        user=user,
        request=request,
    )
    return True


def record_risk_signal(
    *,
    user: User | None,
    signal_type: Any,
    severity: Any = RiskSeverity.MEDIUM,
    request: Any = None,
    details: dict[str, Any] | None = None,
) -> AuthRiskSignal:
    """ثبت سیگنال ریسک امنیتی/ضدتقلب برای بررسی توسط ادمین."""
    ip_addr = get_client_ip(request) if request is not None else ""
    return AuthRiskSignal.objects.create(
        user=user,
        signal_type=signal_type,
        severity=severity,
        ip_address=ip_addr,
        details=details or {},
    )


def review_risk_signal(
    *,
    signal: AuthRiskSignal,
    reviewer: User,
    review_note: str = "",
    request: Any = None,
) -> AuthRiskSignal:
    """ثبت بررسی ادمین روی یک سیگنال ریسک امنیتی."""
    signal.is_reviewed = True
    signal.reviewed_by = reviewer
    signal.reviewed_at = timezone.now()
    signal.review_note = str(review_note or "")[:300]
    signal.save(
        update_fields=["is_reviewed", "reviewed_by", "reviewed_at", "review_note", "updated_at"]
    )
    record_audit_log(
        action=AuditAction.RISK_REVIEWED,
        resource_type="risk_signal",
        resource_id=signal.pk,
        user=reviewer,
        request=request,
        reason=signal.review_note,
    )
    return signal


def update_own_profile(
    *,
    user: User,
    data: dict[str, Any],
    request: Any = None,
) -> User:
    """به‌روزرسانی پروفایل توسط خود کاربر (فقط تا پیش از شروع آزمون مجاز است)."""
    from apps.exam.models import ExamAttempt

    if ExamAttempt.objects.filter(user=user).exists():
        raise ConflictDomainError(
            "پس از شروع یا پایان آزمون، امکان تغییر اطلاعات هویتی و مسجد انتخابی وجود ندارد.",
            code="profile_locked_after_exam",
        )

    changes: dict[str, Any] = {}
    if "first_name" in data and str(data["first_name"]).strip():
        new_fn = str(data["first_name"]).strip()
        if new_fn != user.first_name:
            changes["first_name"] = {"old": user.first_name, "new": new_fn}
            user.first_name = new_fn

    if "last_name" in data and str(data["last_name"]).strip():
        new_ln = str(data["last_name"]).strip()
        if new_ln != user.last_name:
            changes["last_name"] = {"old": user.last_name, "new": new_ln}
            user.last_name = new_ln

    if data.get("birth_date"):
        parsed_bd = parse_and_validate_birth_date(data["birth_date"])
        if parsed_bd != user.birth_date:
            changes["birth_date"] = {"old": str(user.birth_date), "new": str(parsed_bd)}
            user.birth_date = parsed_bd

    if "mosque_id" in data and data["mosque_id"] is not None:
        new_mosque = get_active_mosque_by_id(int(data["mosque_id"]))
        old_mosque_id = user.mosque_id
        if old_mosque_id != new_mosque.id:
            changes["mosque_id"] = {"old": old_mosque_id, "new": new_mosque.id}
            user.mosque = new_mosque
            if old_mosque_id:
                Mosque.all_objects.filter(
                    pk=old_mosque_id,
                    registered_count__gt=0,
                ).update(registered_count=models.F("registered_count") - 1)
            increment_mosque_registered_count(new_mosque.id)

    user.save()
    if changes:
        record_audit_log(
            action=AuditAction.USER_UPDATED,
            resource_type="user",
            resource_id=user.pk,
            user=user,
            request=request,
            changes=changes,
        )
    return user


def update_user_by_admin(
    *,
    target_user: User,
    data: dict[str, Any],
    request: Any = None,
) -> User:
    """ویرایش اطلاعات کاربر توسط مدیر کل سامانه."""
    changes: dict[str, Any] = {}
    for field in ("first_name", "last_name", "is_active", "is_phone_verified"):
        if field in data:
            new_val = data[field]
            old_val = getattr(target_user, field)
            if new_val != old_val:
                changes[field] = {"old": old_val, "new": new_val}
                setattr(target_user, field, new_val)

    if data.get("birth_date"):
        parsed_bd = parse_and_validate_birth_date(data["birth_date"])
        if parsed_bd != target_user.birth_date:
            changes["birth_date"] = {"old": str(target_user.birth_date), "new": str(parsed_bd)}
            target_user.birth_date = parsed_bd

    if "mosque_id" in data and data["mosque_id"] is not None:
        new_mosque = get_active_mosque_by_id(int(data["mosque_id"]))
        if target_user.mosque_id != new_mosque.id:
            changes["mosque_id"] = {"old": target_user.mosque_id, "new": new_mosque.id}
            target_user.mosque = new_mosque

    if "role" in data and data["role"] in dict(UserRole.choices):
        new_role = data["role"]
        if target_user.role != new_role:
            changes["role"] = {"old": target_user.role, "new": new_role}
            target_user.role = new_role
            target_user.is_staff = new_role in {UserRole.ADMIN, UserRole.OPERATOR}

    target_user.save()
    record_audit_log(
        action=AuditAction.USER_UPDATED,
        resource_type="user",
        resource_id=target_user.pk,
        request=request,
        changes=changes,
    )
    return target_user

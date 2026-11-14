"""ویوهای ثبت‌نام شرکت‌کنندگان، احراز هویت دوحالته، مدیریت نشست‌ها، MFA و ادمین کاربران."""

from __future__ import annotations

from typing import Any

from django.conf import settings
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from apps.core.exceptions import UnauthorizedDomainError
from apps.core.pagination import StandardResultsSetPagination
from apps.core.responses import created_response, deleted_response, success_response

from .choices import OTPPurpose
from .constants import ACCESS_COOKIE_NAME, REFRESH_COOKIE_NAME
from .deprecation import add_deprecation_headers, log_legacy_endpoint_usage
from .models import User
from .permissions import IsAdminUser
from .selectors import (
    get_admin_users_queryset,
    get_risk_signal_by_id,
    get_risk_signals_queryset,
    get_user_by_id_or_404,
    get_user_exam_eligibility,
    list_user_active_sessions,
)
from .serializers import (
    AdminUserUpdateInputSerializer,
    AuthRiskSignalSerializer,
    AuthSessionOutputSerializer,
    MFACodeInputSerializer,
    OTPRequestInputSerializer,
    OTPVerifyInputSerializer,
    ParticipantRegistrationInputSerializer,
    PasswordLoginInputSerializer,
    ProfileUpdateInputSerializer,
    RiskReviewInputSerializer,
    TokenRefreshInputSerializer,
    UserProfileOutputSerializer,
)
from .services import (
    confirm_user_totp,
    create_and_send_otp,
    login_with_password,
    register_or_enter_participant,
    review_risk_signal,
    revoke_all_sessions_for_user,
    revoke_session_by_id,
    setup_user_totp,
    update_own_profile,
    update_user_by_admin,
    validate_and_touch_session,
    verify_otp_and_issue_session,
    verify_user_mfa,
)
from .throttles import (
    OTPRequestRateThrottle,
    OTPVerifyRateThrottle,
    PasswordLoginRateThrottle,
    RegistrationRateThrottle,
    SessionManagementRateThrottle,
)


def _attach_auth_cookies(response: Response, tokens: dict[str, Any] | None) -> Response:
    """تنظیم کوکی‌های امن `HttpOnly` برای توکن‌های Access و Refresh در کنار پاسخ JSON."""
    if not tokens:
        return response
    secure = not getattr(settings, "DEBUG", False)
    samesite = "Lax"
    response.set_cookie(
        ACCESS_COOKIE_NAME,
        tokens["access"],
        max_age=3600 * 12,
        httponly=True,
        secure=secure,
        samesite=samesite,
    )
    response.set_cookie(
        REFRESH_COOKIE_NAME,
        tokens["refresh"],
        max_age=3600 * 24 * 7,
        httponly=True,
        secure=secure,
        samesite=samesite,
    )
    return response


def _clear_auth_cookies(response: Response) -> Response:
    """پاک کردن کوکی‌های احراز هویت هنگام خروج."""
    response.delete_cookie(ACCESS_COOKIE_NAME)
    response.delete_cookie(REFRESH_COOKIE_NAME)
    return response


class ParticipantRegisterAPIView(APIView):
    """ثبت‌نام یکپارچهٔ شرکت‌کننده، انتخاب مسجد و فعال‌سازی دکمهٔ ورود به آزمون."""

    permission_classes = [AllowAny]
    authentication_classes: list[Any] = []
    throttle_classes = [RegistrationRateThrottle]

    @extend_schema(
        tags=["Authentication & Identity"],
        summary="ثبت‌نام شرکت‌کننده، انتخاب مسجد و آماده‌سازی ورود به آزمون",
        request=ParticipantRegistrationInputSerializer,
        responses={201: UserProfileOutputSerializer, 200: UserProfileOutputSerializer},
    )
    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """ثبت اطلاعات هویتی، بررسی یکتایی کدملی و شماره تماس، و صدور نشست یا ارسال OTP."""
        del args, kwargs
        serializer = ParticipantRegistrationInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        v = serializer.validated_data

        result = register_or_enter_participant(
            first_name=v["first_name"],
            last_name=v["last_name"],
            national_id=v["national_id"],
            phone_number=v["phone_number"],
            birth_date=v["birth_date"],
            mosque_id=v["mosque_id"],
            request=request,
        )
        user: User = result["user"]
        eligibility = get_user_exam_eligibility(user)

        if result["otp_required"]:
            return success_response(
                data={
                    "is_new_user": result["created_new"],
                    "otp_required": True,
                    "otp": result["otp"],
                    "user": UserProfileOutputSerializer(user).data,
                    "exam_eligibility": eligibility,
                },
                status_code=status.HTTP_202_ACCEPTED,
                code="otp_sent",
                message="کد تایید پیامکی به شماره همراه شما ارسال شد.",
            )

        tokens = result["tokens"]
        token_payload = {
            "access": tokens["access"],
            "refresh": tokens["refresh"],
            "session_uid": tokens["session_uid"],
        }
        http_status = status.HTTP_201_CREATED if result["created_new"] else status.HTTP_200_OK
        resp = success_response(
            data={
                "is_new_user": result["created_new"],
                "otp_required": False,
                "tokens": token_payload,
                "access": tokens["access"],
                "refresh": tokens["refresh"],
                "session_uid": tokens["session_uid"],
                "user": UserProfileOutputSerializer(user).data,
                "exam_eligibility": eligibility,
            },
            status_code=http_status,
            code="registered" if result["created_new"] else "authenticated",
            message="ثبت‌نام شما با موفقیت انجام شد. اکنون می‌توانید وارد آزمون شوید.",
        )
        return _attach_auth_cookies(resp, tokens)


class LegacySignupAliasAPIView(ParticipantRegisterAPIView):
    """مسیر جایگزین قدیمی (`/signup/`) همراه با هدرهای استاندارد RFC 8594 Deprecation."""

    @extend_schema(
        tags=["Authentication & Identity"],
        summary="مسیر قدیمی ثبت‌نام (Deprecated — از /api/v1/auth/register/ استفاده کنید)",
        deprecated=True,
        request=ParticipantRegistrationInputSerializer,
        responses={201: UserProfileOutputSerializer},
    )
    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """هدایت به ثبت‌نام اصلی همراه با درج هدرهای Deprecation و Link."""
        log_legacy_endpoint_usage(
            endpoint_name="auth.legacy_signup",
            request=request,
            successor="/api/v1/auth/register/",
        )
        response = super().post(request, *args, **kwargs)
        return add_deprecation_headers(response, successor="/api/v1/auth/register/")


class OTPRequestAPIView(APIView):
    """درخواست ارسال کد یک‌بارمصرف پیامکی (OTP) برای ورود یا تایید شماره تماس."""

    permission_classes = [AllowAny]
    authentication_classes: list[Any] = []
    throttle_classes = [OTPRequestRateThrottle]

    @extend_schema(
        tags=["Authentication & Identity"],
        summary="درخواست ارسال کد تایید پیامکی (OTP)",
        request=OTPRequestInputSerializer,
        responses={202: {"type": "object"}},
    )
    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """ایجاد چالش OTP و ارسال پیامک (با پاسخ یکسان جهت جلوگیری از شمارش کاربران)."""
        del args, kwargs
        serializer = OTPRequestInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        otp_info = create_and_send_otp(
            phone_number=serializer.validated_data["phone_number"],
            purpose=OTPPurpose.LOGIN,
            request=request,
        )
        if "debug_code" in otp_info and "debug_otp_code" not in otp_info:
            otp_info["debug_otp_code"] = otp_info["debug_code"]
        return success_response(
            data=otp_info,
            status_code=status.HTTP_202_ACCEPTED,
            code="otp_sent",
            message="در صورت ثبت بودن شماره، کد تایید پیامکی ارسال شد.",
        )


class OTPVerifyAPIView(APIView):
    """تأیید کد یک‌بارمصرف پیامکی (OTP) و دریافت توکن ورود به آزمون."""

    permission_classes = [AllowAny]
    authentication_classes: list[Any] = []
    throttle_classes = [OTPVerifyRateThrottle]

    @extend_schema(
        tags=["Authentication & Identity"],
        summary="تأیید کد OTP و دریافت توکن نشست",
        request=OTPVerifyInputSerializer,
        responses={200: UserProfileOutputSerializer},
    )
    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """بررسی کد OTP و صدور توکن‌های JWT مقید به نشست."""
        del args, kwargs
        serializer = OTPVerifyInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        res = verify_otp_and_issue_session(
            phone_number=serializer.validated_data["phone_number"],
            code=serializer.validated_data["code"],
            request=request,
        )
        user: User = res["user"]
        tokens = res["tokens"]
        token_payload = {
            "access": tokens["access"],
            "refresh": tokens["refresh"],
            "session_uid": tokens["session_uid"],
        }
        eligibility = get_user_exam_eligibility(user)
        resp = success_response(
            data={
                "tokens": token_payload,
                "access": tokens["access"],
                "refresh": tokens["refresh"],
                "session_uid": tokens["session_uid"],
                "user": UserProfileOutputSerializer(user).data,
                "exam_eligibility": eligibility,
            },
            message="احراز هویت با موفقیت انجام شد.",
        )
        return _attach_auth_cookies(resp, tokens)


class PasswordLoginAPIView(APIView):
    """ورود مدیران و اپراتورهای سامانه با شماره تماس/کدملی و رمز عبور."""

    permission_classes = [AllowAny]
    authentication_classes: list[Any] = []
    throttle_classes = [PasswordLoginRateThrottle]

    @extend_schema(
        tags=["Authentication & Identity"],
        summary="ورود با رمز عبور (مخصوص ادمین و اپراتورها)",
        request=PasswordLoginInputSerializer,
        responses={200: UserProfileOutputSerializer},
    )
    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """احراز هویت با رمز عبور و صدور نشست."""
        del args, kwargs
        serializer = PasswordLoginInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        res = login_with_password(
            identifier=serializer.validated_data["identifier"],
            password=serializer.validated_data["password"],
            request=request,
        )
        user: User = res["user"]
        tokens = res["tokens"]
        resp = success_response(
            data={
                "access": tokens["access"],
                "refresh": tokens["refresh"],
                "session_uid": tokens["session_uid"],
                "user": UserProfileOutputSerializer(user).data,
            },
            message="ورود با موفقیت انجام شد.",
        )
        return _attach_auth_cookies(resp, tokens)


class TokenRefreshAPIView(APIView):
    """تمدید توکن Access با بررسی زنده بودن نشست (`AuthSession`)."""

    permission_classes = [AllowAny]
    authentication_classes: list[Any] = []

    @extend_schema(
        tags=["Authentication & Identity"],
        summary="تمدید توکن دسترسی (Refresh Token)",
        request=TokenRefreshInputSerializer,
        responses={200: {"type": "object"}},
    )
    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """صدور توکن Access جدید پس از بررسی عدم ابطال نشست."""
        del args, kwargs
        serializer = TokenRefreshInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        raw_refresh = (
            serializer.validated_data.get("refresh")
            or request.COOKIES.get(REFRESH_COOKIE_NAME)
            or ""
        ).strip()
        if not raw_refresh:
            raise UnauthorizedDomainError(
                "توکن Refresh ارسال نشده است.", code="missing_refresh_token"
            )

        try:
            refresh = RefreshToken(raw_refresh)  # type: ignore[arg-type]
            user_id = refresh.get("user_id")
            user = get_user_by_id_or_404(int(user_id))
            session = validate_and_touch_session(user=user, token_claims=refresh)
            if session is None:
                raise UnauthorizedDomainError(
                    "نشست مرتبط با این توکن باطل شده است.",
                    code="session_revoked",
                )
            access = refresh.access_token
            access["sid"] = session.sid_str
            access["role"] = user.role
            new_tokens = {
                "access": str(access),
                "refresh": str(refresh),
                "session_uid": session.sid_str,
            }
            resp = success_response(
                data=new_tokens,
                message="توکن دسترسی با موفقیت تمدید شد.",
            )
            return _attach_auth_cookies(resp, new_tokens)
        except TokenError as exc:
            raise UnauthorizedDomainError(
                "توکن Refresh نامعتبر یا منقضی شده است.",
                code="invalid_refresh_token",
            ) from exc


class LogoutAPIView(APIView):
    """خروج از حساب کاربری و ابطال آنی نشست جاری."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Authentication & Identity"],
        summary="خروج از حساب و ابطال نشست جاری",
        request=None,
        responses={200: {"type": "object"}},
    )
    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """ابطال نشست جاری و حذف کوکی‌های احراز هویت."""
        del args, kwargs
        auth_session = getattr(request, "auth_session", None)
        if auth_session is not None:
            revoke_session_by_id(
                user=request.user,  # type: ignore[arg-type]
                session_id=auth_session.id,
                reason="user_logout",
                request=request,
            )
        resp = success_response(data=None, message="با موفقیت از حساب کاربری خارج شدید.")
        return _clear_auth_cookies(resp)


class LogoutAllAPIView(APIView):
    """خروج از تمامی دستگاه‌ها و ابطال تمام نشست‌های فعال کاربر."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Authentication & Identity"],
        summary="خروج از تمامی دستگاه‌ها (Revoke All Sessions)",
        request=None,
        responses={200: {"type": "object"}},
    )
    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """ابطال تمام نشست‌های فعال کاربر."""
        del args, kwargs
        revoked_count = revoke_all_sessions_for_user(
            target_user=request.user,  # type: ignore[arg-type]
            reason="user_logout_all",
            request=request,
        )
        resp = success_response(
            data={"revoked_sessions_count": revoked_count},
            message="تمامی نشست‌های فعال شما با موفقیت بسته شدند.",
        )
        return _clear_auth_cookies(resp)


class MeProfileAPIView(APIView):
    """مشاهده و ویرایش اطلاعات پروفایل کاربر جاری به همراه وضعیت آمادگی ورود به آزمون."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Authentication & Identity"],
        summary="دریافت اطلاعات هویتی، مسجد انتخابی و وضعیت دکمهٔ ورود به آزمون",
        responses={200: UserProfileOutputSerializer},
    )
    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """برگرداندن پروفایل کاربر و وضعیت دقیق `exam_eligibility`."""
        del args, kwargs
        user: User = request.user  # type: ignore[assignment]
        eligibility = get_user_exam_eligibility(user)
        return success_response(
            data={
                "user": UserProfileOutputSerializer(user).data,
                "exam_eligibility": eligibility,
            },
            message="اطلاعات کاربری و وضعیت آزمون با موفقیت دریافت شد.",
        )

    @extend_schema(
        tags=["Authentication & Identity"],
        summary="ویرایش اطلاعات پروفایل و مسجد (فقط تا پیش از شروع آزمون)",
        request=ProfileUpdateInputSerializer,
        responses={200: UserProfileOutputSerializer},
    )
    def patch(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """به‌روزرسانی نام، تاریخ تولد یا مسجد انتخابی قبل از شروع آزمون."""
        del args, kwargs
        serializer = ProfileUpdateInputSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        updated = update_own_profile(
            user=request.user,  # type: ignore[arg-type]
            data=serializer.validated_data,
            request=request,
        )
        eligibility = get_user_exam_eligibility(updated)
        return success_response(
            data={
                "user": UserProfileOutputSerializer(updated).data,
                "exam_eligibility": eligibility,
            },
            message="اطلاعات پروفایل با موفقیت به‌روزرسانی شد.",
        )


class UserSessionListAPIView(APIView):
    """مشاهدهٔ فهرست نشست‌ها و دستگاه‌های فعال کاربر جاری."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [SessionManagementRateThrottle]

    @extend_schema(
        tags=["Authentication & Identity"],
        summary="فهرست نشست‌ها و دستگاه‌های فعال من",
        responses={200: AuthSessionOutputSerializer(many=True)},
    )
    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """برگرداندن لیست نشست‌های فعال کاربر با مشخص کردن نشست فعلی."""
        del args, kwargs
        auth_session = getattr(request, "auth_session", None)
        current_sid = auth_session.sid_str if auth_session is not None else ""
        sessions = list_user_active_sessions(request.user, current_sid=current_sid)  # type: ignore[arg-type]
        return success_response(
            data=sessions,
            message="فهرست نشست‌های فعال با موفقیت دریافت شد.",
        )


class UserSessionRevokeAPIView(APIView):
    """ابطال یک نشست خاص توسط خود کاربر."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [SessionManagementRateThrottle]

    @extend_schema(
        tags=["Authentication & Identity"],
        summary="لغو یک نشست فعال با شناسه",
        request=None,
        responses={200: AuthSessionOutputSerializer},
    )
    def post(
        self,
        request: Request,
        session_id: str,
        *args: Any,
        **kwargs: Any,
    ) -> Response:
        """ابطال نشست مشخص‌شده."""
        del args, kwargs
        session = revoke_session_by_id(
            user=request.user,  # type: ignore[arg-type]
            session_id=session_id,
            reason="user_manual_revoke",
            request=request,
        )
        return success_response(
            data=AuthSessionOutputSerializer(session).data,
            message="نشست مورد نظر با موفقیت لغو شد.",
        )


class MFATOTPSetupAPIView(APIView):
    """شروع راه‌اندازی تأیید دومرحله‌ای (TOTP) برای حساب کاربری/مدیریتی."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Authentication & Identity"],
        summary="تولید راز و لینک QR برای راه‌اندازی TOTP دومرحله‌ای",
        request=None,
        responses={200: {"type": "object"}},
    )
    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """تولید راز Base32 و URI استاندارد Authenticator."""
        del args, kwargs
        info = setup_user_totp(user=request.user)  # type: ignore[arg-type]
        return created_response(
            data=info,
            message="راز تأیید دومرحله‌ای تولید شد. کد ۶ رقمی اپلیکیشن را برای فعال‌سازی ارسال کنید.",
        )


class MFATOTPConfirmAPIView(APIView):
    """تأیید و فعال‌سازی نهایی TOTP دومرحله‌ای و دریافت کدهای بازیابی."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Authentication & Identity"],
        summary="تأیید کد TOTP و دریافت کدهای بازیابی یک‌بارمصرف",
        request=MFACodeInputSerializer,
        responses={200: {"type": "object"}},
    )
    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """فعال‌سازی MFA پس از بررسی کد ۶ رقمی."""
        del args, kwargs
        serializer = MFACodeInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        recovery_codes = confirm_user_totp(
            user=request.user,  # type: ignore[arg-type]
            code=serializer.validated_data["code"],
            request=request,
        )
        return success_response(
            data={"mfa_enabled": True, "recovery_codes": recovery_codes},
            message="تأیید دومرحله‌ای با موفقیت فعال شد. کدهای بازیابی را در جای امن نگهداری کنید.",
        )


class MFAVerifyStepUpAPIView(APIView):
    """تأیید دومرحله‌ای تازه (Step-Up MFA) برای عملیات‌های حساس مدیریتی."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Authentication & Identity"],
        summary="تأیید کد TOTP/بازیابی برای عملیات حساس (Step-Up MFA)",
        request=MFACodeInputSerializer,
        responses={200: {"type": "object"}},
    )
    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """بررسی کد MFA و ثبت زمان تأیید تازه روی نشست جاری."""
        del args, kwargs
        serializer = MFACodeInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        verify_user_mfa(
            user=request.user,  # type: ignore[arg-type]
            code=serializer.validated_data["code"],
            request=request,
        )
        return success_response(
            data={"mfa_verified": True},
            message="تأیید دومرحله‌ای با موفقیت انجام شد.",
        )


class AdminUserListAPIView(APIView):
    """فهرست صفحه‌بندی‌شدهٔ تمام کاربران سامانه مخصوص ادمین."""

    permission_classes = [IsAdminUser]

    @extend_schema(
        tags=["Admin - Users & Security"],
        summary="فهرست کاربران و شرکت‌کنندگان (مخصوص ادمین)",
        responses={200: UserProfileOutputSerializer(many=True)},
    )
    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """واکشی کاربران با فیلتر نقش، مسجد و جست‌وجو."""
        del args, kwargs
        qs = get_admin_users_queryset(params=request.query_params.dict())
        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        serializer = UserProfileOutputSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


class AdminUserDetailAPIView(APIView):
    """مشاهده، ویرایش و غیرفعال‌سازی یک کاربر توسط ادمین."""

    permission_classes = [IsAdminUser]

    @extend_schema(
        tags=["Admin - Users & Security"],
        summary="مشاهدهٔ اطلاعات کامل یک کاربر توسط ادمین",
        responses={200: UserProfileOutputSerializer},
    )
    def get(self, request: Request, user_id: int, *args: Any, **kwargs: Any) -> Response:
        """دریافت اطلاعات کاربر و وضعیت آزمون او."""
        del request, args, kwargs
        target = get_user_by_id_or_404(user_id)
        return success_response(
            data={
                "user": UserProfileOutputSerializer(target).data,
                "exam_eligibility": get_user_exam_eligibility(target),
            },
            message="اطلاعات کاربر دریافت شد.",
        )

    @extend_schema(
        tags=["Admin - Users & Security"],
        summary="ویرایش اطلاعات یا نقش کاربر توسط ادمین",
        request=AdminUserUpdateInputSerializer,
        responses={200: UserProfileOutputSerializer},
    )
    def patch(self, request: Request, user_id: int, *args: Any, **kwargs: Any) -> Response:
        """به‌روزرسانی اطلاعات کاربر توسط ادمین."""
        del args, kwargs
        target = get_user_by_id_or_404(user_id)
        serializer = AdminUserUpdateInputSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        updated = update_user_by_admin(
            target_user=target,
            data=serializer.validated_data,
            request=request,
        )
        return success_response(
            data=UserProfileOutputSerializer(updated).data,
            message="اطلاعات کاربر با موفقیت به‌روزرسانی شد.",
        )

    @extend_schema(
        tags=["Admin - Users & Security"],
        summary="غیرفعال‌سازی حساب کاربر و ابطال نشست‌های او توسط ادمین",
        responses={200: {"type": "object"}},
    )
    def delete(self, request: Request, user_id: int, *args: Any, **kwargs: Any) -> Response:
        """غیرفعال‌سازی کاربر و بستن تمام نشست‌های فعال او."""
        del args, kwargs
        target = get_user_by_id_or_404(user_id)
        update_user_by_admin(
            target_user=target,
            data={"is_active": False},
            request=request,
        )
        revoke_all_sessions_for_user(
            target_user=target,
            actor=request.user,  # type: ignore[arg-type]
            reason="admin_deactivated_user",
            request=request,
        )
        return deleted_response(message="حساب کاربر غیرفعال شد و نشست‌های او بسته شدند.")


class AdminUserSessionsAPIView(APIView):
    """مشاهدهٔ نشست‌های فعال یک کاربر مشخص توسط ادمین."""

    permission_classes = [IsAdminUser]

    @extend_schema(
        tags=["Admin - Users & Security"],
        summary="مشاهدهٔ نشست‌های فعال یک کاربر توسط ادمین",
        responses={200: AuthSessionOutputSerializer(many=True)},
    )
    def get(self, request: Request, user_id: int, *args: Any, **kwargs: Any) -> Response:
        """برگرداندن لیست نشست‌های فعال کاربر هدف."""
        del request, args, kwargs
        target = get_user_by_id_or_404(user_id)
        sessions = list_user_active_sessions(target)
        return success_response(
            data=sessions,
            message="نشست‌های فعال کاربر دریافت شد.",
        )


class AdminUserRevokeAllSessionsAPIView(APIView):
    """ابطال تمامی نشست‌های فعال یک کاربر توسط ادمین."""

    permission_classes = [IsAdminUser]

    @extend_schema(
        tags=["Admin - Users & Security"],
        summary="ابطال تمامی نشست‌های یک کاربر توسط ادمین",
        request=None,
        responses={200: {"type": "object"}},
    )
    def post(self, request: Request, user_id: int, *args: Any, **kwargs: Any) -> Response:
        """بستن فوری تمام نشست‌های فعال کاربر هدف."""
        del args, kwargs
        target = get_user_by_id_or_404(user_id)
        count = revoke_all_sessions_for_user(
            target_user=target,
            actor=request.user,  # type: ignore[arg-type]
            reason="admin_revoke_all",
            request=request,
        )
        return success_response(
            data={"revoked_sessions_count": count},
            message="تمامی نشست‌های فعال کاربر با موفقیت باطل شدند.",
        )


class AdminRiskSignalListAPIView(APIView):
    """فهرست سیگنال‌های ریسک امنیتی و ناهنجاری‌های آزمون برای بررسی ادمین."""

    permission_classes = [IsAdminUser]

    @extend_schema(
        tags=["Admin - Users & Security"],
        summary="فهرست سیگنال‌های ریسک امنیتی و ضدتقلب",
        responses={200: AuthRiskSignalSerializer(many=True)},
    )
    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """واکشی سیگنال‌های ریسک."""
        del args, kwargs
        is_reviewed = str(request.query_params.get("is_reviewed", ""))
        severity = str(request.query_params.get("severity", ""))
        qs = get_risk_signals_queryset(is_reviewed=is_reviewed, severity=severity)
        return success_response(
            data=AuthRiskSignalSerializer(qs[:200], many=True).data,
            message="فهرست سیگنال‌های ریسک امنیتی دریافت شد.",
        )


class AdminRiskSignalReviewAPIView(APIView):
    """ثبت بررسی ادمین روی یک سیگنال ریسک امنیتی."""

    permission_classes = [IsAdminUser]

    @extend_schema(
        tags=["Admin - Users & Security"],
        summary="ثبت نتیجهٔ بررسی سیگنال ریسک توسط ادمین",
        request=RiskReviewInputSerializer,
        responses={200: AuthRiskSignalSerializer},
    )
    def post(self, request: Request, signal_id: int, *args: Any, **kwargs: Any) -> Response:
        """علامت‌گذاری سیگنال ریسک به‌عنوان بررسی‌شده."""
        del args, kwargs
        sig = get_risk_signal_by_id(signal_id)
        serializer = RiskReviewInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        updated = review_risk_signal(
            signal=sig,
            reviewer=request.user,  # type: ignore[arg-type]
            review_note=serializer.validated_data.get("review_note", ""),
            request=request,
        )
        return success_response(
            data=AuthRiskSignalSerializer(updated).data,
            message="بررسی سیگنال ریسک با موفقیت ثبت شد.",
        )

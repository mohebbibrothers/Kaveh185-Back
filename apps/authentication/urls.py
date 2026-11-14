"""مسیرهای API احراز هویت، ثبت‌نام، نشست‌ها، MFA و مدیریت کاربران."""

from __future__ import annotations

from django.urls import path

from .views import (
    AdminRiskSignalListAPIView,
    AdminRiskSignalReviewAPIView,
    AdminUserDetailAPIView,
    AdminUserListAPIView,
    AdminUserRevokeAllSessionsAPIView,
    AdminUserSessionsAPIView,
    LegacySignupAliasAPIView,
    LogoutAllAPIView,
    LogoutAPIView,
    MeProfileAPIView,
    MFATOTPConfirmAPIView,
    MFATOTPSetupAPIView,
    MFAVerifyStepUpAPIView,
    OTPRequestAPIView,
    OTPVerifyAPIView,
    ParticipantRegisterAPIView,
    PasswordLoginAPIView,
    TokenRefreshAPIView,
    UserSessionListAPIView,
    UserSessionRevokeAPIView,
)

app_name = "authentication"

urlpatterns = [
    # ثبت‌نام و ورود شرکت‌کنندگان
    path("register/", ParticipantRegisterAPIView.as_view(), name="register"),
    path("signup/", LegacySignupAliasAPIView.as_view(), name="legacy-signup"),
    path("otp/request/", OTPRequestAPIView.as_view(), name="otp-request"),
    path("otp/verify/", OTPVerifyAPIView.as_view(), name="otp-verify"),
    path("login/password/", PasswordLoginAPIView.as_view(), name="login-password"),
    path("token/refresh/", TokenRefreshAPIView.as_view(), name="token-refresh"),
    path("logout/", LogoutAPIView.as_view(), name="logout"),
    path("logout-all/", LogoutAllAPIView.as_view(), name="logout-all"),
    # پروفایل و نشست‌های کاربر جاری
    path("me/", MeProfileAPIView.as_view(), name="me"),
    path("sessions/", UserSessionListAPIView.as_view(), name="sessions"),
    path(
        "sessions/<str:session_id>/revoke/",
        UserSessionRevokeAPIView.as_view(),
        name="session-revoke",
    ),
    # تأیید دومرحله‌ای (TOTP MFA & Step-Up)
    path("mfa/totp/setup/", MFATOTPSetupAPIView.as_view(), name="mfa-totp-setup"),
    path("mfa/totp/confirm/", MFATOTPConfirmAPIView.as_view(), name="mfa-totp-confirm"),
    path("mfa/verify/", MFAVerifyStepUpAPIView.as_view(), name="mfa-verify"),
    # مدیریت کاربران و امنیت توسط ادمین
    path("admin/users/", AdminUserListAPIView.as_view(), name="admin-users"),
    path("admin/users/<int:user_id>/", AdminUserDetailAPIView.as_view(), name="admin-user-detail"),
    path(
        "admin/users/<int:user_id>/sessions/",
        AdminUserSessionsAPIView.as_view(),
        name="admin-user-sessions",
    ),
    path(
        "admin/users/<int:user_id>/sessions/revoke-all/",
        AdminUserRevokeAllSessionsAPIView.as_view(),
        name="admin-user-revoke-sessions",
    ),
    path("admin/risk-signals/", AdminRiskSignalListAPIView.as_view(), name="admin-risk-signals"),
    path(
        "admin/risk-signals/<int:signal_id>/review/",
        AdminRiskSignalReviewAPIView.as_view(),
        name="admin-risk-review",
    ),
]

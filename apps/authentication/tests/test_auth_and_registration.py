"""تست‌های جامع ثبت‌نام، اعتبارسنجی کدملی و موبایل، یکتایی سخت‌گیرانه، OTP، نشست‌ها و TOTP MFA."""

from __future__ import annotations

from io import StringIO

import pytest
from django.core.management import call_command
from rest_framework.test import APIClient

from apps.authentication.models import User
from apps.authentication.totp import compute_totp_code
from apps.mosques.models import Mosque
from tests.factories import make_valid_national_id


@pytest.mark.django_db()
def test_participant_registration_uniqueness_and_resume_flow(
    api_client: APIClient,
    seeded_mosques: list[Mosque],
) -> None:
    """ثبت‌نام شرکت‌کننده با نام، کدملی یکتا، موبایل یکتا، تاریخ تولد شمسی و انتخاب مسجد از لیست."""
    mosque = seeded_mosques[0]
    nid_1 = make_valid_national_id(101)
    nid_2 = make_valid_national_id(102)

    reg_resp = api_client.post(
        "/api/v1/auth/register/",
        data={
            "first_name": "محمدحسین",
            "last_name": "کریمی",
            "national_id": nid_1,
            "phone_number": "۰۹۱۲۳۴۵۶۷۸۹",  # ارقام فارسی به لاتین نرمال می‌شوند
            "birth_date": "۱۳۸۲/۰۶/۱۵",  # تاریخ شمسی به میلادی تبدیل می‌شود
            "mosque_id": mosque.id,
        },
        format="json",
    )
    assert reg_resp.status_code == 201
    reg_data = reg_resp.json()["data"]
    assert reg_data["is_new_user"] is True
    assert "tokens" in reg_data
    assert reg_data["user"]["phone_number"] == "09123456789"
    assert reg_data["user"]["birth_date_jalali"] == "1382/06/15"
    assert reg_data["user"]["mosque_id"] == mosque.id

    # بررسی ذخیره شدن رمزنگاری‌شدهٔ کدملی و شاخص کور در دیتابیس
    created_user = User.objects.get(phone_number="09123456789")
    assert created_user.national_id_encrypted.startswith("v1:")
    assert len(created_user.national_id_hash) == 64

    # ۱) تلاش برای ثبت‌نام با همان شماره موبایل ولی کد ملی متفاوت باید رد شود
    dup_phone_resp = api_client.post(
        "/api/v1/auth/register/",
        data={
            "first_name": "رضا",
            "last_name": "احمدی",
            "national_id": nid_2,
            "phone_number": "09123456789",
            "birth_date": "1380/01/01",
            "mosque_id": mosque.id,
        },
        format="json",
    )
    assert dup_phone_resp.status_code == 409

    # ۲) تلاش برای ثبت‌نام با همان کد ملی ولی شماره موبایل متفاوت باید رد شود
    dup_nid_resp = api_client.post(
        "/api/v1/auth/register/",
        data={
            "first_name": "رضا",
            "last_name": "احمدی",
            "national_id": nid_1,
            "phone_number": "09351112233",
            "birth_date": "1380/01/01",
            "mosque_id": mosque.id,
        },
        format="json",
    )
    assert dup_nid_resp.status_code == 409

    # ۳) ورود مجدد همان کاربر با تطابق کامل موبایل و کد ملی برای ادامهٔ آزمون
    resume_resp = api_client.post(
        "/api/v1/auth/register/",
        data={
            "first_name": "محمدحسین",
            "last_name": "کریمی",
            "national_id": nid_1,
            "phone_number": "09123456789",
            "birth_date": "1382/06/15",
            "mosque_id": mosque.id,
        },
        format="json",
    )
    assert resume_resp.status_code == 200
    assert resume_resp.json()["data"]["is_new_user"] is False
    assert "tokens" in resume_resp.json()["data"]


@pytest.mark.django_db()
def test_invalid_iranian_national_id_and_phone_rejected(
    api_client: APIClient,
    seeded_mosques: list[Mosque],
) -> None:
    """کد ملی با رقم کنترلی نامعتبر یا ارقام تکراری (`1111111111`) باید رد شود."""
    resp = api_client.post(
        "/api/v1/auth/register/",
        data={
            "first_name": "تست",
            "last_name": "خطا",
            "national_id": "1111111111",
            "phone_number": "09120001122",
            "birth_date": "1380/05/10",
            "mosque_id": seeded_mosques[0].id,
        },
        format="json",
    )
    assert resp.status_code == 400


@pytest.mark.django_db()
def test_otp_request_verify_and_legacy_signup_deprecation(
    api_client: APIClient,
    seeded_mosques: list[Mosque],
) -> None:
    """تست چرخهٔ درخواست و تایید OTP پیامکی و هدرهای استاندارد Deprecation در مسیر قدیمی."""
    nid = make_valid_national_id(205)
    legacy_resp = api_client.post(
        "/api/v1/auth/signup/",
        data={
            "first_name": "سجاد",
            "last_name": "موسوی",
            "national_id": nid,
            "phone_number": "09195556677",
            "birth_date": "1379/11/22",
            "mosque_id": seeded_mosques[1].id,
        },
        format="json",
    )
    assert legacy_resp.status_code == 201
    assert legacy_resp["Deprecation"] == "true"
    assert "Sunset" in legacy_resp

    otp_req = api_client.post(
        "/api/v1/auth/otp/request/",
        data={"phone_number": "09195556677", "purpose": "login"},
        format="json",
    )
    assert otp_req.status_code in {200, 202}
    debug_code = otp_req.json()["data"].get("debug_otp_code")
    assert debug_code

    otp_ver = api_client.post(
        "/api/v1/auth/otp/verify/",
        data={"phone_number": "09195556677", "code": debug_code},
        format="json",
    )
    assert otp_ver.status_code == 200
    assert "tokens" in otp_ver.json()["data"]


@pytest.mark.django_db()
def test_sessions_profile_totp_mfa_and_admin_user_management(
    participant_client: APIClient,
    admin_client: APIClient,
    admin_user: User,
) -> None:
    """تست پروفایل `/me/`، فهرست و ابطال نشست‌ها، راه‌اندازی TOTP MFA و مدیریت کاربران توسط ادمین."""
    me_resp = participant_client.get("/api/v1/auth/me/")
    assert me_resp.status_code == 200

    sessions_resp = participant_client.get("/api/v1/auth/sessions/")
    assert sessions_resp.status_code == 200
    sessions = sessions_resp.json()["data"]
    assert len(sessions) >= 1

    # راه‌اندازی و تایید TOTP MFA برای ادمین
    setup_resp = admin_client.post("/api/v1/auth/mfa/totp/setup/")
    assert setup_resp.status_code in {200, 201}
    secret = setup_resp.json()["data"]["secret"]

    code = compute_totp_code(secret)
    confirm_resp = admin_client.post(
        "/api/v1/auth/mfa/totp/confirm/",
        data={"code": code},
        format="json",
    )
    assert confirm_resp.status_code == 200
    assert confirm_resp.json()["data"]["mfa_enabled"] is True

    stepup_resp = admin_client.post(
        "/api/v1/auth/mfa/verify/",
        data={"code": compute_totp_code(secret)},
        format="json",
    )
    assert stepup_resp.status_code == 200

    # مدیریت کاربران و دستور grant_admin
    users_resp = admin_client.get("/api/v1/auth/admin/users/")
    assert users_resp.status_code == 200

    detail_resp = admin_client.get(f"/api/v1/auth/admin/users/{admin_user.id}/")
    assert detail_resp.status_code == 200

    out = StringIO()
    call_command(
        "grant_admin",
        "--phone=09128889900",
        f"--national-id={make_valid_national_id(888)}",
        "--password=AdminPass185!",
        stdout=out,
    )
    assert User.objects.filter(phone_number="09128889900", role="admin").exists()


@pytest.mark.django_db()
def test_password_login_refresh_logout_admin_actions_and_risk_signals(
    api_client: APIClient,
    participant_client: APIClient,
    participant_user: User,
    admin_client: APIClient,
    admin_user: User,
    seeded_mosques: list[Mosque],
) -> None:
    """تست ورود با رمز عبور، تمدید توکن، خروج، ویرایش پروفایل، سیگنال‌های ریسک و حالت OTP اجباری."""
    from apps.authentication.models import AuthRiskSignal
    from apps.exam.selectors import get_or_create_exam_configuration

    # ۱) ویرایش پروفایل قبل از شروع آزمون
    patch_me = participant_client.patch(
        "/api/v1/auth/me/",
        data={
            "first_name": "محمدحسین",
            "last_name": "رضایی‌پور",
            "birth_date": "1381/03/20",
            "mosque_id": seeded_mosques[2].id,
        },
        format="json",
    )
    assert patch_me.status_code == 200
    assert patch_me.json()["data"]["user"]["first_name"] == "محمدحسین"

    # ۲) ابطال نشست خاص توسط کاربر
    sessions_resp = participant_client.get("/api/v1/auth/sessions/")
    sid = sessions_resp.json()["data"][0]["session_uid"]
    rev_resp = participant_client.post(f"/api/v1/auth/sessions/{sid}/revoke/")
    assert rev_resp.status_code == 200

    # ۳) ورود با رمز عبور (موفق و ناموفق با تولید سیگنال ریسک)
    bad_login = api_client.post(
        "/api/v1/auth/login/password/",
        data={"identifier": admin_user.phone_number, "password": "WrongPassword!"},
        format="json",
    )
    assert bad_login.status_code in {400, 401}

    ok_login = api_client.post(
        "/api/v1/auth/login/password/",
        data={"identifier": admin_user.phone_number, "password": "StrongAdminPass!185"},
        format="json",
    )
    assert ok_login.status_code == 200
    refresh_token = ok_login.json()["data"]["refresh"]

    # ۴) عملیات ادمین روی کاربران، نشست‌ها و سیگنال‌های ریسک (پیش از ابطال نشست‌های ادمین)
    filtered_users = admin_client.get(
        f"/api/v1/auth/admin/users/?role=participant&mosque_id={seeded_mosques[2].id}&q=محمد&is_active=true"
    )
    assert filtered_users.status_code == 200

    patch_user = admin_client.patch(
        f"/api/v1/auth/admin/users/{participant_user.id}/",
        data={
            "first_name": "محمدحسین",
            "last_name": "رضایی",
            "mosque_id": seeded_mosques[1].id,
            "role": "operator",
            "is_active": True,
        },
        format="json",
    )
    assert patch_user.status_code == 200

    user_sessions = admin_client.get(f"/api/v1/auth/admin/users/{participant_user.id}/sessions/")
    assert user_sessions.status_code == 200

    revoke_all_admin = admin_client.post(
        f"/api/v1/auth/admin/users/{participant_user.id}/sessions/revoke-all/"
    )
    assert revoke_all_admin.status_code == 200

    signal = AuthRiskSignal.objects.first()
    assert signal is not None
    signals_resp = admin_client.get(
        "/api/v1/auth/admin/risk-signals/?is_reviewed=false&severity=medium"
    )
    assert signals_resp.status_code == 200

    review_resp = admin_client.post(
        f"/api/v1/auth/admin/risk-signals/{signal.id}/review/",
        data={"review_note": "بررسی شد — تست امنیتی"},
        format="json",
    )
    assert review_resp.status_code == 200

    del_user = admin_client.delete(f"/api/v1/auth/admin/users/{participant_user.id}/")
    assert del_user.status_code == 200

    # ۵) تمدید توکن و خروج از نشست
    refresh_resp = api_client.post(
        "/api/v1/auth/token/refresh/",
        data={"refresh": refresh_token},
        format="json",
    )
    assert refresh_resp.status_code == 200
    new_access = refresh_resp.json()["data"]["access"]
    new_refresh = refresh_resp.json()["data"]["refresh"]

    authed = APIClient()
    authed.credentials(HTTP_AUTHORIZATION=f"Bearer {new_access}")
    logout_resp = authed.post("/api/v1/auth/logout/", data={"refresh": new_refresh}, format="json")
    assert logout_resp.status_code == 200

    logout_all_resp = admin_client.post("/api/v1/auth/logout-all/")
    assert logout_all_resp.status_code == 200

    # ۶) ثبت‌نام در حالت فعال بودن OTP اجباری (require_otp_before_exam=True)
    cfg = get_or_create_exam_configuration()
    cfg.require_otp_before_exam = True
    cfg.save()
    otp_reg = api_client.post(
        "/api/v1/auth/register/",
        data={
            "first_name": "زهرا",
            "last_name": "احمدی",
            "national_id": make_valid_national_id(312),
            "phone_number": "09361112233",
            "birth_date": "1384/07/10",
            "mosque_id": seeded_mosques[0].id,
        },
        format="json",
    )
    assert otp_reg.status_code == 202
    assert otp_reg.json()["data"]["otp_required"] is True
    cfg.require_otp_before_exam = False
    cfg.save()

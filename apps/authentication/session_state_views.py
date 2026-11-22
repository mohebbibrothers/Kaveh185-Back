"""مسیرِ «وضعیتِ من» — نشستِ خودترمیم (`POST /auth/session/state/`).

══ چرا این مسیر لازم شد؟ ══════════════════════════════════════════════════
گزارشِ میدانی: «بعد از ثبت‌نام از صفحهٔ آزمون به خانه می‌روم، دوباره
«ثبت‌نام و شرکت» را می‌زنم و به‌جای شروعِ آزمون، فرمِ خالی می‌آید.»

سه علتِ فنی پشتِ این یک جمله، و هر سه در نهایت به یک چیز می‌رسند: **رابط
نمی‌داند این دستگاه چه کسی است**. تا وقتی این را نداند، هر تصمیمی حدس است.

  ۱) توکنِ دسترسی منقضی می‌شود (پیش‌فرض ۶ ساعت، ممکن است کمتر باشد). تا
     امروز هیچ‌کس توکن را تمدید نمی‌کرد: `refresh` در `localStorage` ذخیره
     می‌شد و هیچ‌جا مصرف نمی‌شد. نتیجه: نشستِ «ظاهراً موجود» که هر درخواستش
     ۴۰۱ می‌گیرد ⇒ رابط فکر می‌کند کاربر تازه است ⇒ فرمِ خالی.
  ۲) کاربر نشستش را روی دستگاهِ دیگر ساخته و این دستگاه نمی‌داند.
  ۳) `localStorage` پاک شده (حالتِ ناشناس، پاک‌کردنِ دادهٔ سایت، مرورگرِ دیگر).

این مسیر هر سه را با یک قرارداد حل می‌کند و پاسخش **همیشه** شکلِ واحدی
دارد تا رابط بتواند یک‌بار برای همیشه تصمیم بگیرد:

    {
      "state": "no_session" | "session" | "revived" | "completed" | "incomplete",
      "session": {access, refresh, session_uid, expires_in} | null,
      "user": {...} | null,
      "exam_eligibility": {...} | null,
      "next": {"path": "/exam" | "/register" | "/receipt?code=…", "label": "…"},
      "reason": "...",            # توضیحِ کوتاهِ فارسی برای نمایش
      "phone_hint": "0990***41"   # فقط وقتی نشست نیست و شماره‌ای داریم
    }

── چرا POST و نه GET؟ ─────────────────────────────────────────────────────
چون در حالتِ `revived` توکنِ تازه صادر می‌شود و پاسخ نباید در کشِ HTTP یا
لاگِ پروکسی بیفتد. ضمناً بدنه‌اش می‌تواند `phone_number` بگیرد تا حالتِ
«دستگاهِ تازه، پرونده با شماره پیدا شود» هم بدونِ فرمِ ثبت‌نام حل شود.

── امنیت (همان سیاستِ ثبت‌شده) ────────────────────────────────────────────
با `BALE_OTP_MANDATORY=False` (جریانِ فعالِ فعلی) هر کسی که شماره + کدملیِ
یک ثبت‌نام‌شده را بداند می‌تواند نشست بگیرد؛ این مسیر دقیقاً همان سطح را
دارد و **بیشتر** نه: با شماره تنها و کد ملی نمی‌شود، نشستِ تازه ساخت —
برای آن باید کد ملی هم بیاید. با روشن‌شدنِ OTP، این مسیر خودکار به
`verification_required` می‌افتد و هیچ نشستی نمی‌دهد.
"""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.views import APIView

from apps.audit_logs.choices import AuditAction
from apps.audit_logs.services import record_audit_log
from apps.authentication.choices import UserRole
from apps.authentication.models import User
from apps.authentication.selectors import get_user_exam_eligibility
from apps.authentication.serializers import (
    SessionStateInputSerializer,
    UserProfileOutputSerializer,
)
from apps.authentication.services import (
    issue_tokens_and_session,
    validate_and_touch_session,
)
from apps.core.crypto import mask_phone
from apps.core.exceptions import ForbiddenDomainError
from apps.core.responses import success_response


class SessionStateAPIView(APIView):
    """«من چه کسی هستم و قدمِ بعدی‌ام چیست؟» — با تمدیدِ خودکارِ نشست."""

    permission_classes = [AllowAny]
    authentication_classes: list[Any] = []

    @extend_schema(
        tags=["Authentication & Identity"],
        summary="وضعیت نشست دستگاه (خودترمیم با Refresh Token)",
        request=SessionStateInputSerializer,
        responses={200: UserProfileOutputSerializer},
    )
    def post(self, request: Request, *args: Any, **kwargs: Any) -> Any:
        """تشخیصِ وضعیت + صدورِ توکنِ تازه در صورت امکان + پیشنهادِ قدمِ بعد."""
        del args, kwargs
        data = request.data if isinstance(request.data, dict) else {}
        access = str(data.get("access") or request.COOKIES.get("access_token") or "").strip()
        refresh = str(data.get("refresh") or request.COOKIES.get("refresh_token") or "").strip()
        phone = str(data.get("phone_number") or "").strip()
        national_id = str(data.get("national_id") or "").strip()

        # ── ۱) نشستِ زنده: سریع‌ترین و مطمئن‌ترین حالت ────────────────────
        user = self._user_from_access(access)
        if user is not None:
            return self._respond(request, user, state="session", tokens=None)

        # ── ۲) توکنِ دسترسی منقضی ⇒ با refresh زنده‌اش کن ─────────────────
        revived = self._revive(request, refresh)
        if revived is not None:
            user, tokens = revived
            return self._respond(request, user, state="revived", tokens=tokens)

        # ── ۳) دستگاهِ تازه: اگر شماره + کد ملی بیاید، پرونده را وصل کن ───
        claimed = self._claim(request, phone, national_id)
        if claimed is not None:
            return claimed

        # ── ۴) هیچ‌چیز: صادقانه بگو «نشست نیست» ──────────────────────────
        return success_response(
            data={
                "state": "no_session",
                "session": None,
                "user": None,
                "exam_eligibility": None,
                "next": {"path": "/register", "label": "ثبت‌نام و شرکت در آزمون"},
                "reason": "روی این دستگاه نشستی نیست؛ با شمارهٔ همراه پرونده‌تان را پیدا کنید.",
                "phone_hint": "",
            },
            message="نشستی یافت نشد.",
        )

    # ── کمکی‌ها ────────────────────────────────────────────────────────────
    @staticmethod
    def _user_from_access(access: str) -> User | None:
        """کاربر از توکنِ دسترسی — بدونِ خطا: هر مشکلی یعنی «نشست نیست»."""
        if not access:
            return None
        try:
            from rest_framework_simplejwt.tokens import AccessToken

            token = AccessToken(access)  # type: ignore[arg-type]
            user = User.objects.filter(pk=int(token.get("user_id")), is_active=True).first()
            if user is None:
                return None
            session = validate_and_touch_session(user=user, token_claims=token)
            return user if session is not None else None
        except Exception:
            return None

    @staticmethod
    def _revive(request: Request, refresh: str) -> tuple[User, dict[str, Any]] | None:
        """صدورِ توکنِ دسترسیِ تازه از refresh، فقط اگر نشست روی سرور زنده باشد.

        ⚠️ `refresh` باید دقیقاً مثلِ `/auth/token/refresh/` سنجیده شود:
        امضای معتبر، نوعِ درست، **و** `AuthSession` باطل‌نشده. اگر نشست با
        `logout-all` یا توسطِ ادمین باطل شده باشد، این‌جا هم زنده نمی‌شود.
        """
        if not refresh:
            return None
        try:
            from rest_framework_simplejwt.exceptions import TokenError
            from rest_framework_simplejwt.tokens import RefreshToken

            token = RefreshToken(refresh)  # type: ignore[arg-type]
            user = User.objects.filter(pk=int(token.get("user_id")), is_active=True).first()
            if user is None:
                return None
            session = validate_and_touch_session(user=user, token_claims=token)
            if session is None:
                return None
            access = token.access_token
            access["sid"] = session.sid_str
            access["role"] = user.role
            tokens = {
                "access": str(access),
                "refresh": str(token),
                "session_uid": session.sid_str,
            }
            record_audit_log(
                action=AuditAction.USER_LOGGED_IN,
                resource_type="user",
                resource_id=user.pk,
                user=user,
                request=request,
                extra_data={"mode": "session_state_refresh"},
            )
            return user, tokens
        except TokenError:
            return None
        except Exception:
            return None

    def _claim(self, request: Request, phone: str, national_id: str) -> Any | None:
        """وصل‌کردنِ دستگاهِ تازه به پروندهٔ موجود با شماره + کد ملی.

        چرا کد ملی هم لازم است؟ چون شمارهٔ تنها قابلِ حدس است. با هر دو،
        ریسکِ تصاحبِ حساب همان سطحِ فرمِ ثبت‌نام است (که همان اطلاعات را
        می‌خواهد و همان نشست را می‌دهد) — نه بیشتر.
        """
        if not phone or not national_id:
            return None
        try:
            from apps.authentication.validators import (
                normalize_and_validate_national_id,
                normalize_and_validate_phone,
            )

            norm_phone = normalize_and_validate_phone(phone)
            norm_nid = normalize_and_validate_national_id(national_id)
        except Exception:
            return None

        user = User.objects.filter(
            phone_number=norm_phone, national_id=norm_nid, is_active=True
        ).first()
        if user is None:
            return None

        eligibility = get_user_exam_eligibility(user)
        if user.role != UserRole.PARTICIPANT:
            # ادمین‌ها از این مسیر وارد نمی‌شوند؛ مسیرشان رمز است.
            return None
        if bool(getattr(settings, "BALE_OTP_MANDATORY", False)) and not user.is_phone_verified:
            raise ForbiddenDomainError(
                "برای ادامه باید شمارهٔ خود را با کدِ یک‌بارمصرف تأیید کنید.",
                code="verification_required",
                errors={"phone_number": ["تأییدِ شماره لازم است."]},
            )
        if eligibility.get("has_completed_exam"):
            return success_response(
                data={
                    "state": "completed",
                    "session": None,
                    "user": UserProfileOutputSerializer(user).data,
                    "exam_eligibility": eligibility,
                    "next": {
                        "path": f"/receipt?code={eligibility.get('tracking_code') or ''}",
                        "label": "دیدنِ کارنامه",
                    },
                    "reason": "شما قبلاً در آزمون شرکت کرده‌اید؛ کارنامه‌تان آماده است.",
                    "phone_hint": mask_phone(user.phone_number),
                },
                message="کارنامهٔ شما آماده است.",
            )

        tokens = issue_tokens_and_session(user=user, request=request)
        record_audit_log(
            action=AuditAction.USER_LOGGED_IN,
            resource_type="user",
            resource_id=user.pk,
            user=user,
            request=request,
            extra_data={"mode": "session_state_claim"},
        )
        return self._respond(request, user, state="session", tokens=tokens)

    def _respond(
        self,
        request: Request,
        user: User,
        *,
        state: str,
        tokens: dict[str, Any] | None,
    ) -> Any:
        """پاسخِ یکنواخت: کی هستم + قدمِ بعدی کجاست."""
        del request
        eligibility = get_user_exam_eligibility(user)
        next_step = _next_step(user=user, eligibility=eligibility)
        # وضعیتِ نهایی از **قدمِ بعدی** مشتق می‌شود، نه از توکن: کاربری که
        # آزمونش تمام شده ممکن است نشستِ زنده هم داشته باشد، ولی معنای
        # وضعیتش «کارنامه» است. یک منبعِ حقیقت، دو نمایش.
        finished = next_step["path"].startswith("/receipt")
        payload: dict[str, Any] = {
            "state": "completed" if finished else state,
            "session": None,
            "user": UserProfileOutputSerializer(user).data,
            "exam_eligibility": eligibility,
            "next": next_step,
            "reason": next_step["reason"],
            "phone_hint": mask_phone(user.phone_number),
        }
        if tokens is not None:
            payload["session"] = {
                "access": tokens["access"],
                "refresh": tokens["refresh"],
                "session_uid": tokens["session_uid"],
                "expires_in": int(
                    getattr(settings, "SIMPLE_JWT", {})
                    .get("ACCESS_TOKEN_LIFETIME", timezone.timedelta(hours=6))
                    .total_seconds()
                ),
            }
        return success_response(data=payload, message=next_step["reason"])


def _next_step(*, user: User, eligibility: dict[str, Any]) -> dict[str, str]:
    """تصمیمِ واحدِ «کاربر بعدش کجا برود؟» — تنها منبعِ حقیقت برای همهٔ CTAها.

    قواعد، به ترتیبِ اولویت:
      ۱) کارنامه دارد            ⇒ `/receipt?code=…`
      ۲) پروفایل ناقص            ⇒ `/register`
      ۳) آزمونِ باز               ⇒ `/exam` (ادامه)
      ۴) پنجره باز و آماده       ⇒ `/exam` (شروعِ آگاهانه در بریفینگ)
      ۵) پنجره بسته/نیامده       ⇒ `/exam` ولی با پیامِ دلیل (بریفینگ می‌گوید)
    """
    code = eligibility.get("tracking_code")
    # مدیر/اپراتور: مسیرش آزمون نیست؛ دکمه‌اش باید پنل باشد، نه فرمِ ثبت‌نام
    # (که برای مدیر بی‌معنا و گیج‌کننده است).
    if user.role != UserRole.PARTICIPANT:
        return {
            "path": "/login",
            "label": "ورود به پنل",
            "reason": "این حساب مدیریتی است؛ از صفحهٔ ورود وارد پنل شوید.",
        }
    if eligibility.get("has_completed_exam"):
        return {
            "path": f"/receipt?code={code or ''}",
            "label": "دیدنِ کارنامه",
            "reason": "شما قبلاً در آزمون شرکت کرده‌اید؛ کارنامه‌تان آماده است.",
        }
    if not eligibility.get("profile_ready", True):
        return {
            "path": "/register",
            "label": "تکمیلِ ثبت‌نام",
            "reason": "پروندهٔ شما کامل نیست؛ چند فیلد باقی مانده است.",
        }
    if eligibility.get("has_in_progress_exam"):
        return {
            "path": "/exam",
            "label": "ادامهٔ آزمون",
            "reason": "آزمونِ شما باز است؛ زمان روی سرور می‌گذرد.",
        }
    if eligibility.get("can_enter_exam"):
        return {
            "path": "/exam",
            "label": "ورود به آزمون",
            "reason": "پروندهٔ شما آماده است؛ آزمون را از صفحهٔ بعد شروع کنید.",
        }
    return {
        "path": "/exam",
        "label": "مشاهدهٔ وضعیتِ آزمون",
        "reason": str(eligibility.get("reason_message") or "وضعیتِ آزمون را ببینید."),
    }

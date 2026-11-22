"""ورودِ بازگشتی: «من قبلاً ثبت‌نام کرده‌ام».

══ چرا این فایل وجود دارد؟ ═══════════════════════════════════════════════
شکایتِ واقعی: «کاربری ثبت‌نام می‌کند ولی دکمهٔ ورود به آزمون را نمی‌زند؛ بار
بعد که «ثبت‌نام و شرکت» را می‌زند، دوباره فرمِ خالی می‌بیند و باید همه‌چیز را
از نو بزند.»

فرمِ ثبت‌نام هیچ راهی برای «ادامه دادن» نداشت: با هر بار پر کردن، یا کاربرِ
تازه ساخته می‌شد، یا (اگر شماره/کدملی یکی بود) پیامِ ۴۰۹ می‌آمد. راه‌حلِ
درست دو تکه است:

  ۱) **یافتن (این فایل)**: با شمارهٔ همراه، پروندهٔ موجود را پیدا می‌کنیم و
     یک **نشستِ تازه** می‌دهیم تا کاربر مستقیم به ایستگاهِ «پرونده آماده است»
     برود — بی‌آنکه چیزی دوباره وارد کند.
  ۲) **پرکردنِ خودکارِ فرم** در فرانت: به‌محضِ وارد کردنِ شماره (یا کدملی)،
     فرم نام/تاریخ/مسجدِ او را پر می‌کند و پیامِ «خوش آمدید» می‌دهد.

⚠️ نکتهٔ امنیتیِ صریح: این مسیر **فقط** زمانی معنا دارد که سیاستِ فعلی
«ورود بدونِ کد» باشد (`BALE_OTP_MANDATORY=False`). اگر تأییدِ شماره روشن
باشد، دانستنِ یک شماره نباید نشست بدهد — پس همان‌جا ۴۰۳ برمی‌گردانیم و
کاربر را به مسیرِ کد هدایت می‌کنیم. این محافظ، آیندهٔ روشن‌کردنِ سیاست را
امن نگه می‌دارد.
"""

from __future__ import annotations

from typing import Any

from django.conf import settings
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit_logs.choices import AuditAction
from apps.audit_logs.services import record_audit_log
from apps.core.exceptions import ForbiddenDomainError
from apps.core.responses import success_response

from .choices import UserRole
from .models import User
from .selectors import get_user_exam_eligibility
from .serializers import UserProfileOutputSerializer
from .services import issue_tokens_and_session
from .throttles import RegistrationRateThrottle
from .validators import normalize_and_validate_phone


class ParticipantLookupInputSerializer(serializers.Serializer):
    """ورودیِ یافتنِ پرونده: فقط شمارهٔ همراه.

    شماره به‌صورتِ رشته می‌آید (ارقامِ فارسی هم پذیرفته می‌شود) و همان
    `normalize_and_validate_phone` آن را استاندارد می‌کند؛ پس اعتبارسنجیِ
    این‌جا عمداً سبک است تا پیامِ خطا یکی باشد.
    """

    phone_number = serializers.CharField(max_length=20, help_text="شمارهٔ همراه ثبت‌شده")


class ParticipantLookupAPIView(APIView):
    """یافتنِ پروندهٔ یک شرکت‌کننده با شمارهٔ همراه و صدورِ نشستِ تازه.

    پاسخ همیشه یک شکل دارد: `found` (bool) به‌همراهِ `state` که دقیقاً می‌گوید
    کاربر در کدام وضعیت است تا فرانت متنِ درست را نشان دهد:

    | state | معنی | کاری که فرانت می‌کند |
    |---|---|---|
    | `not_found` | شماره‌ای در سامانه نیست | فقط فرم را باز نگه می‌دارد |
    | `session_ready` | پرونده هست و آزمونش تمام نشده | مستقیم به «پرونده آماده است» |
    | `exam_completed` | آزمونش را داده | به کارنامه با کدِ رهگیری |
    | `verification_required` | سیاستِ کد روشن است | به گامِ کد |
    """

    permission_classes = [AllowAny]
    authentication_classes: list[Any] = []
    throttle_classes = [RegistrationRateThrottle]

    @extend_schema(
        tags=["Authentication & Identity"],
        summary="یافتنِ پروندهٔ شرکت‌کننده با شمارهٔ همراه (ورودِ بازگشتی بدونِ فرمِ تازه)",
        # صریح به یک serializer ارجاع می‌دهیم؛ `--fail-on-warn` اسکیما تولید
        # را با هر هشدار می‌شکند و «شیءِ آزاد» برای فرانت قرارداد نیست.
        request=ParticipantLookupInputSerializer,
        responses={200: UserProfileOutputSerializer},
    )
    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """اگر پرونده هست، نشستِ تازه صادر می‌شود؛ وگرنه پاسخِ صریحِ `not_found`.

        ⚠️ این مسیر عمداً یک «کشفِ اطلاعات» کوچک دارد: با دانستنِ یک شماره
        می‌شود فهمید آن شماره در سامانه ثبت‌نام کرده یا نه، و نامِ کوچکِ صاحبش
        را دید. این هزینهٔ آگاهانهٔ سیاستِ «ورود بدونِ کد» است؛ با روشن‌کردنِ
        `BALE_OTP_MANDATORY` خودکار بسته می‌شود.
        """
        del args, kwargs
        raw_phone = str((request.data or {}).get("phone_number", "") or "")
        try:
            phone = normalize_and_validate_phone(raw_phone)
        except Exception:
            return success_response(
                data={"found": False, "state": "not_found"},
                message="شمارهٔ همراه معتبر نیست.",
                status_code=status.HTTP_200_OK,
            )

        user = (
            User.objects.filter(phone_number=phone, is_active=True, role=UserRole.PARTICIPANT)
            .select_related("mosque")
            .first()
        )
        if user is None:
            return success_response(
                data={"found": False, "state": "not_found"},
                message="برای این شماره پرونده‌ای نیست؛ ثبت‌نامِ تازه بسازید.",
            )

        mandatory = bool(getattr(settings, "BALE_OTP_MANDATORY", False))
        if mandatory and not user.is_phone_verified:
            # سیاستِ کد روشن است ⇒ دانستنِ شماره نباید نشست بدهد.
            raise ForbiddenDomainError(
                "برای ادامه، باید شمارهٔ خود را با کدِ یک‌بارمصرف تأیید کنید.",
                code="verification_required",
                errors={"phone_number": ["تأییدِ شماره لازم است."]},
            )

        eligibility = get_user_exam_eligibility(user)
        if eligibility.get("has_completed_exam"):
            # آزمونش را داده ⇒ نشستِ تازه لازم نیست؛ فقط کارنامه را نشان بده.
            return success_response(
                data={
                    "found": True,
                    "state": "exam_completed",
                    "tracking_code": eligibility.get("tracking_code"),
                    "user": UserProfileOutputSerializer(user).data,
                    "exam_eligibility": eligibility,
                },
                message="شما قبلاً در آزمون شرکت کرده‌اید؛ کارنامه‌تان آماده است.",
            )

        tokens = issue_tokens_and_session(user=user, request=request)
        record_audit_log(
            action=AuditAction.USER_LOGGED_IN,
            resource_type="user",
            resource_id=user.pk,
            user=user,
            request=request,
            extra_data={"mode": "lookup_resume", "created_new": False},
        )
        return success_response(
            data={
                "found": True,
                "state": "session_ready",
                "access": tokens["access"],
                "refresh": tokens["refresh"],
                "session_uid": tokens["session_uid"],
                "is_phone_verified": user.is_phone_verified,
                "user": UserProfileOutputSerializer(user).data,
                "exam_eligibility": eligibility,
            },
            message="پروندهٔ شما پیدا شد. می‌توانید آزمون را شروع کنید.",
        )

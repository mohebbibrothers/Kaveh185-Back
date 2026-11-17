"""نمای خواندن کتاب مسابقه — عمومی (مطالعه) و کنترل‌شده (دانلود فایل).

چرا فایل را مستقیم از `MEDIA_URL` نمی‌دهیم؟
─────────────────────────────────────────────
اگر پوشهٔ media را آزاد سرو کنیم، هر کسی که نام فایل را حدس بزند نسخهٔ
منتشرنشده را می‌گیرد. این‌جا فایل از یک نمای کنترل‌شده رد می‌شود که:

  • فقط کتاب `is_published=True` را می‌دهد؛
  • پاسخ را با `Content-Disposition: inline` می‌فرستد تا PDF در مرورگر
    باز شود (تجربهٔ مطالعه، نه دانلود اجباری) — با دکمهٔ دانلود اختیاری؛
  • `Cache-Control` کوتاه می‌گذارد تا تغییر فایل بلافاصله دیده شود؛
  • `X-Robots-Tag: noindex` می‌گذارد تا نسخه‌های قدیمی در گوگل ایندکس
    نشوند؛
  • فایل‌های EPUB را با `application/epub+zip` می‌فرستد.

── چرا `X-Frame-Options: SAMEORIGIN` صریحاً روی فایل کتاب گذاشته می‌شود؟
─────────────────────────────────────────────────────────────────────────────
صفحهٔ «مطالعهٔ کتاب» فایل را در یک `<iframe>` نشان می‌دهد. سندِ HTML سایت
`frame-ancestors 'none'` دارد، ولی آن سیاست **وارثِ iframe نیست** — یعنی
محدودیتِ فریم برای خودِ سایت اعمال می‌شود، نه برای فایلِ PDF. تا امروز
`X-Frame-Options: DENY` سراسری (روی همین پاسخ) جلوی نمایش را می‌گرفت و
کاربر در کادرِ مطالعه فقط «صفحه سفید» می‌دید. `SAMEORIGIN` همان امنیت را
می‌دهد (هیچ دامنهٔ بیگانه‌ای نمی‌تواند کتاب را قاب کند) و مسیرِ مطالعه را باز
می‌کند. عمداً از `django.views.decorators.clickjacking.xframe_options_sameorigin`
استفاده نمی‌کنیم تا وابستگی به ترتیبِ میان‌افزارها نداشته باشیم.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from django.http import FileResponse, Http404, HttpRequest
from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.responses import success_response

from .models import BookFile
from .serializers import PublicBookSerializer

OPINIONATED_MIME = {
    "pdf": "application/pdf",
    "epub": "application/epub+zip",
}


def _published_book(slug: str | None = None) -> BookFile:
    """آخرین کتاب منتشرشده (یا کتاب با slug مشخص) یا ۴۰۴ صادقانه."""
    queryset = BookFile.objects.filter(is_published=True, is_active=True)
    if slug:
        return get_object_or_404(queryset, slug=slug)
    book = queryset.order_by("-updated_at", "-id").first()
    if book is None:
        raise Http404("کتابی منتشر نشده است.")
    return book


class PublicBookMetaAPIView(APIView):
    """متادیتای کتاب منتشرشده برای صفحهٔ مطالعه و صفحهٔ اول."""

    permission_classes = [AllowAny]
    authentication_classes: list[Any] = []

    @extend_schema(
        tags=["Book"],
        summary="متادیتای کتاب مسابقه (اگر ادمین منتشر کرده باشد)",
        responses={200: PublicBookSerializer, 404: None},
    )
    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """اگر کتابی منتشر نشده باشد، ۴۰۴ با پیام روشن برمی‌گردد.

        چرا ۴۰۴ و نه یک شیء خالی؟ چون فرانت باید بتواند «هیچ کتابی نیست»
        را از «کتاب هست ولی بارگیری نشد» تفکیک کند و پوستهٔ صادقانه نشان
        دهد. یک پاسخ ۲۰۰ با `null` این تفکیک را از بین می‌برد.
        """
        del request, args, kwargs
        book = _published_book()
        return success_response(
            data=PublicBookSerializer(book, context={"request": None}).data,
            message="متادیتای کتاب دریافت شد.",
        )


class PublicBookFileView(APIView):
    """ارسال فایل کتاب منتشرشده به مرورگر کاربر."""

    permission_classes = [AllowAny]
    authentication_classes: list[Any] = []

    @extend_schema(
        tags=["Book"],
        summary="دریافت فایل کتاب (PDF/EPUB) برای مطالعه",
        responses={(200, "application/pdf"): OpenApiTypes.BINARY},
    )
    def get(self, request: Request, *args: Any, **kwargs: Any) -> FileResponse:
        """جریان فایل کتاب با سرآیندهای امن."""
        del args
        slug = str(kwargs.get("slug") or "") or None
        book = _published_book(slug)
        if not book.file:
            raise Http404("فایل این کتاب موجود نیست.")
        try:
            handle = book.file.open("rb")
        except FileNotFoundError as exc:
            raise Http404("فایل کتاب روی سرور پیدا نشد.") from exc

        ext = book.extension or "pdf"
        response = FileResponse(
            handle, content_type=OPINIONATED_MIME.get(ext, "application/octet-stream")
        )
        quoted = Path(book.file.name or "book").name
        response["Content-Disposition"] = f'inline; filename="{quoted}"'
        response["Cache-Control"] = "public, max-age=300"
        response["X-Robots-Tag"] = "noindex"
        # خوانندهٔ درون‌صفحه‌ای (iframe) روی همین دامنه مجاز است؛ بیگانه نه.
        response["X-Frame-Options"] = "SAMEORIGIN"
        response["Content-Security-Policy"] = "frame-ancestors 'self'"
        return response


class BookViewCountAPIView(APIView):
    """ثبت یک بازدید مطالعه — سبک و بی‌اثر در تکرار.

    چرا POST و نه افزایش در GET متادیتا؟ چون پیش‌بارگذاری لینک در
    پیام‌رسان‌ها و خزنده‌ها GET می‌زنند و شمارنده را باد می‌کنند. POST فقط
    از سمت خود صفحهٔ مطالعه می‌آید، یعنی کاربر واقعی.
    """

    permission_classes = [AllowAny]
    authentication_classes: list[Any] = []

    @extend_schema(
        tags=["Book"],
        summary="ثبت بازدید مطالعهٔ کتاب",
        request=None,
        responses={
            200: inline_serializer("BookViewCount", {"view_count": serializers.IntegerField()})
        },
    )
    def post(self, request: Request, slug: str, *args: Any, **kwargs: Any) -> Response:
        """یک واحد به شمارندهٔ بازدید اضافه می‌کند."""
        del request, args, kwargs
        book = _published_book(slug)
        BookFile.objects.filter(pk=book.pk).update(view_count=book.view_count + 1)
        return success_response(data={"view_count": book.view_count + 1}, message="ثبت شد.")


def book_download_view(request: HttpRequest, slug: str) -> FileResponse:
    """همان نمای فایل، برای پیوند مستقیم `/book/<slug>/file/` در HTML."""
    book = _published_book(slug)
    if not book.file:
        raise Http404
    response = FileResponse(
        book.file.open("rb"), content_type=OPINIONATED_MIME.get(book.extension, "application/pdf")
    )
    response["Content-Disposition"] = f'inline; filename="{Path(book.file.name).name}"'
    response["X-Robots-Tag"] = "noindex"
    # همان دلیلِ نمای DRF بالا: مطالعه در iframe همان دامنه باید کار کند.
    response["X-Frame-Options"] = "SAMEORIGIN"
    response["Content-Security-Policy"] = "frame-ancestors 'self'"
    return response

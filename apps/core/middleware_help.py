"""میان‌افزارِ «۴۰۴ِ گویا» — یک ۴۰۴ هرگز نباید معما باشد.

## مشکلی که واقعاً خوردیم

کاربر آدرسِ `/secure-kaveh185-admin/participant-ranking/` را باز کرد و دید
«این صفحه یافت نشد». آن ۴۰۴ سه علتِ ممکن داشت و از **بیرون هیچ‌کدام قابلِ
تشخیص نبود**:

۱) کدِ تازه روی سرور نبود (نسخهٔ قدیمی مانده بود)؛
۲) کد بود، ولی مسیر در جدولِ URLها نبود؛
۳) مسیر بود، ولی `ADMIN_URL_PATH` عوض شده بود (مثلاً `/panel/`).

عیب‌یابیِ این حالت چند ساعت شد. حالا یک ۴۰۴ زیرِ پیشوندِ پنل، **خودش**
می‌گوید کدام‌یک است: به‌جای صفحهٔ مبهم، یک صفحهٔ ۴۰۴ با زمینهٔ روشن که می‌گوید
«این کد این مسیر را ندارد» یا «آدرسِ پنل این نصب X است» و دستورِ
`manage.py check_ranking_page` را نشان می‌دهد.

## نکاتِ امنیتی (مهم)

* این میان‌افزار **لیستِ مسیرها یا نامِ مدل‌ها را افشا نمی‌کند** — فقط می‌گوید
  «این آدرس وجود ندارد» و پیشوندِ پنلِ همین نصب را (که از قبل در همهٔ لینک‌های
  صفحهٔ ورود دیده می‌شود).
* فقط برای درخواست‌های GET/HEAD، فقط برای مسیرهای زیرِ پیشوندِ پنل، و فقط
  وقتی کاربر **staff** است هشدارِ تکمیلی نشان می‌دهد؛ کاربرِ عادی همان صفحهٔ
  ۴۰۴ِ معمولی را می‌گیرد (بی‌آنکه بفهمد پنلی هست یا نه).
* اگر `DEBUG=False` نباشد هیچ کاری نمی‌کند (در توسعه پیامِ استانداردِ جنگو
  گویاتر است).

## چرا middleware و نه `handler404`؟

چون `handler404` نمی‌تواند بداند درخواست زیرِ پیشوندِ پنل بوده یا نه (فقط
`path_info` را دارد، که کافی است) — ولی مهم‌تر: این میان‌افزار مستقل از
ترتیبِ `urlpatterns` است و با هر تغییرِ مسیرها کار می‌کند.
"""

from __future__ import annotations

from collections.abc import Callable

from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect

#: مسیرهایی که «۴۰۴ِ گویا» برایشان فعال است (زیرِ پیشوندِ پنل).
_HINT_PATH = "/participant-ranking/"


def _admin_prefix() -> str:
    """پیشوندِ پنلِ همین نصب، با اسلشِ ابتدا و انتها."""
    raw = str(getattr(settings, "ADMIN_URL_PATH", "secure-kaveh185-admin/")).strip("/")
    return f"/{raw}/"


class AdminRouteHintMiddleware:
    """۴۰۴ِ زیرِ پیشوندِ پنل را به یک راهنمای عیب‌یابیِ کوتاه تبدیل می‌کند."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        """ذخیرهٔ حلقهٔ بعدی (الگوی استاندارد)."""
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        """پاسخ را می‌گیرد و اگر ۴۰۴ِ «قابلِ توضیح» بود، جایگزین می‌کند."""
        response = self.get_response(request)

        if getattr(response, "status_code", None) != 404:
            return response
        if request.method not in ("GET", "HEAD"):
            return response
        if getattr(settings, "DEBUG", False):
            return response

        path = getattr(request, "path_info", "") or ""
        prefix = _admin_prefix()
        if not path.startswith(prefix):
            return response
        # فقط کاربرِ staff توضیحِ تکمیلی می‌گیرد؛ برای بقیه ۴۰۴ ساده می‌ماند.
        user = getattr(request, "user", None)
        if not getattr(user, "is_staff", False):
            return response

        # ── ۱) اگر همان صفحهٔ رتبه‌بندی است ولی با آدرسِ دیگری: ببرش آن‌جا.
        if "participant-ranking" in path:
            real = self._ranking_url()
            if real and real.rstrip("/") != path.rstrip("/"):
                return redirect(real)

        # ── ۲) هر ۴۰۴ِ دیگری زیرِ پنل: صفحهٔ راهنما، نه ۴۰۴ِ برهنه.
        # چرا برای همه و نه فقط مسیرِ رتبه‌بندی؟ چون ۹۰٪ مواقع علت یکی است
        # (کدِ قدیمی یا پیشوندِ عوض‌شده) و ادمین همان ۱۵ ثانیه را هم نباید
        # صرفِ حدس کند. این صفحه هیچ فهرستی از مسیرها را افشا نمی‌کند.
        return self._diagnostic_page(path)

    @staticmethod
    def _ranking_url() -> str | None:
        """نشانیِ واقعیِ صفحهٔ رتبه‌بندی در همین نصب (یا None اگر مسیر نیست)."""
        from django.urls import NoReverseMatch, reverse

        try:
            return str(reverse("participant-ranking"))
        except NoReverseMatch:
            return None

    @staticmethod
    def _diagnostic_page(path: str) -> HttpResponse:
        """صفحهٔ ۴۰۴ِ فارسی که دقیقاً می‌گوید چه چیزی سرِ جایش نیست."""
        prefix = _admin_prefix()
        body = f"""<!doctype html>
<html lang="fa" dir="rtl"><head><meta charset="utf-8">
<title>مسیر پیدا نشد — پنل کاوه ۱۸۵</title>
<style>
 body{{font-family:Tahoma,system-ui,sans-serif;background:#f6f8f7;color:#14342b;
      display:grid;place-items:center;min-height:100vh;margin:0;padding:24px}}
 .card{{background:#fff;border:1px solid #e3e7e4;border-radius:14px;max-width:720px;
       padding:28px 30px;box-shadow:0 2px 10px rgba(0,0,0,.05)}}
 h1{{font-size:19px;margin:0 0 10px}}
 p{{font-size:13px;line-height:2;color:#40544c;margin:8px 0}}
 code{{background:#f1f5f3;padding:2px 6px;border-radius:5px;font-size:12px;direction:ltr;
      display:inline-block}}
 .box{{background:#fffdf5;border:1px solid #f0e3b8;border-radius:9px;padding:12px 14px;margin:14px 0}}
 ul{{font-size:12.5px;line-height:2.1;padding-inline-start:18px;margin:6px 0}}
 a{{color:#1b4332;font-weight:700}}
</style></head><body><div class="card">
<h1>این مسیر در این نصب وجود ندارد</h1>
<p>آدرسی که باز کردید: <code>{path}</code></p>
<div class="box">
<p style="margin:0 0 6px"><b>سه علتِ ممکن، به ترتیبِ احتمال:</b></p>
<ul>
<li>کدِ تازه روی سرور نصب نشده است (سریع‌ترین راهِ بررسی: <code>manage.py check_ranking_page</code>)</li>
<li>آدرسِ پنل در این نصب <code>{prefix}</code> است، نه آدرسی که زده‌اید</li>
<li>مسیر در جدولِ URLها ثبت نشده است</li>
</ul>
</div>
<p>روی سرور این را اجرا کنید تا جوابِ قطعی بگیرید:</p>
<p><code>cd ~/Kaveh185-Back &amp;&amp; python manage.py check_ranking_page</code></p>
<p><a href="{prefix}">بازگشت به صفحهٔ اولِ پنل</a></p>
</div></body></html>"""
        return HttpResponse(body, status=404, content_type="text/html; charset=utf-8")

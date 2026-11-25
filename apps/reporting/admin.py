"""اتصالِ صفحهٔ «رتبه‌بندی شرکت‌کنندگان» به پنل ادمین — بدونِ هیچ monkeypatch.

## چرا این فایل؟

* **کارتِ میان‌بر** در صفحهٔ اولِ ادمین با `admin.site.index_template`. این
  مقدار در **هر درخواست** خوانده می‌شود، پس زمانِ ست شدنش مهم نیست؛ همین‌جا
  (که جنگو خودش ماژول‌های `admin.py` را در autodiscover وارد می‌کند) مطمئن‌ترین
  جاست.

* **مسیرِ خودِ صفحه** این‌جا ثبت *نمی‌شود* — عمداً. مسیر در `config/urls.py`
  صریح فهرست شده است. دلیلش یک باگِ واقعی است که روی هاست ۴۰۴ داد:
  `admin.site.get_urls` فقط **یک بار** (هنگامِ ساختِ `urlpatterns`) صدا زده
  می‌شود؛ اگر مسیر را با patch کردنِ آن تابع در `AppConfig.ready()` اضافه
  می‌کردیم، نتیجه به ترتیبِ بار‌شدنِ اپ‌ها بستگی پیدا می‌کرد. روی محیطِ
  توسعه درست بود، روی هاست نه. یک خطِ صریح در `urls.py` این وابستگی را
  به‌کل حذف می‌کند.
"""

from __future__ import annotations

from typing import Any

from django.contrib import admin
from django.http import HttpRequest

from .ranking_admin import ranking_url

#: قالبِ صفحهٔ اولِ ادمین با کارتِ «رتبه‌بندی» (خودِ قالب، قالبِ جنگو را ارث می‌برد).
admin.site.index_template = "admin/k185_index.html"

_original_each_context = admin.site.each_context


def _each_context_with_ranking(request: HttpRequest) -> dict[str, Any]:
    """همان contextِ استانداردِ ادمین + نشانیِ صفحهٔ رتبه‌بندی.

    ⚠️ `reverse` را **داخلِ تابع** صدا می‌زنیم، نه در زمانِ import. در زمانِ
    import، `ulrs` هنوز کامل بار نشده و ممکن است `NoReverseMatch` بدهد؛
    و اگر هم بدهد، خطا در `autodiscover` کلِ پنل را می‌خواباند. داخلِ تابع،
    جدولِ مسیرها همیشه آماده است.
    """
    context = _original_each_context(request)
    context["participant_ranking_url"] = ranking_url()
    return context


admin.site.each_context = _each_context_with_ranking  # type: ignore[method-assign]

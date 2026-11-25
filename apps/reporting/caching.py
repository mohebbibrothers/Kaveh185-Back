"""رقابتِ رتبه‌ای با «سرریز» — یک لایهٔ کشِ سبک که مسابقه را بدونِ فشار روی دیتابیس زنده نگه می‌دارد.

## چرا این فایل وجود دارد

حینِ آزمون، `ExamAttempt.total_score` و `duration_seconds` مرتب تغییر می‌کنند.
سه جا به این ستون‌ها نگاه می‌کنند:

۱) **شرکت‌کننده** که ۵ ثانیه بعد از هر پاسخ، کارتِ ادامه/رتبهٔ مسجدش را می‌گیرد؛
۲) **پنل ادمین** که فهرستِ رتبه‌بندی را باز می‌کند و اکسل می‌گیرد؛
۳) **صفحهٔ عمومی مساجد** (فقط شمارش، نه رتبهٔ فردی).

اگر هر سه مستقیم به همان کوئریِ سنگینِ رتبه‌بندی وصل شوند، در پیکِ آزمون
دیتابیس زیرِ بارِ مرتب‌سازیِ مکرر می‌نشیند. این ماژول دو کار می‌کند:

* **کش کوتاه (چند ثانیه)** روی «آمار تجمیعی» — اعدادِ داشبورد و رتبهٔ مسجد.
  کوتاه بودنش عمدی است: عددِ کهنه در حینِ آزمون بدتر از هزینهٔ کوئری است،
  ولی چند ثانیه تفاوت برای کاربر دیده نمی‌شود.
* **سرریز به کش قدیمی** اگر دیتابیس خطا داد. این تضمین می‌کند یک کندیِ
  لحظه‌ایِ دیتابیس به **۵۰۰** تبدیل نشود؛ آمارِ ۳۰ ثانیه پیش می‌دهیم و در
  پس‌زمینه دوباره پر می‌کنیم. اصلِ کار: «کاربر هیچ‌وقت صفحهٔ خطا نمی‌بیند».

## چیزهایی که این ماژول عمداً *نمی‌کند*

* شمارش را در حافظه نگه نمی‌دارد (با چند پروسهٔ Passenger بی‌معنا می‌شود).
* رتبهٔ دقیقِ هر فرد را کش نمی‌کند؛ رتبه با هر ثبتِ پاسخ عوض می‌شود و
  کش کردنش کاربر را با عددِ غلط گول می‌زند. آنجا فقط «سقفِ مصرف» داریم.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from django.core.cache import cache

logger = logging.getLogger(__name__)

#: پیشوندِ کلیدها — با `KEY_PREFIX`ِ خودِ کش (`kaveh185`) ترکیب می‌شود.
_PREFIX = "rank:"

#: مدتِ نگه‌داریِ «نسخهٔ سالمِ آخر» برای سرریز. عمداً بلندتر از TTLِ عادی است:
#: اگر دیتابیس چند دقیقه‌ای در دسترس نباشد، آمارِ ۵ دقیقه پیش بهتر از ۵۰۰ است.
_STALE_TTL_SECONDS = 300


def cached_with_stale_fallback[T](
    *,
    key: str,
    ttl_seconds: int,
    producer: Callable[[], T],
    stale_key_suffix: str = "stale",
) -> T:
    """مقدارِ کش‌شده را برمی‌گرداند؛ در خطای تولیدکننده، آخرین نسخهٔ سالم را.

    سه مسیر:
    ۱) کش داغ است ⇒ همان مقدار (بدونِ لمسِ دیتابیس).
    ۲) کش سرد و تولیدکننده موفق ⇒ ذخیره در هر دو کلید (تازه + سرریز).
    ۳) تولیدکننده خطا داد ⇒ نسخهٔ سرریز (تا ۵ دقیقهٔ پیش)؛ اگر آن هم نبود،
       خطا را بالا می‌دهیم تا فراخوان تصمیم بگیرد (معمولاً «صفرِ امن»).

    Args:
        key: کلیدِ کش.
        ttl_seconds: عمرِ نسخهٔ تازه. برای آمارِ زنده ۵ تا ۱۰ ثانیه.
        producer: تابعِ بدون‌آرگومان که مقدار را از دیتابیس می‌سازد.
        stale_key_suffix: پسوندِ کلیدِ سرریز.
    """
    full_key = f"{_PREFIX}{key}"
    stale_key = f"{full_key}:{stale_key_suffix}"

    try:
        hit = cache.get(full_key)
    except Exception:  # pragma: no cover - کشِ خراب نباید درخواست را بکشد
        hit = None
    if hit is not None:
        return hit  # type: ignore[no-any-return]

    try:
        value = producer()
    except Exception:
        logger.exception("rank cache producer failed; serving stale copy if any")
        stale = None
        try:
            stale = cache.get(stale_key)
        except Exception:  # pragma: no cover
            stale = None
        if stale is not None:
            return stale  # type: ignore[no-any-return]
        raise

    try:
        cache.set(full_key, value, timeout=ttl_seconds)
        cache.set(stale_key, value, timeout=_STALE_TTL_SECONDS)
    except Exception:  # pragma: no cover - نوشتنِ کش هرگز نباید خطا بدهد
        logger.warning("rank cache write failed for %s", full_key, exc_info=True)
    return value


def invalidate_rank_caches(*keys: str) -> None:
    """پاک کردنِ کلیدهای تجمیعی پس از رویدادی که آمار را قطعاً عوض می‌کند.

    فقط جایی صدا زده می‌شود که «قطعیت» داریم (مثلاً پایانِ آزمون یا تغییرِ
    پیکربندی)؛ نه در مسیرِ هر پاسخ — آنجا TTLِ کوتاه خودش کار را می‌کند و
    پاک‌کردنِ مداوم کش، همان فشارِ کوئری را برمی‌گرداند.
    """
    for key in keys:
        full_key = f"{_PREFIX}{key}"
        try:
            cache.delete_many([full_key, f"{full_key}:stale"])
        except Exception:  # pragma: no cover
            logger.warning("rank cache invalidation failed for %s", full_key, exc_info=True)


def admin_ranking_cache_scope(params: dict[str, Any]) -> str:
    """کلیدِ کش برای «فهرستِ رتبه‌بندی ادمین» بر اساس همان فیلترهای درخواست.

    ⚠️ چرا پارامترها هم بخشی از کلیدند؟ چون ادمین ممکن است هم‌زمان دو تب با
    دو فیلترِ متفاوت باز کند؛ اگر کلید یکی باشد، فهرستِ یک تب به تبِ دیگر
    نشت می‌کند و ادمین فکر می‌کند فیلتر کار نکرده.
    """
    parts: list[str] = []
    for key in sorted(params):
        value = str(params[key]).strip()
        if value:
            parts.append(f"{key}={value}")
    return "admin-list:" + ("|".join(parts) if parts else "default")

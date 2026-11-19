"""نام‌شناسیِ مسجد و ترتیبِ الفبای فارسی — منبعِ واحدِ رتبه‌بندی در بک‌اند.

چرا این ماژول لازم است؟ رتبه‌بندیِ جدول پیش از این فقط با
`completed_participants_count` و سپس `display_order` انجام می‌شد. مشکل:
«ترتیبِ نمایش» یک تنظیمِ دلخواهِ ادمین است، نه معیارِ رقابت. نتیجه این بود
که دو مسجدِ هم‌امتیاز به‌جای الفبا، بر اساسِ عددِ دلخواهِ `display_order`
مرتب می‌شدند و در دو نصبِ مختلف نتیجهٔ متفاوت می‌داد.

قاعدهٔ رسمی (همان که فرانت‌اند هم پیاده می‌کند):
    ۱) تعداد شرکت‌کنندهٔ کامل — نزولی
    ۲) ترتیب الفبای نامِ مسجد — صعودی (با الفبای صریحِ فارسی)

«آ» عمداً پیش از «ا» می‌آید (قاعدهٔ فرهنگ‌های فارسی) و `localeCompare`ِ ICU
جایگزین نشده چون در دستگاه‌های مختلف ترتیبِ متفاوت می‌دهد — در یک جدولِ
رقابتی، ناپایداری بدترین حالت است.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

# پیشوندهای عمومی/تشریفاتی که «هویتِ» مسجد نیستند.
_GENERIC_PREFIXES: tuple[str, ...] = (
    "مسجد جامع",
    "مسجد اعظم",
    "مسجد بزرگ",
    "مسجد",
    "جامع",
    "مصلی",
    "مصلای",
    "حسینیه",
    "تکیه",
    "زیارتگاه",
    "امامزاده",
    "بقعه",
    "آستان",
)

_HONORIFICS: tuple[str, ...] = ("حضرت", "امام", "آیت‌الله", "آیت الله", "شهید")

_DUAS = re.compile(r"\s+(عج|ع|س|ره|سلام الله علیه|روحی فداه)$")

# الفبای صریحِ فارسی — وزنِ هر حرف = جایگاهش در این رشته.
_FA_ALPHABET = "آاأإءبپتثجچحخدذرزژسشصضطظعغفقکگلمنوهیئؤ"
_FA_WEIGHT: dict[str, int] = {ch: i for i, ch in enumerate(_FA_ALPHABET)}

# اشکالِ عربی/جایگزین که باید یکسان شوند.
_TRANS = str.maketrans(
    {
        "ي": "ی",
        "ى": "ی",
        "ك": "ک",
        "ة": "ه",
        "ۀ": "ه",
        "أ": "ا",
        "إ": "ا",
        "آ": "آ",
    }
)

_PUNCT = re.compile(r"[()\[\]«»\"'’‘“”.,،؛:!?؟…\-–—_/\\]")
_SPACES = re.compile(r"\s+")
_CONTROL = re.compile(r"[\u200c\u200e\u200f\u202a-\u202e]")
_DIACRITICS = re.compile(r"[\u064b-\u0652\u0670]")


def normalize_name(name: str) -> str:
    """نرمال‌سازیِ نمایشی/مقایسه‌ای: ی/ک، اعراب، نیم‌فاصله، نشانه‌ها."""
    text = unicodedata.normalize("NFC", name or "")
    text = _DIACRITICS.sub("", text)
    text = text.translate(_TRANS)
    text = _CONTROL.sub(" ", text)
    text = _PUNCT.sub(" ", text)
    return _SPACES.sub(" ", text).strip()


def mosque_core_name(name: str) -> str:
    """نامِ مسجد بدونِ پیشوندهای عمومی و یک لایه واژهٔ تشریفاتی."""
    core = normalize_name(name)
    if not core:
        return ""

    for _ in range(3):
        stripped = _DUAS.sub("", core).strip()
        if stripped == core:
            break
        core = stripped

    for prefix in _GENERIC_PREFIXES:
        if core == prefix:
            core = ""
            break
        if core.startswith(prefix + " "):
            core = core[len(prefix) + 1 :].strip()
            break

    for word in _HONORIFICS:
        if core.startswith(word + " "):
            core = core[len(word) + 1 :].strip()
            break

    return core or normalize_name(name)


def mosque_initial(name: str) -> str:
    """حرفِ نشان — نخستین حرفِ معنادارِ نامِ هسته (نه «م»ِ همیشگی)."""
    core = mosque_core_name(name)
    for ch in core:
        if ch in _FA_WEIGHT:
            return ch
    return core[:1].upper() or "م"


def fa_sort_key(name: str) -> tuple[Any, ...]:
    """کلیدِ مرتب‌سازیِ الفبای فارسی برای `sorted(..., key=...)`.

    خروجی تاپلِ وزن‌های حرفی است؛ حروفِ لاتین/عدد ته صف می‌روند و در
    نهایت نامِ خام به‌عنوان ضامنِ قطعیت اضافه می‌شود.
    """
    core = mosque_core_name(name).lower()
    weights: list[int] = []
    for ch in core:
        if ch in _FA_WEIGHT:
            weights.append(_FA_WEIGHT[ch])
        elif ch.isdigit():
            weights.append(100)
        elif ch.isascii() and ch.isalpha():
            weights.append(200)
        elif ch.strip():
            weights.append(300)
    return (*weights, core)


def rank_sort_key(item: dict[str, Any]) -> tuple[Any, ...]:
    """کلیدِ رتبه‌بندیِ رسمی: مشارکت نزولی، سپس الفبا صعودی، سپس شناسه."""
    return (
        -int(item.get("completed_participants_count") or 0),
        *fa_sort_key(str(item.get("name") or "")),
        int(item.get("mosque_id") or 0),
    )


def competition_ranks(items: list[dict[str, Any]]) -> list[int]:
    """رتبهٔ رقابتی با **جایگاهِ مشترک** (1224 → ۱، ۲، ۲، ۴ …).

    ── چرا این قاعده و نه «۱۲۲۴»ِ سخت‌گیرانه؟ ───────────────────────────────
    در جدولِ این مسابقه سه جایگاهِ نمایشی داریم: سکوی افتخار (۱ تا ۳)، مدالِ
    برنز برای نفرِ سوم و سطحِ رقابتی (طلایی/نقره‌ای/برنز). قاعدهٔ «۱۲۲۴» این
    سه را می‌شکست و یک تناقضِ دیداری می‌ساخت:

        مسجد الف ۱۴ · مسجد ب ۱۱ · مسجد ج ۱۱ · مسجد د ۸
        با ۱۲۲۴  ⇒  رتبه‌ها: ۱، ۲، ۲، ۴   ← «سوم» و «برنز» هرگز وجود ندارند
        با جایگاه ⇒  رتبه‌ها: ۱، ۲، ۲، ۳   ← دو مسجدِ هم‌امتیاز هر دو سوم‌اند

    قاعدهٔ «جایگاه» همان چیزی است که در جدول‌های ورزشی و المپیک هم به کار
    می‌رود: هر کس بعد از یک گروهِ مساوی بیاید، **جایگاهِ بعدی** را می‌گیرد
    (نه شمارهٔ ردیف). سه خاصیتِ مهم را هم حفظ می‌کند:

      ۱) **بی‌ساختگی:** هیچ مسجدی با امتیازِ کمتر رتبهٔ بهتری نمی‌گیرد؛
         ترتیبِ رتبه‌ها همیشه صعودی و بی‌سوراخ نیست ولی هرگز نزولی نمی‌شود.
      ۲) **انصاف:** دو مسجدِ هم‌امتیاز دقیقاً یک رتبه و یک سطح دارند.
      ۳) **صفرها:** مسجدِ بی‌مشارکت رتبهٔ ۰ می‌گیرد (یعنی «هنوز رتبه‌ای
         ندارد»)، نه رتبهٔ قلابی.
    """
    any_participation = any(int(i.get("completed_participants_count") or 0) > 0 for i in items)
    ranks: list[int] = []
    last_rank = 0
    last_count: int | None = None
    for item in items:
        count = int(item.get("completed_participants_count") or 0)
        if not any_participation or count == 0:
            ranks.append(0)
            last_count = count
            continue
        if count == last_count:
            # هم‌امتیاز با ردیفِ قبل ⇒ همان جایگاه
            ranks.append(last_rank)
            continue
        # جایگاهِ تازه = جایگاهِ قبلی + ۱ (نه شمارهٔ ردیف) — تا «سوم» وجود
        # داشته باشد حتی وقتی دو مسجد رویِ جایگاهِ دوم نشسته‌اند.
        last_rank = last_rank + 1
        last_count = count
        ranks.append(last_rank)
    return ranks

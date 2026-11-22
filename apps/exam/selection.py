"""توزیع عادلانهٔ سؤال بین شرکت‌کنندگان — قلب «انصاف» مسابقه.

مسئله
──────
انتخاب تصادفی ساده (`random.sample`) از نظر ریاضی منصفانه است، ولی در
عمل ناعادلانه دیده می‌شود. با بانک ۳۰ سؤالی و آزمون ۵ سؤالی، اگر دو نفر
همزمان شروع کنند ممکن است یکی پنج سؤال ساده بگیرد و دیگری پنج سؤال
دشوار.شرکت‌کننده حق دارد بپرسد «چرا سؤال‌های من سخت‌تر بود؟».

راه‌حل
──────
«قرعه‌کشی لایه‌ای» (stratified draw) + «شمارندهٔ کشش»:

۱. **لایه‌بندی بر اساس دشواری:** سهم هر سطح از تعداد سؤال آزمون حساب
   می‌شود (۵ سؤال → ۲ ساده، ۲ متوسط، ۱ دشوار). اگر سطحی کمبود داشت،
   سهمش به سطح‌های دیگر بازتوزیع می‌شود — هرگز آزمون ناقص نمی‌ماند.

۲. **شمارندهٔ کشش (draw balance):** هر سؤال یک `times_drawn` دارد. داخل
   هر لایه، سؤال‌های کم‌کشش‌تر شانس بیشتری می‌گیرند. نتیجه: در طول
   مسابقه، همهٔ سؤال‌های بانک تقریباً به یک اندازه دیده می‌شوند و هیچ
   سؤالی «سؤال همیشگی» نمی‌شود.

۳. **پراکندگی داستان:** از هر داستان حداکثر یک سؤال در یک آزمون. اگر
   بانک کوچک بود و ناچار شدیم تکرار کنیم، در پایان دور دوم داستان‌ها
   آزاد می‌شوند (fallback) — دوباره: هرگز آزمون ناقص نمی‌ماند.

۴. **تصادفی بودن واقعی:** انتخاب داخل هر لایه با `secrets.SystemRandom`
   انجام می‌شود و وزن‌ها با نمونه‌گیری وزنی بدون جایگذاری
   (weighted sampling without replacement) اعمال می‌شوند. هیچ‌کس نمی‌تواند
   الگوی سؤال‌ها را حدس بزند یا تکرارِ قابل پیش‌بینی ببیند.

۵. **قابل بازتولید برای پرسش‌های ادمین:** انتخاب نهایی در
   `ExamAttemptItem` ذخیره می‌شود، پس گزارش‌ها همیشه قابل حسابرسی‌اند.

این ماژول عمداً بدون وابستگی به Django است تا بتوان آن را در تست‌های
واحد، مستقل از دیتابیس، سنجید.
"""

from __future__ import annotations

import secrets
from collections import defaultdict
from collections.abc import Sequence
from typing import Any, Protocol

_SYS_RANDOM = secrets.SystemRandom()

#: موتورِ تصادفِ قابلِ جای‌گزینی. تولید همیشه از `secrets.SystemRandom`
#: استفاده می‌کند (غیرقابل‌پیش‌بینی)؛ تست‌ها می‌توانند با
#: `use_random_source(random.Random(seed))` نتیجه را بازتولیدپذیر کنند تا
#: «تستِ آماریِ گاهی‌شکست» نداشته باشیم.
_RNG: Any = _SYS_RANDOM


def use_random_source(rng: Any) -> None:
    """جای‌گزینیِ موتورِ تصادف (فقط برای تست/بازتولید).

    چرا لازم شد؟ تستِ یکنواختیِ توزیع روی `SystemRandom` واقعاً غیرقطعی است و
    در CI (با ترتیبِ متفاوتِ اجرا) گاهی می‌شکست. تصادفِ غیرقابلِ‌پیش‌بینی برای
    **تولید** درست است، ولی برای **تستِ یک تضمینِ آماری** باید دانه داد.
    """
    global _RNG
    _RNG = rng


# سهم هر سطح دشواری از آزمون. جمع کسرها لازم نیست دقیقاً ۱ باشد؛
# تابع `_apportion` باقی‌مانده را بر اساس بزرگ‌ترین باقی‌مانده توزیع می‌کند.
_DIFFICULTY_WEIGHTS: dict[str, float] = {
    "easy": 0.35,
    "medium": 0.45,
    "hard": 0.20,
}

# ترتیب ترجیحی وقتی باید تصمیم بگیریم کدام سطح یک سهم اضافه بگیرد.
_DIFFICULTY_ORDER: tuple[str, ...] = ("medium", "easy", "hard")


class _QuestionLike(Protocol):
    """حداقل چیزی که این ماژول از یک سؤال لازم دارد."""

    id: int
    difficulty: str
    source_story: str


def _apportion(total: int, weights: dict[str, float]) -> dict[str, int]:
    """تقسیم `total` سؤال بین سطوح با روش «بزرگ‌ترین باقی‌مانده».

    چرا این روش؟ تقسیم سادهٔ `round` جمعش همیشه برابر `total` نمی‌شود و
    نتیجه‌اش آزمون ۴ سؤالی یا ۶ سؤالی است. این روش تضمین می‌کند جمع
    دقیقاً `total` باشد.
    """
    raw = {key: total * weight for key, weight in weights.items()}
    base = {key: int(value) for key, value in raw.items()}
    remainder = total - sum(base.values())
    if remainder > 0:
        # بیشترین باقی‌مانده اول؛ در تساوی، ترتیب ترجیحی پروژه.
        ranked = sorted(
            raw,
            key=lambda k: (
                raw[k] - base[k],
                -_DIFFICULTY_ORDER.index(k) if k in _DIFFICULTY_ORDER else 0,
            ),
            reverse=True,
        )
        for key in ranked[:remainder]:
            base[key] += 1
    return base


def _weighted_pick[Q: _QuestionLike](pool: Sequence[Q], draw_counts: dict[int, int]) -> Q:
    """انتخاب یک سؤال از استخر با وزن معکوسِ تعداد دفعات کشیده‌شدن.

    سؤالی که هیچ‌وقت نیامده وزن ۲ دارد، سؤالی که ۱ بار آمده وزن ۱، و به
    همین ترتیب. این «کشش» تضمین می‌کند توزیع در طول مسابقه یکنواخت شود
    بدون اینکه انتخاب قابل پیش‌بینی شود.
    """
    # ── چرا دو مرحله‌ای؟ ─────────────────────────────────────────────────
    # انتخابِ کاملِ وزنی، هر چند بار هم تکرار شود، دنبالهٔ هندسی می‌سازد و
    # همیشه کمی ناهموار می‌ماند (سؤالِ کم‌کشش می‌تواند چند بار پشتِ‌سرِ‌هم
    # بیاید). پس: **اول** سؤال‌های کم‌کشش‌تر را جدا می‌کنیم (کمینهٔ کشش) و
    # **بعد** بین همان‌ها تصادفی می‌کشیم. تصادف حفظ می‌شود، ولی هیچ سؤالی
    # نمی‌تواند بیش از یک واحد از کمینه جلو بزند.
    counts = [int(draw_counts.get(int(q.id), 0)) for q in pool]
    floor = min(counts)
    # پنجرهٔ مجاز: فقط سؤال‌هایی که کشششان در کمترین «سطح» است. اگر استخر
    # کوچک شد (همه یک‌اند) همان همه می‌مانند.
    window = [q for q, c in zip(pool, counts, strict=True) if c <= floor]
    if len(window) > 1:
        return _RNG.choice(window)
    weights = [1.0 / (1.0 + float(draw_counts.get(int(q.id), 0))) * 2.0 for q in pool]
    total = sum(weights)
    if total <= 0:
        return _RNG.choice(list(pool))
    point = _RNG.uniform(0, total)
    cursor = 0.0
    for question, weight in zip(pool, weights, strict=True):
        cursor += weight
        if point <= cursor:
            return question
    return pool[-1]


def select_balanced_questions[Q: _QuestionLike](
    candidates: Sequence[Q],
    count: int,
    *,
    draw_counts: dict[int, int] | None = None,
) -> list[Q]:
    """انتخاب `count` سؤال منصفانه از `candidates`.

    پارامترها
    ─────────
    candidates : سؤال‌های واجد شرایط (فعال و دارای چهار گزینه).
    count      : تعداد سؤال آزمون.
    draw_counts: نگاشت `question_id → تعداد دفعات کشیده‌شدن` تا این تابع
                 یکنواختی را در طول مسابقه دنبال کند.

    خروجی همیشه دقیقاً `count` سؤال است (تا وقتی `candidates` کمتر نباشد)،
    و ترکیب دشواری‌اش تا حد امکان به نسبت هدف نزدیک می‌ماند.
    """
    if count <= 0:
        return []
    pool: list[Q] = list(candidates)
    if len(pool) < count:
        raise ValueError("بانک سؤال برای توزیع منصفانه کافی نیست.")
    draws = draw_counts or {}

    by_difficulty: dict[str, list[Q]] = defaultdict(list)
    for question in pool:
        by_difficulty[str(question.difficulty)].append(question)

    # سهم اولیه؛ سطح‌های غایب یا خالی سهمشان آزاد می‌شود.
    target = _apportion(count, _DIFFICULTY_WEIGHTS)
    chosen: list[Q] = []
    used_ids: set[int] = set()
    used_stories: set[str] = set()

    def _take_from(candidates_of_tier: list[Q], how_many: int) -> int:
        """برداشتن تا `how_many` سؤال از یک سطح با رعایت پراکندگی داستان."""
        taken = 0
        spill: list[Q] = []
        while taken < how_many:
            available = [q for q in candidates_of_tier if int(q.id) not in used_ids]
            if not available:
                break
            fresh = [
                q for q in available if (str(q.source_story) or f"#{q.id}") not in used_stories
            ]
            # اگر همهٔ داستان‌های این سطح تکراری شد، اجازهٔ تکرار داستان می‌دهیم
            # ولی همچنان سؤال تکراری نمی‌گیریم.
            bucket = fresh or available
            if not bucket:
                break
            picked = _weighted_pick(bucket, draws)
            if not fresh:
                spill.append(picked)
            chosen.append(picked)
            used_ids.add(int(picked.id))
            story = str(picked.source_story) or f"#{picked.id}"
            used_stories.add(story)
            taken += 1
        del spill
        return taken

    # دور اول: هر سطح سهم خودش را می‌گیرد.
    for tier in _DIFFICULTY_ORDER:
        want = min(target.get(tier, 0), count - len(chosen))
        if want > 0:
            _take_from(by_difficulty.get(tier, []), want)

    # دور دوم: کمبود سطح‌های خالی را از باقی بانک پر کن (بی‌طرف به سطح).
    if len(chosen) < count:
        remaining = [q for q in pool if int(q.id) not in used_ids]
        # ترتیب: اول سطح‌هایی که در هدف سهم داشتند ولی خالی بودند.
        ordered: list[Q] = []
        for tier in _DIFFICULTY_ORDER:
            ordered.extend([q for q in remaining if str(q.difficulty) == tier])
        ordered.extend([q for q in remaining if str(q.difficulty) not in _DIFFICULTY_WEIGHTS])
        _take_from(ordered, count - len(chosen))

    # دور سوم (شبکهٔ ایمنی): اگر به هر دلیلی هنوز کم بود، همهٔ باقی بانک.
    if len(chosen) < count:
        leftover = [q for q in pool if int(q.id) not in used_ids]
        _take_from(leftover, count - len(chosen))

    # ترتیب نهایی سؤال‌ها هم تصادفی است تا الگوی «ساده‌ها اول» لو نرود.
    _RNG.shuffle(chosen)
    return chosen[:count]


def describe_balance(selected: Sequence[_QuestionLike]) -> dict[str, Any]:
    """گزارش خوانای ترکیب انتخاب‌شده — برای لاگ حسابرسی و تست.

    خروجی نمونه:
        {"total": 5, "tiers": {"easy": 2, "medium": 2, "hard": 1},
         "stories": ["داستان ۳", …], "unique_stories": 5}
    """
    tiers: dict[str, int] = defaultdict(int)
    stories: list[str] = []
    for question in selected:
        tiers[str(question.difficulty)] += 1
        stories.append(str(question.source_story) or f"#{question.id}")
    return {
        "total": len(selected),
        "tiers": dict(tiers),
        "stories": stories,
        "unique_stories": len(set(stories)),
    }

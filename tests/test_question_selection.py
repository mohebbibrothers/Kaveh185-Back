"""تست‌های توزیع عادلانهٔ سؤال (`apps/exam/selection.py`).

چرا این تست‌ها مهم‌اند؟ «تصادفی» و «عادلانه» یکی نیستند. اگر روزی کسی
`selection` را با `random.sample` ساده عوض کند، هیچ تستی نمی‌شکند مگر
همین‌جا. هر تست یک تعهد مشخص را قفل می‌کند:

  ۱. تعداد دقیق سؤال
  ۲. ترکیب سطح‌ها نزدیک به سهم هدف
  ۳. یک داستان تکراری در یک آزمون نمی‌آید
  ۴. سؤال‌های کم‌کشش‌تر در طول زمان یکنواخت توزیع می‌شوند
  ۵. بانک کوچک آزمون را نمی‌شکند
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from apps.exam.selection import describe_balance, select_balanced_questions


@dataclass
class FakeQuestion:
    """سؤال ساختگی برای تست — بدون دیتابیس."""

    id: int
    difficulty: str
    source_story: str


def build_bank(easy: int = 12, medium: int = 12, hard: int = 6) -> list[FakeQuestion]:
    """بانک سؤال ساختگی با تعداد مشخص در هر سطح و داستان یکتا."""
    bank: list[FakeQuestion] = []
    seq = 1
    for tier, how_many in (("easy", easy), ("medium", medium), ("hard", hard)):
        for _ in range(how_many):
            bank.append(FakeQuestion(id=seq, difficulty=tier, source_story=f"داستان {seq}"))
            seq += 1
    return bank


def test_returns_exact_count() -> None:
    """همیشه دقیقاً `count` سؤال برمی‌گردد."""
    for count in (1, 3, 5, 10):
        picked = select_balanced_questions(build_bank(), count)
        assert len(picked) == count


def test_no_duplicate_questions() -> None:
    """یک سؤال دو بار در یک آزمون نمی‌آید."""
    picked = select_balanced_questions(build_bank(), 10)
    assert len({q.id for q in picked}) == len(picked)


def test_difficulty_mix_is_balanced() -> None:
    """ترکیب سطح‌ها به سهم هدف (۳۵/۴۵/۲۰) نزدیک است و هرگز یک‌طرفه نیست."""
    bank = build_bank()
    # میانگین روی ۲۰۰ آزمون: توزیع باید به هدف نزدیک شود، نه تصادفی یک‌طرفه.
    totals = {"easy": 0, "medium": 0, "hard": 0}
    for _ in range(200):
        for question in select_balanced_questions(bank, 5):
            totals[question.difficulty] += 1
    shares = {tier: total / 1000 for tier, total in totals.items()}
    # ۵ سؤال در هر آزمون ⇒ در هر آزمون میانگین ۱.۷۵ ساده، ۲.۲۵ متوسط، ۱ دشوار
    assert 0.25 <= shares["easy"] <= 0.45, shares
    assert 0.35 <= shares["medium"] <= 0.55, shares
    assert 0.12 <= shares["hard"] <= 0.30, shares


def test_every_attempt_has_at_least_two_tiers() -> None:
    """هیچ آزمونی تک‌سطحی نیست — مگر بانک واقعاً یک‌سطحی باشد."""
    bank = build_bank()
    for _ in range(50):
        tiers = {q.difficulty for q in select_balanced_questions(bank, 5)}
        assert len(tiers) >= 2


def test_story_spread_within_one_attempt() -> None:
    """در یک آزمون، داستان‌ها تکرار نمی‌شوند (تا وقتی بانک اجازه دهد)."""
    bank = build_bank()
    for _ in range(50):
        picked = select_balanced_questions(bank, 5)
        stories = [q.source_story for q in picked]
        assert len(set(stories)) == len(stories), stories


def test_draw_counts_even_out_over_time() -> None:
    """شمارندهٔ کشش باعث می‌شود همهٔ سؤال‌ها به یک اندازه دیده شوند.

    این همان چیزی است که کاربر می‌خواهد: «سؤال‌ها عادلانه توزیع شوند».
    اگر `times_drawn` را نادیده بگیریم، این تست می‌شکند.
    """
    bank = build_bank(easy=10, medium=10, hard=10)
    draws: dict[int, int] = {}
    for _ in range(120):
        for question in select_balanced_questions(bank, 5, draw_counts=draws):
            draws[question.id] = draws.get(question.id, 0) + 1
    # هر ۳۰ سؤال باید دست‌کم یک بار دیده شده باشد (۱۲۰ آزمون × ۵ = ۶۰۰ کشش).
    assert len(draws) == len(bank)
    spread = max(draws.values()) - min(draws.values())
    average = sum(draws.values()) / len(draws)
    assert spread <= average * 1.2, f"توزیع ناهموار: {sorted(draws.values())}"


def test_small_bank_does_not_crash() -> None:
    """بانک کوچک (اما کافی) هم آزمون کامل می‌دهد."""
    bank = build_bank(easy=2, medium=2, hard=1)
    picked = select_balanced_questions(bank, 5)
    assert len(picked) == 5


def test_bank_smaller_than_count_raises() -> None:
    """بانک ناکافی باید خطای روشن بدهد، نه آزمون ناقص."""
    with pytest.raises(ValueError, match="کافی نیست"):
        select_balanced_questions(build_bank(easy=1, medium=0, hard=0), 5)


def test_describe_balance_reports_truthfully() -> None:
    """گزارش ترکیب با واقعیت انتخاب‌شده می‌خواند."""
    picked = select_balanced_questions(build_bank(), 5)
    report = describe_balance(picked)
    assert report["total"] == 5
    assert sum(report["tiers"].values()) == 5
    assert report["unique_stories"] == 5

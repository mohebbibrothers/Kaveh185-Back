"""اعتبارسنج‌های دامنهٔ بانک سوال چهارگزینه‌ای و تنظیمات آزمون کاوه ۱۸۵."""

from __future__ import annotations

from typing import Any

from apps.core.exceptions import ValidationDomainError


def validate_question_options_payload(options: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """بررسی اینکه هر سوال دقیقاً ۴ گزینه با شماره‌های ۱ تا ۴ و دقیقاً ۱ گزینهٔ صحیح داشته باشد."""
    if not isinstance(options, list) or len(options) != 4:
        raise ValidationDomainError(
            "هر سوال باید دقیقاً دارای ۴ گزینه باشد.",
            code="invalid_options_count",
        )

    normalized: list[dict[str, Any]] = []
    seen_numbers: set[int] = set()
    correct_count = 0

    for idx, opt in enumerate(options, start=1):
        opt_num = int(opt.get("option_number", idx))
        if opt_num not in {1, 2, 3, 4} or opt_num in seen_numbers:
            raise ValidationDomainError(
                "گزینه‌های سوال باید دارای شماره‌های یکتای ۱ تا ۴ باشند.",
                code="invalid_option_numbers",
            )
        seen_numbers.add(opt_num)

        text = str(opt.get("text", "")).strip()
        if not text:
            raise ValidationDomainError(
                f"متن گزینهٔ شمارهٔ {opt_num} نمی‌تواند خالی باشد.",
                code="empty_option_text",
            )
        is_correct = bool(opt.get("is_correct", False))
        if is_correct:
            correct_count += 1

        normalized.append(
            {
                "option_number": opt_num,
                "text": text,
                "is_correct": is_correct,
            }
        )

    if correct_count != 1:
        raise ValidationDomainError(
            "هر سوال چهارگزینه‌ای باید دقیقاً دارای یک گزینهٔ درست باشد.",
            code="invalid_correct_option_count",
        )

    normalized.sort(key=lambda x: int(x["option_number"]))
    return normalized

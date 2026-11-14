"""فیلترهای بانک سوال چهارگزینه‌ای در پنل ادمین."""

from __future__ import annotations

import django_filters

from .models import Question


class QuestionFilterSet(django_filters.FilterSet):
    """فیلتر سوالات بانک سوال بر اساس سطح دشواری، وضعیت فعال و فصل."""

    difficulty = django_filters.CharFilter(field_name="difficulty", lookup_expr="exact")
    is_active = django_filters.BooleanFilter(field_name="is_active")
    chapter = django_filters.CharFilter(field_name="chapter", lookup_expr="icontains")

    class Meta:
        model = Question
        fields = ["difficulty", "is_active", "chapter"]

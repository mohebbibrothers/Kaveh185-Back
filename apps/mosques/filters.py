"""فیلترهای کوئری برای مساجد."""

from __future__ import annotations

import django_filters

from .models import Mosque


class MosqueFilterSet(django_filters.FilterSet):
    """فیلترست مساجد برای پنل ادمین."""

    name = django_filters.CharFilter(field_name="name", lookup_expr="icontains")
    code = django_filters.CharFilter(field_name="code", lookup_expr="iexact")

    class Meta:
        model = Mosque
        fields = ["is_active", "code", "name"]

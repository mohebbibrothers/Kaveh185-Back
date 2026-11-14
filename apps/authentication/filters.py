"""فیلترهای کوئری برای کاربران و سیگنال‌های ریسک."""

from __future__ import annotations

import django_filters

from .models import User


class UserFilterSet(django_filters.FilterSet):
    """فیلترست کاربران در پنل ادمین."""

    mosque_id = django_filters.NumberFilter(field_name="mosque_id")
    role = django_filters.CharFilter(field_name="role", lookup_expr="exact")

    class Meta:
        model = User
        fields = ["role", "mosque_id", "is_active"]

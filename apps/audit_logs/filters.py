"""فیلترهای کوئری برای لاگ‌های حسابرسی."""

from __future__ import annotations

import django_filters

from .models import AuditLog


class AuditLogFilterSet(django_filters.FilterSet):
    """فیلترست رسمی DRF برای جست‌وجوی لاگ‌های حسابرسی."""

    action = django_filters.CharFilter(field_name="action", lookup_expr="exact")
    resource_type = django_filters.CharFilter(field_name="resource_type", lookup_expr="exact")
    resource_id = django_filters.CharFilter(field_name="resource_id", lookup_expr="exact")

    class Meta:
        model = AuditLog
        fields = ["action", "resource_type", "resource_id", "user"]

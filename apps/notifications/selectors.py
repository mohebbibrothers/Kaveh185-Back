"""سلکتورهای خواندن لاگ پیامک‌های ارسالی و وضعیت صف Outbox برای پنل ادمین."""

from __future__ import annotations

from django.db.models import Q, QuerySet

from .models import SMSDeliveryLog


def get_sms_delivery_logs_queryset(
    *,
    category: str = "",
    status: str = "",
    search: str = "",
) -> QuerySet[SMSDeliveryLog]:
    """واکشی لاگ پیامک‌های ارسالی با قابلیت فیلتر و جستجو."""
    qs = SMSDeliveryLog.objects.all().order_by("-created_at", "-id")
    if category.strip():
        qs = qs.filter(category=category.strip())
    if status.strip():
        qs = qs.filter(status=status.strip())
    if search.strip():
        q = search.strip()
        qs = qs.filter(Q(recipient_phone__icontains=q) | Q(message_text__icontains=q))
    return qs

"""مسیرهای API مدیریت پیامک‌ها و صف Outbox برای پنل ادمین."""

from __future__ import annotations

from django.urls import path

from .views import (
    AdminFlushOutboxAPIView,
    AdminSendTestSMSAPIView,
    AdminSMSDeliveryLogListAPIView,
)

app_name = "notifications"

urlpatterns = [
    path("admin/sms-logs/", AdminSMSDeliveryLogListAPIView.as_view(), name="admin-sms-logs"),
    path("admin/send-test/", AdminSendTestSMSAPIView.as_view(), name="admin-send-test"),
    path("admin/outbox/flush/", AdminFlushOutboxAPIView.as_view(), name="admin-outbox-flush"),
]

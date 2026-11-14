"""تست‌های ارسال پیامک، لاگ تحویل، پردازش صف Outbox و مرکز فرماندهی یکپارچه ادمین."""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from apps.mosques.models import Mosque


@pytest.mark.django_db()
def test_notifications_sms_logs_outbox_flush_and_command_center(
    admin_client: APIClient,
    seeded_mosques: list[Mosque],
) -> None:
    """تست ارسال پیامک تستی، مشاهده لاگ پیامک‌ها، پردازش صف Outbox و اسنپ‌شات مرکز فرماندهی ادمین."""
    del seeded_mosques

    send_resp = admin_client.post(
        "/api/v1/notifications/admin/send-test/",
        data={
            "recipient_phone": "09123334455",
            "message_text": "اطلاعیه مراسم قرعه‌کشی بزرگ هفته بسیج حوزه ۱۸۵ شهید کاوه",
        },
        format="json",
    )
    assert send_resp.status_code == 201
    assert send_resp.json()["data"]["status"] == "sent"

    logs_resp = admin_client.get("/api/v1/notifications/admin/sms-logs/?category=announcement")
    assert logs_resp.status_code == 200
    assert logs_resp.json()["data"]["pagination"]["count"] >= 1

    flush_resp = admin_client.post("/api/v1/notifications/admin/outbox/flush/")
    assert flush_resp.status_code == 200
    assert "processed" in flush_resp.json()["data"]

    cmd_resp = admin_client.get("/api/v1/admin/command-center/")
    assert cmd_resp.status_code == 200
    cmd_data = cmd_resp.json()["data"]
    assert "exam_status" in cmd_data
    assert "overview" in cmd_data
    assert "top_mosques" in cmd_data
    assert cmd_data["security_and_integrity"]["audit_chain_intact"] is True

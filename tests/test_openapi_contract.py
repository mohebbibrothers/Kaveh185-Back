"""تست‌های قرارداد اسکیمای OpenAPI 3.0، Swagger UI و ReDoc."""

from __future__ import annotations

from io import StringIO
from typing import Any

import pytest
from django.core.management import call_command
from rest_framework.test import APIClient


@pytest.mark.django_db()
def test_openapi_schema_generation_and_validation() -> None:
    """تولید اسکیمای OpenAPI باید بدون هیچ‌گونه خطا یا هشدار (`--fail-on-warn`) انجام شود."""
    out = StringIO()
    err = StringIO()
    call_command(
        "spectacular",
        "--validate",
        "--fail-on-warn",
        stdout=out,
        stderr=err,
    )
    schema_text = out.getvalue()
    assert "openapi: 3.0." in schema_text
    assert "/api/v1/auth/register/" in schema_text
    assert "/api/v1/mosques/" in schema_text
    assert "/api/v1/mosques/leaderboard/" in schema_text
    assert "/api/v1/exam/status/" in schema_text
    assert "/api/v1/exam/start/" in schema_text
    assert "/api/v1/exam/answer/" in schema_text
    assert "/api/v1/exam/finish/" in schema_text
    assert "/api/v1/exam/report-card/" in schema_text
    assert "/api/v1/reporting/admin/participants/" in schema_text
    assert "/api/v1/reporting/admin/export.xlsx" in schema_text


@pytest.mark.django_db()
def test_swagger_and_redoc_endpoints_respond(api_client: APIClient, settings: Any) -> None:
    """مسیرهای `/api/v1/schema/`، `/api/v1/docs/` و `/api/v1/redoc/` باید در دسترس باشند."""
    settings.API_DOCS_ALLOW_ANONYMOUS = True
    schema_resp = api_client.get("/api/v1/schema/")
    assert schema_resp.status_code == 200

    swagger_resp = api_client.get("/api/v1/docs/")
    assert swagger_resp.status_code == 200

    redoc_resp = api_client.get("/api/v1/redoc/")
    assert redoc_resp.status_code == 200

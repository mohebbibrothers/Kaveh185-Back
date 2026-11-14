"""صفحه‌بندی استاندارد در قالب Envelope یکپارچه برای فهرست‌های API کاوه ۱۸۵."""

from __future__ import annotations

from typing import Any

from rest_framework.pagination import LimitOffsetPagination, PageNumberPagination
from rest_framework.response import Response

from .responses import success_response


class StandardResultsSetPagination(PageNumberPagination):
    """صفحه‌بندی مبتنی بر شماره صفحه با سقف امن و خروجی منطبق با Envelope استاندارد پروژه."""

    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 200

    def get_paginated_response(self, data: Any) -> Response:
        """برگرداندن نتایج صفحه‌بندی‌شده داخل کلید `data` به همراه متادیتای کامل."""
        assert self.page is not None
        paginator = self.page.paginator
        pagination_meta = {
            "count": paginator.count,
            "total_pages": paginator.num_pages,
            "current_page": self.page.number,
            "page_size": self.get_page_size(self.request),
            "next": self.get_next_link(),
            "previous": self.get_previous_link(),
        }
        return success_response(
            data={
                "results": data,
                "pagination": pagination_meta,
            },
            meta=pagination_meta,
            message="فهرست اطلاعات با موفقیت دریافت شد.",
        )

    def get_paginated_response_schema(self, schema: dict[str, Any]) -> dict[str, Any]:
        """تولید اسکیمای دقیق OpenAPI برای پاسخ‌های صفحه‌بندی‌شده."""
        return {
            "type": "object",
            "required": ["success", "status_code", "code", "message", "trace_id", "data"],
            "properties": {
                "success": {"type": "boolean", "example": True},
                "status_code": {"type": "integer", "example": 200},
                "code": {"type": "string", "example": "ok"},
                "message": {"type": "string", "example": "فهرست اطلاعات با موفقیت دریافت شد."},
                "trace_id": {"type": "string", "example": "019a83f0000070008000000000000001"},
                "data": {
                    "type": "object",
                    "required": ["results", "pagination"],
                    "properties": {
                        "results": schema,
                        "pagination": {
                            "type": "object",
                            "properties": {
                                "count": {"type": "integer", "example": 120},
                                "total_pages": {"type": "integer", "example": 6},
                                "current_page": {"type": "integer", "example": 1},
                                "page_size": {"type": "integer", "example": 20},
                                "next": {"type": "string", "nullable": True},
                                "previous": {"type": "string", "nullable": True},
                            },
                        },
                    },
                },
            },
        }


class StandardLimitOffsetPagination(LimitOffsetPagination):
    """صفحه‌بندی مبتنی بر `limit` و `offset` با خروجی منطبق با Envelope استاندارد پروژه."""

    default_limit = 20
    limit_query_param = "limit"
    offset_query_param = "offset"
    max_limit = 200

    def get_paginated_response(self, data: Any) -> Response:
        """برگرداندن نتایج صفحه‌بندی‌شده داخل کلید `data` به همراه متادیتای کامل."""
        pagination_meta = {
            "count": self.count,
            "limit": self.limit,
            "offset": self.offset,
            "next": self.get_next_link(),
            "previous": self.get_previous_link(),
        }
        return success_response(
            data={
                "results": data,
                "pagination": pagination_meta,
            },
            meta=pagination_meta,
            message="فهرست اطلاعات با موفقیت دریافت شد.",
        )

    def get_paginated_response_schema(self, schema: dict[str, Any]) -> dict[str, Any]:
        """تولید اسکیمای دقیق OpenAPI برای پاسخ‌های صفحه‌بندی‌شده با `limit/offset`."""
        return {
            "type": "object",
            "required": ["success", "status_code", "code", "message", "trace_id", "data"],
            "properties": {
                "success": {"type": "boolean", "example": True},
                "status_code": {"type": "integer", "example": 200},
                "code": {"type": "string", "example": "ok"},
                "message": {"type": "string", "example": "فهرست اطلاعات با موفقیت دریافت شد."},
                "trace_id": {"type": "string", "example": "019a83f0000070008000000000000001"},
                "data": {
                    "type": "object",
                    "required": ["results", "pagination"],
                    "properties": {
                        "results": schema,
                        "pagination": {
                            "type": "object",
                            "properties": {
                                "count": {"type": "integer", "example": 120},
                                "limit": {"type": "integer", "example": 20},
                                "offset": {"type": "integer", "example": 0},
                                "next": {"type": "string", "nullable": True},
                                "previous": {"type": "string", "nullable": True},
                            },
                        },
                    },
                },
            },
        }

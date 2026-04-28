"""Unified API response envelope.

All API responses follow the format:
{
    "ok": bool,
    "error": {"code": str, "message": str} | null,
    "data": any | null
}
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class APIError(BaseModel):
    """Standardized API error."""

    code: str
    message: str
    details: dict | None = None  # v5.3.0: Optional additional details


class EnvelopeResponse(BaseModel):
    """Unified API response envelope."""

    ok: bool
    error: APIError | None = None
    data: Any = None


def envelope_response(data: Any) -> EnvelopeResponse:
    """Create a successful response envelope."""
    return EnvelopeResponse(ok=True, error=None, data=data)


def error_response(code: str, message: str, details: dict | None = None) -> EnvelopeResponse:
    """Create an error response envelope."""
    return EnvelopeResponse(ok=False, error=APIError(code=code, message=message, details=details), data=None)


# Standard error codes
ERROR_CODES = {
    "PROJECT_NOT_FOUND": "项目不存在",
    "CHAPTER_NOT_FOUND": "章节不存在",
    "VALIDATION_ERROR": "参数验证失败",
    "INTERNAL_ERROR": "内部错误",
    "INVALID_REQUEST": "无效请求",
    "RESOURCE_NOT_FOUND": "资源不存在",
    "OPERATION_FAILED": "操作失败",
    "UNAUTHORIZED": "未授权",
    "FORBIDDEN": "禁止访问",
}

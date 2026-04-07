"""Canonical API error responses."""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse


def api_error_payload(
    *,
    error: str,
    code: str,
    request_id: str | None = None,
    details: Any | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "error": error,
        "code": code,
    }
    if request_id:
        payload["request_id"] = request_id
    if details is not None:
        payload["details"] = details
    return payload


def api_error_response(
    *,
    request: Request | None,
    status_code: int,
    error: str,
    code: str,
    details: Any | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None) if request else None
    return JSONResponse(
        status_code=status_code,
        content=api_error_payload(
            error=error,
            code=code,
            request_id=request_id,
            details=details,
        ),
        headers=headers,
    )

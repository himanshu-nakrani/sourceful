"""Shared router dependencies for provider auth and client scoping."""

from __future__ import annotations

from dataclasses import dataclass
import re

from fastapi import Header, HTTPException, Request

SESSION_RE = re.compile(r"^[A-Za-z0-9._:-]{8,128}$")


@dataclass(slots=True)
class RequestContext:
    owner_id: str
    request_id: str
    client_ip: str


async def get_request_context(
    request: Request,
    x_client_session: str | None = Header(default=None),
) -> RequestContext:
    if not x_client_session or not SESSION_RE.match(x_client_session):
        raise HTTPException(
            status_code=400,
            detail={
                "error": "Missing or invalid X-Client-Session header.",
                "code": "INVALID_CLIENT_SESSION",
            },
        )

    return RequestContext(
        owner_id=x_client_session,
        request_id=getattr(request.state, "request_id", "unknown"),
        client_ip=request.client.host if request.client else "unknown",
    )



def require_provider_api_key(x_provider_api_key: str | None = Header(default=None)) -> str:
    if not x_provider_api_key or not x_provider_api_key.strip():
        raise HTTPException(
            status_code=401,
            detail={
                "error": "Missing X-Provider-Api-Key header.",
                "code": "MISSING_PROVIDER_API_KEY",
            },
        )
    return x_provider_api_key.strip()

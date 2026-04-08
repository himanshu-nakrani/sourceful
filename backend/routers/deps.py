"""Shared router dependencies for provider auth and client scoping."""

from __future__ import annotations

from dataclasses import dataclass
import re

from fastapi import Depends, Header, HTTPException, Request
from backend.auth import get_user_from_session
from backend.settings import settings

SESSION_RE = re.compile(r"^[A-Za-z0-9._:-]{8,128}$")


@dataclass(slots=True)
class RequestContext:
    owner_id: str
    request_id: str
    client_ip: str
    user_id: str | None = None
    role: str = "anonymous"
    is_authenticated: bool = False


async def get_request_context(
    request: Request,
    x_client_session: str | None = Header(default=None),
) -> RequestContext:
    session_token = request.cookies.get(settings.auth_cookie_name)
    if session_token:
        user = await get_user_from_session(session_token)
        if user:
            return RequestContext(
                owner_id=f"user:{user['id']}",
                request_id=getattr(request.state, "request_id", "unknown"),
                client_ip=request.client.host if request.client else "unknown",
                user_id=user["id"],
                role=user.get("role", "user"),
                is_authenticated=True,
            )

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


async def require_authenticated_context(
    request: Request,
) -> RequestContext:
    session_token = request.cookies.get(settings.auth_cookie_name)
    if not session_token:
        raise HTTPException(
            status_code=401,
            detail={"error": "Authentication required.", "code": "AUTH_REQUIRED"},
        )
    user = await get_user_from_session(session_token)
    if not user:
        raise HTTPException(
            status_code=401,
            detail={"error": "Authentication required.", "code": "AUTH_REQUIRED"},
        )
    return RequestContext(
        owner_id=f"user:{user['id']}",
        request_id=getattr(request.state, "request_id", "unknown"),
        client_ip=request.client.host if request.client else "unknown",
        user_id=user["id"],
        role=user.get("role", "user"),
        is_authenticated=True,
    )


async def require_admin_context(
    context: RequestContext = Depends(require_authenticated_context),
) -> RequestContext:
    if context.role != "admin":
        raise HTTPException(
            status_code=403,
            detail={"error": "Admin access required.", "code": "ADMIN_REQUIRED"},
        )
    return context

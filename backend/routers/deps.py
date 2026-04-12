"""Shared router dependencies for provider auth and client scoping."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException, Request
from backend.auth import get_user_from_session
from backend.settings import settings
from backend.services.provider_auth import normalize_provider_api_key


@dataclass(slots=True)
class RequestContext:
    owner_id: str
    request_id: str
    client_ip: str
    user_id: str | None = None
    role: str = "anonymous"
    is_authenticated: bool = False


def _read_bearer_token(request: Request) -> str | None:
    authorization = request.headers.get("authorization", "")
    if not authorization.lower().startswith("bearer "):
        return None
    token = authorization[7:].strip()
    return token or None


async def get_request_context(
    request: Request,
) -> RequestContext:
    session_token = request.cookies.get(settings.auth_cookie_name) or _read_bearer_token(request)
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
    raise HTTPException(
        status_code=401,
        detail={"error": "Authentication required.", "code": "AUTH_REQUIRED"},
    )



def require_provider_api_key(x_provider_api_key: str | None = Header(default=None)) -> str:
    provider_api_key = normalize_provider_api_key(x_provider_api_key)
    if not provider_api_key:
        raise HTTPException(
            status_code=401,
            detail={
                "error": "Missing X-Provider-Api-Key header.",
                "code": "MISSING_PROVIDER_API_KEY",
            },
        )
    return provider_api_key


async def require_authenticated_context(
    request: Request,
) -> RequestContext:
    session_token = request.cookies.get(settings.auth_cookie_name) or _read_bearer_token(request)
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

"""Shared router dependencies for provider auth and client scoping."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException, Request
from backend.auth import get_user_from_session
from backend.settings import settings
from backend.services.provider_auth import normalize_provider_api_key
from backend.services.anon_scope import anon_owner_id


@dataclass(slots=True)
class RequestContext:
    owner_id: str
    request_id: str
    client_ip: str
    user_id: str | None = None
    role: str = "anonymous"
    is_authenticated: bool = False


def _read_bearer_token(request: Request) -> str | None:
    """
    Extracts a Bearer token from the request's Authorization header.
    
    Reads the Authorization header (case-insensitive) and returns the token portion after the "Bearer " prefix if present and non-empty.
    
    Returns:
        str: The Bearer token string if present and non-empty, `None` otherwise.
    """
    authorization = request.headers.get("authorization", "")
    if not authorization.lower().startswith("bearer "):
        return None
    token = authorization[7:].strip()
    return token or None


def _read_client_session(request: Request) -> str | None:
    """
    Extract the X-Client-Session header value used for anonymous client scoping.
    
    Reads the "x-client-session" request header, strips surrounding whitespace, and returns the header value or None when the header is missing or empty.
    
    Parameters:
        request (Request): The incoming HTTP request.
    
    Returns:
        str | None: The trimmed client session identifier if present, `None` otherwise.
    """
    client_session = request.headers.get("x-client-session", "")
    return client_session.strip() or None


async def get_request_context(
    request: Request,
) -> RequestContext:
    """
    Resolve authentication for the incoming HTTP request and return a RequestContext reflecting the resolved scope.
    
    If a valid session token is found (cookie named by settings.auth_cookie_name or a Bearer token), returns an authenticated RequestContext with owner_id set to "user:{user_id}", the request_id and client_ip extracted from the request, the user's id and role, and is_authenticated=True. If no authenticated user is found but an X-Client-Session header is present, returns an anonymous RequestContext with owner_id set to "anon:{client_session}", user_id=None, role="anonymous", and is_authenticated=False.
    
    Returns:
        RequestContext: Context populated with owner_id, request_id, client_ip, user_id, role, and is_authenticated.
    
    Raises:
        HTTPException: Raised with status 401 and detail code "AUTH_REQUIRED" when neither an authenticated session nor an X-Client-Session header is provided.
    """
    bearer_token = _read_bearer_token(request)
    if bearer_token:
        user = await get_user_from_session(bearer_token)
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
    # Allow anonymous access with client session ID
    # Fix #5: HMAC the raw client-session value so the owner_id is
    # deterministic for the same header value but cannot be guessed/forged by
    # another client who doesn't know the HMAC secret.
    client_session = _read_client_session(request)
    if client_session:
        return RequestContext(
            owner_id=anon_owner_id(client_session),
            request_id=getattr(request.state, "request_id", "unknown"),
            client_ip=request.client.host if request.client else "unknown",
            user_id=None,
            role="anonymous",
            is_authenticated=False,
        )
    raise HTTPException(
        status_code=401,
        detail={"error": "Authentication required. Provide auth token or X-Client-Session header.", "code": "AUTH_REQUIRED"},
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
    bearer_token = _read_bearer_token(request)
    session_token = bearer_token or request.cookies.get(settings.auth_cookie_name)
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

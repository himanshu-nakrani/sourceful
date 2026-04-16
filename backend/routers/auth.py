from __future__ import annotations

import httpx
import logging
from fastapi import APIRouter, Depends, HTTPException, Request, Response

from backend.auth import (
    authenticate_or_create_oauth_user,
    authenticate_user,
    change_password,
    create_session,
    create_user,
    get_user_by_email,
    get_user_by_id,
    revoke_session,
)
from backend.models import (
    AuthResponse,
    ChangePasswordRequest,
    LoginRequest,
    SignupRequest,
    UserResponse,
)
from backend.routers.deps import RequestContext, require_authenticated_context
from backend.settings import settings

router = APIRouter()
logger = logging.getLogger(__name__)


def _read_bearer_token(request: Request) -> str | None:
    authorization = request.headers.get("authorization", "")
    if not authorization.lower().startswith("bearer "):
        return None
    token = authorization[7:].strip()
    return token or None


def _set_auth_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=settings.auth_cookie_name,
        value=token,
        httponly=True,
        secure=settings.auth_secure_cookies,
        samesite="lax",
        max_age=settings.auth_cookie_ttl_hours * 3600,
        path="/",
    )


@router.post("/auth/signup", response_model=AuthResponse, status_code=201)
async def signup(payload: SignupRequest, request: Request, response: Response):
    if len(payload.password) < 8:
        raise HTTPException(status_code=422, detail={"error": "Password too short.", "code": "WEAK_PASSWORD"})
    existing = await get_user_by_email(payload.email)
    if existing:
        raise HTTPException(status_code=409, detail={"error": "Email is already registered.", "code": "EMAIL_EXISTS"})
    user = await create_user(payload.email, payload.password)
    token = await create_session(
        user["id"],
        user_agent=request.headers.get("user-agent"),
        ip_address=request.client.host if request.client else None,
        ttl_hours=settings.auth_cookie_ttl_hours,
    )
    _set_auth_cookie(response, token)
    return AuthResponse(**user, session_token=token)


@router.post("/auth/login", response_model=AuthResponse)
async def login(payload: LoginRequest, request: Request, response: Response):
    user = await authenticate_user(payload.email, payload.password)
    if not user:
        raise HTTPException(status_code=401, detail={"error": "Invalid email or password.", "code": "INVALID_CREDENTIALS"})
    token = await create_session(
        user["id"],
        user_agent=request.headers.get("user-agent"),
        ip_address=request.client.host if request.client else None,
        ttl_hours=settings.auth_cookie_ttl_hours,
    )
    _set_auth_cookie(response, token)
    return AuthResponse(**user, session_token=token)


@router.post("/auth/logout")
async def logout(request: Request, response: Response):
    session_token = request.cookies.get(settings.auth_cookie_name) or _read_bearer_token(request)
    if session_token:
        await revoke_session(session_token)
    response.delete_cookie(key=settings.auth_cookie_name, path="/")
    return {"status": "ok"}


@router.get("/auth/me", response_model=UserResponse)
async def me(context: RequestContext = Depends(require_authenticated_context)):
    assert context.user_id
    user = await get_user_by_id(context.user_id)
    if not user:
        raise HTTPException(status_code=404, detail={"error": "User not found.", "code": "USER_NOT_FOUND"})
    return UserResponse(**user)


@router.post("/auth/change-password")
async def update_password(
    payload: ChangePasswordRequest,
    context: RequestContext = Depends(require_authenticated_context),
):
    assert context.user_id
    changed = await change_password(context.user_id, payload.current_password, payload.new_password)
    if not changed:
        raise HTTPException(status_code=400, detail={"error": "Invalid current password.", "code": "INVALID_PASSWORD"})
    return {"status": "ok"}


@router.get("/auth/google/config")
async def google_oauth_config():
    """Return the Google OAuth client_id so the frontend can build the consent URL."""
    return {"client_id": settings.google_oauth_client_id}


@router.post("/auth/google/callback")
async def google_oauth_callback(request: Request, response: Response):
    """Exchange a Google authorization code for user info, create/find the user, and issue a session."""
    body = await request.json()
    code = body.get("code", "").strip()
    redirect_uri = body.get("redirect_uri", "").strip()
    if not code:
        raise HTTPException(status_code=400, detail={"error": "Missing authorization code.", "code": "MISSING_CODE"})

    # Exchange auth code for tokens
    async with httpx.AsyncClient() as client:
        token_res = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": settings.google_oauth_client_id,
                "client_secret": settings.google_oauth_client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
        )
    if token_res.status_code != 200:
        logger.warning(
            "Google token exchange failed (status=%s): %s",
            token_res.status_code,
            token_res.text,
        )
        raise HTTPException(
            status_code=502,
            detail={"error": "Google token exchange failed.", "code": "GOOGLE_TOKEN_FAILED"},
        )
    tokens = token_res.json()
    id_token = tokens.get("id_token")
    if not id_token:
        raise HTTPException(status_code=502, detail={"error": "No id_token from Google.", "code": "GOOGLE_NO_ID_TOKEN"})

    # Decode the id_token (we trust Google's endpoint, just decode payload)
    import base64
    import json as _json

    parts = id_token.split(".")
    if len(parts) < 2:
        raise HTTPException(status_code=502, detail={"error": "Malformed id_token.", "code": "GOOGLE_BAD_TOKEN"})
    payload_b64 = parts[1] + "=" * (-len(parts[1]) % 4)
    payload = _json.loads(base64.urlsafe_b64decode(payload_b64))
    email = payload.get("email", "").strip().lower()
    if not email:
        raise HTTPException(status_code=400, detail={"error": "No email in Google token.", "code": "GOOGLE_NO_EMAIL"})
    if payload.get("email_verified") is not True:
        raise HTTPException(
            status_code=401,
            detail={"error": "Google account email is not verified.", "code": "GOOGLE_EMAIL_NOT_VERIFIED"},
        )

    user = await authenticate_or_create_oauth_user(email)
    if not user:
        raise HTTPException(status_code=401, detail={"error": "Account disabled.", "code": "ACCOUNT_DISABLED"})
    token = await create_session(
        user["id"],
        user_agent=request.headers.get("user-agent"),
        ip_address=request.client.host if request.client else None,
        ttl_hours=settings.auth_cookie_ttl_hours,
    )
    _set_auth_cookie(response, token)
    return AuthResponse(**user, session_token=token)

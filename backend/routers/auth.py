from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from backend.auth import (
    authenticate_user,
    change_password,
    create_session,
    create_user,
    get_user_by_id,
    get_user_by_email,
    revoke_session,
)
from backend.models import (
    ChangePasswordRequest,
    LoginRequest,
    SignupRequest,
    UserResponse,
)
from backend.routers.deps import RequestContext, require_authenticated_context
from backend.settings import settings

router = APIRouter()


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


@router.post("/auth/signup", response_model=UserResponse, status_code=201)
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
    return UserResponse(**user)


@router.post("/auth/login", response_model=UserResponse)
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
    return UserResponse(**user)


@router.post("/auth/logout")
async def logout(request: Request, response: Response):
    session_token = request.cookies.get(settings.auth_cookie_name)
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

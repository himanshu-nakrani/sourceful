from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from backend.auth import list_users, update_user
from backend.models import UpdateUserRequest, UserListResponse, UserResponse
from backend.routers.deps import require_admin_context

router = APIRouter()


@router.get("/users", response_model=UserListResponse)
async def users_list(_: object = Depends(require_admin_context)):
    users = await list_users()
    return UserListResponse(users=[UserResponse(**user) for user in users])


@router.patch("/users/{user_id}", response_model=UserResponse)
async def users_update(user_id: str, payload: UpdateUserRequest, _: object = Depends(require_admin_context)):
    if payload.role is None and payload.is_active is None:
        raise HTTPException(status_code=422, detail={"error": "No updates provided.", "code": "NO_UPDATES"})
    try:
        user = await update_user(user_id, role=payload.role, is_active=payload.is_active)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error": str(exc), "code": "SUPERUSER_PROTECTED"}) from exc
    if not user:
        raise HTTPException(status_code=404, detail={"error": "User not found.", "code": "USER_NOT_FOUND"})
    return UserResponse(**user)

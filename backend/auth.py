from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from backend.database import execute, execute_returning, fetch_all, fetch_one

PBKDF2_ITERATIONS = 480000
DEFAULT_SUPERUSER_EMAIL = "himanshunakrani0@gmail.com"
DEFAULT_SUPERUSER_PASSWORD = "him123"
DEFAULT_SUPERUSER_ROLE = "admin"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_dt(value: Any) -> datetime:
    if isinstance(value, datetime):
        dt = value
    else:
        dt = datetime.fromisoformat(str(value).replace(" ", "T"))
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _encode_b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _decode_b64(data: str) -> bytes:
    return base64.b64decode(data.encode("ascii"))


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${_encode_b64(salt)}${_encode_b64(digest)}"


def verify_password(password: str, password_hash: str) -> bool:
    try:
        algo, iteration_str, salt_b64, digest_b64 = password_hash.split("$", 3)
        if algo != "pbkdf2_sha256":
            return False
        iterations = int(iteration_str)
        expected = _decode_b64(digest_b64)
        actual = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            _decode_b64(salt_b64),
            iterations,
        )
        return hmac.compare_digest(expected, actual)
    except Exception:
        return False


def _normalize_user(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None
    return {
        "id": row["id"],
        "email": row["email"],
        "role": row.get("role", "user"),
        "is_active": bool(row.get("is_active", False)),
        "is_verified": bool(row.get("is_verified", False)),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


async def create_user(email: str, password: str, role: str = "user") -> dict[str, Any]:
    now = _utcnow().isoformat()
    normalized_email = email.strip().lower()
    row = await execute_returning(
        """
        INSERT INTO users (id, email, password_hash, role, is_active, is_verified, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        RETURNING id, email, role, is_active, is_verified, created_at, updated_at
        """,
        (str(uuid4()), normalized_email, hash_password(password), role, 1, 1, now, now),
    )
    if not row:
        raise RuntimeError("Failed to create user.")
    return _normalize_user(row) or {}


def is_reserved_superuser_email(email: str) -> bool:
    return email.strip().lower() == DEFAULT_SUPERUSER_EMAIL


async def get_user_by_email(email: str) -> dict[str, Any] | None:
    row = await fetch_one(
        """
        SELECT id, email, password_hash, role, is_active, is_verified, created_at, updated_at
        FROM users
        WHERE email = ?
        """,
        (email.strip().lower(),),
    )
    return row


async def authenticate_user(email: str, password: str) -> dict[str, Any] | None:
    row = await get_user_by_email(email)
    if not row or not bool(row.get("is_active")):
        return None
    if not verify_password(password, str(row.get("password_hash", ""))):
        return None
    return _normalize_user(row)


async def get_user_by_id(user_id: str) -> dict[str, Any] | None:
    row = await fetch_one(
        """
        SELECT id, email, role, is_active, is_verified, created_at, updated_at
        FROM users
        WHERE id = ?
        """,
        (user_id,),
    )
    return _normalize_user(row)


def _session_token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


async def create_session(
    user_id: str,
    *,
    user_agent: str | None,
    ip_address: str | None,
    ttl_hours: int,
) -> str:
    token = secrets.token_urlsafe(48)
    expires_at = (_utcnow() + timedelta(hours=ttl_hours)).isoformat()
    await execute(
        """
        INSERT INTO auth_sessions (id, user_id, token_hash, user_agent, ip_address, expires_at, revoked)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (str(uuid4()), user_id, _session_token_hash(token), user_agent, ip_address, expires_at, 0),
    )
    return token


async def revoke_session(token: str) -> None:
    await execute(
        "UPDATE auth_sessions SET revoked = 1 WHERE token_hash = ?",
        (_session_token_hash(token),),
    )


async def get_user_from_session(token: str) -> dict[str, Any] | None:
    row = await fetch_one(
        """
        SELECT
            users.id,
            users.email,
            users.role,
            users.is_active,
            users.is_verified,
            users.created_at,
            users.updated_at,
            auth_sessions.expires_at,
            auth_sessions.revoked
        FROM auth_sessions
        JOIN users ON users.id = auth_sessions.user_id
        WHERE auth_sessions.token_hash = ?
        """,
        (_session_token_hash(token),),
    )
    if not row:
        return None
    if bool(row.get("revoked")):
        return None
    if _parse_dt(row["expires_at"]) <= _utcnow():
        return None
    if not bool(row.get("is_active")):
        return None
    return _normalize_user(row)


async def change_password(user_id: str, current_password: str, new_password: str) -> bool:
    row = await fetch_one("SELECT password_hash FROM users WHERE id = ?", (user_id,))
    if not row or not verify_password(current_password, str(row["password_hash"])):
        return False
    await execute(
        "UPDATE users SET password_hash = ?, updated_at = ? WHERE id = ?",
        (hash_password(new_password), _utcnow().isoformat(), user_id),
    )
    return True


async def list_users() -> list[dict[str, Any]]:
    rows = await fetch_all(
        """
        SELECT id, email, role, is_active, is_verified, created_at, updated_at
        FROM users
        ORDER BY created_at DESC
        LIMIT 500
        """
    )
    return [_normalize_user(row) or {} for row in rows]


async def update_user(user_id: str, *, role: str | None, is_active: bool | None) -> dict[str, Any] | None:
    existing = await fetch_one("SELECT id, email FROM users WHERE id = ?", (user_id,))
    if not existing:
        return None
    if is_reserved_superuser_email(str(existing.get("email", ""))):
        if role is not None and role != DEFAULT_SUPERUSER_ROLE:
            raise ValueError("The default superuser role cannot be changed.")
        if is_active is not None and not is_active:
            raise ValueError("The default superuser cannot be disabled.")
    fields: list[str] = []
    params: list[Any] = []
    if role is not None:
        fields.append("role = ?")
        params.append(role)
    if is_active is not None:
        fields.append("is_active = ?")
        params.append(1 if is_active else 0)
    fields.append("updated_at = ?")
    params.append(_utcnow().isoformat())
    params.append(user_id)
    await execute(f"UPDATE users SET {', '.join(fields)} WHERE id = ?", tuple(params))
    row = await fetch_one(
        "SELECT id, email, role, is_active, is_verified, created_at, updated_at FROM users WHERE id = ?",
        (user_id,),
    )
    return _normalize_user(row)


async def ensure_default_superuser() -> dict[str, Any]:
    now = _utcnow().isoformat()
    existing = await get_user_by_email(DEFAULT_SUPERUSER_EMAIL)
    if existing:
        await execute(
            """
            UPDATE users
            SET password_hash = ?, role = ?, is_active = 1, is_verified = 1, updated_at = ?
            WHERE email = ?
            """,
            (
                hash_password(DEFAULT_SUPERUSER_PASSWORD),
                DEFAULT_SUPERUSER_ROLE,
                now,
                DEFAULT_SUPERUSER_EMAIL,
            ),
        )
    else:
        await create_user(
            DEFAULT_SUPERUSER_EMAIL,
            DEFAULT_SUPERUSER_PASSWORD,
            role=DEFAULT_SUPERUSER_ROLE,
        )
    user = await get_user_by_email(DEFAULT_SUPERUSER_EMAIL)
    return _normalize_user(user) or {}

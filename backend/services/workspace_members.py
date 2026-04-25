"""Phase 3: workspace membership + role-based access control.

The Phase 0 ownership model — ``owner_scope`` on the workspace — remains the
final source of truth: whoever created/owns a workspace can do anything. On
top of that, this module implements *additional* membership for authenticated
users, with the four roles required by the plan:

    owner   — full control (one-and-only-one per workspace)
    admin   — manage members, sources, notes, chats
    editor  — manage sources, notes, chats (no membership changes)
    viewer  — chat + read-only

The role hierarchy used for ``require_role`` checks:

    viewer < editor < admin < owner
"""

from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from backend.database import execute, fetch_all, fetch_one
from backend.settings import settings


TIMESTAMP_SQL = "NOW()" if settings.using_postgres else "CURRENT_TIMESTAMP"

ROLES = ("owner", "admin", "editor", "viewer")
_RANK = {role: idx for idx, role in enumerate(reversed(ROLES))}
# {"viewer": 0, "editor": 1, "admin": 2, "owner": 3}


def role_at_least(role: str | None, minimum: str) -> bool:
    if not role:
        return False
    return _RANK.get(role, -1) >= _RANK.get(minimum, 99)


def _serialize_member(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "workspace_id": row["workspace_id"],
        "user_id": row["user_id"],
        "email": row.get("email"),
        "role": row.get("role") or "viewer",
        "joined_at": row.get("joined_at"),
    }


def _serialize_invitation(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "workspace_id": row["workspace_id"],
        "email": row["email"],
        "role": row.get("role") or "viewer",
        "token": row["token"],
        "invited_by": row.get("invited_by"),
        "accepted_at": row.get("accepted_at"),
        "expires_at": row.get("expires_at"),
        "created_at": row.get("created_at"),
    }


async def get_effective_role(
    *,
    workspace_id: str,
    workspace_owner_scope: str,
    caller_owner_scope: str,
    caller_user_id: str | None,
) -> str | None:
    """Return the role the caller has on the workspace, or None if no access.

    The workspace's ``owner_scope`` always grants the ``owner`` role. Beyond
    that, authenticated users can be members via ``workspace_members``.
    """
    if caller_owner_scope == workspace_owner_scope:
        return "owner"
    if not caller_user_id:
        return None
    row = await fetch_one(
        "SELECT role FROM workspace_members WHERE workspace_id = ? AND user_id = ?",
        (workspace_id, caller_user_id),
    )
    return row["role"] if row else None


async def list_members(workspace_id: str) -> list[dict[str, Any]]:
    rows = await fetch_all(
        """
        SELECT m.id, m.workspace_id, m.user_id, m.role, m.joined_at, u.email
        FROM workspace_members m
        LEFT JOIN users u ON u.id = m.user_id
        WHERE m.workspace_id = ?
        ORDER BY m.joined_at ASC
        """,
        (workspace_id,),
    )
    return [_serialize_member(r) for r in rows]


async def add_member(
    workspace_id: str, *, user_id: str, role: str = "viewer"
) -> dict[str, Any]:
    if role not in ROLES:
        raise ValueError(f"Invalid role: {role}")
    existing = await fetch_one(
        "SELECT id FROM workspace_members WHERE workspace_id = ? AND user_id = ?",
        (workspace_id, user_id),
    )
    if existing:
        await execute(
            "UPDATE workspace_members SET role = ? WHERE id = ?",
            (role, existing["id"]),
        )
        member_id = existing["id"]
    else:
        member_id = str(uuid.uuid4())
        await execute(
            f"""
            INSERT INTO workspace_members (id, workspace_id, user_id, role, joined_at)
            VALUES (?, ?, ?, ?, {TIMESTAMP_SQL})
            """,
            (member_id, workspace_id, user_id, role),
        )
    row = await fetch_one(
        """
        SELECT m.id, m.workspace_id, m.user_id, m.role, m.joined_at, u.email
        FROM workspace_members m
        LEFT JOIN users u ON u.id = m.user_id
        WHERE m.id = ?
        """,
        (member_id,),
    )
    assert row is not None
    return _serialize_member(row)


async def update_member_role(
    workspace_id: str, *, member_id: str, role: str
) -> dict[str, Any] | None:
    if role not in ROLES:
        raise ValueError(f"Invalid role: {role}")
    existing = await fetch_one(
        "SELECT id FROM workspace_members WHERE id = ? AND workspace_id = ?",
        (member_id, workspace_id),
    )
    if not existing:
        return None
    await execute(
        "UPDATE workspace_members SET role = ? WHERE id = ?",
        (role, member_id),
    )
    row = await fetch_one(
        """
        SELECT m.id, m.workspace_id, m.user_id, m.role, m.joined_at, u.email
        FROM workspace_members m
        LEFT JOIN users u ON u.id = m.user_id
        WHERE m.id = ?
        """,
        (member_id,),
    )
    return _serialize_member(row) if row else None


async def remove_member(workspace_id: str, member_id: str) -> bool:
    existing = await fetch_one(
        "SELECT id FROM workspace_members WHERE id = ? AND workspace_id = ?",
        (member_id, workspace_id),
    )
    if not existing:
        return False
    await execute("DELETE FROM workspace_members WHERE id = ?", (member_id,))
    return True


# ---------- Invitations ----------------------------------------------------


async def create_invitation(
    workspace_id: str,
    *,
    email: str,
    role: str = "viewer",
    invited_by: str | None,
    expires_in_days: int | None = 14,
) -> dict[str, Any]:
    if role not in ROLES:
        raise ValueError(f"Invalid role: {role}")
    email = email.strip().lower()
    if not email:
        raise ValueError("Email cannot be empty.")
    invitation_id = str(uuid.uuid4())
    token = secrets.token_urlsafe(24)
    expires_at = None
    if expires_in_days:
        expires_at = (datetime.now(timezone.utc) + timedelta(days=expires_in_days)).isoformat()
    await execute(
        f"""
        INSERT INTO workspace_invitations
            (id, workspace_id, email, role, invited_by, token, expires_at, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, {TIMESTAMP_SQL})
        """,
        (invitation_id, workspace_id, email, role, invited_by, token, expires_at),
    )
    row = await fetch_one(
        "SELECT * FROM workspace_invitations WHERE id = ?", (invitation_id,)
    )
    assert row is not None
    return _serialize_invitation(row)


async def list_invitations(workspace_id: str) -> list[dict[str, Any]]:
    rows = await fetch_all(
        "SELECT * FROM workspace_invitations WHERE workspace_id = ? ORDER BY created_at DESC",
        (workspace_id,),
    )
    return [_serialize_invitation(r) for r in rows]


async def revoke_invitation(workspace_id: str, invitation_id: str) -> bool:
    existing = await fetch_one(
        "SELECT id FROM workspace_invitations WHERE id = ? AND workspace_id = ?",
        (invitation_id, workspace_id),
    )
    if not existing:
        return False
    await execute("DELETE FROM workspace_invitations WHERE id = ?", (invitation_id,))
    return True


async def accept_invitation(token: str, *, user_id: str) -> dict[str, Any] | None:
    """Consume an invitation token: mark accepted + add member row."""
    row = await fetch_one(
        "SELECT * FROM workspace_invitations WHERE token = ?", (token,)
    )
    if not row:
        return None
    if row.get("accepted_at"):
        return _serialize_invitation(row)
    member = await add_member(
        row["workspace_id"], user_id=user_id, role=row.get("role") or "viewer"
    )
    await execute(
        f"UPDATE workspace_invitations SET accepted_at = {TIMESTAMP_SQL} WHERE id = ?",
        (row["id"],),
    )
    return {**_serialize_invitation(row), "member": member}

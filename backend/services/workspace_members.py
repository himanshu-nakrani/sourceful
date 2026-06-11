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
    """Check if a role meets or exceeds a minimum role level.

    Uses the role hierarchy: viewer < editor < admin < owner.

    Args:
        role: The role to check (None returns False).
        minimum: The minimum required role.

    Returns:
        True if role >= minimum, False otherwise.
    """
    if not role:
        return False
    return _RANK.get(role, -1) >= _RANK.get(minimum, 99)


def _serialize_member(row: dict[str, Any]) -> dict[str, Any]:
    """Serialize a database row to a member dict.

    Args:
        row: The database row dict.

    Returns:
        A serialized member dict with email joined from users table.
    """
    return {
        "id": row["id"],
        "workspace_id": row["workspace_id"],
        "user_id": row["user_id"],
        "email": row.get("email"),
        "role": row.get("role") or "viewer",
        "joined_at": row.get("joined_at"),
    }


def _serialize_invitation(row: dict[str, Any], *, include_token: bool = True) -> dict[str, Any]:
    """Serialize a database row to an invitation dict.

    Args:
        row: The database row dict.

    Returns:
        A serialized invitation dict.
    """
    token = row["token"]
    return {
        "id": row["id"],
        "workspace_id": row["workspace_id"],
        "email": row["email"],
        "role": row.get("role") or "viewer",
        "token": token if include_token else f"{token[:8]}…",
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
    """List all members of a workspace.

    Args:
        workspace_id: The workspace ID.

    Returns:
        A list of serialized member dicts, ordered by joined_at ASC.
    """
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
    """Add a member to a workspace or update their role if already a member.

    Args:
        workspace_id: The workspace ID.
        user_id: The user ID to add.
        role: The role to assign (default: 'viewer').

    Returns:
        The serialized member dict.

    Raises:
        ValueError: If role is not a valid ROLES value.
    """
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
    """Update a member's role in a workspace.

    Args:
        workspace_id: The workspace ID.
        member_id: The member ID to update.
        role: The new role.

    Returns:
        The updated member dict, or None if not found.

    Raises:
        ValueError: If role is not a valid ROLES value.
    """
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
    """Remove a member from a workspace.

    Args:
        workspace_id: The workspace ID.
        member_id: The member ID to remove.

    Returns:
        True if the member was removed, False if not found.
    """
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
    """Create an invitation for a user to join a workspace.

    Args:
        workspace_id: The workspace ID.
        email: The email address to invite.
        role: The role to assign upon acceptance (default: 'viewer').
        invited_by: Optional ID of the user who created the invitation.
        expires_in_days: Days until the invitation expires (default: 14).

    Returns:
        The serialized invitation dict.

    Raises:
        ValueError: If role is invalid or email is empty.
    """
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
    """List pending invitations for a workspace.

    Args:
        workspace_id: The workspace ID.

    Returns:
        A list of serialized invitation dicts, ordered by created_at DESC.
    """
    rows = await fetch_all(
        "SELECT * FROM workspace_invitations WHERE workspace_id = ? ORDER BY created_at DESC",
        (workspace_id,),
    )
    return [_serialize_invitation(r, include_token=False) for r in rows]


async def revoke_invitation(workspace_id: str, invitation_id: str) -> bool:
    """Revoke a pending invitation.

    Args:
        workspace_id: The workspace ID.
        invitation_id: The invitation ID to revoke.

    Returns:
        True if the invitation was revoked, False if not found.
    """
    existing = await fetch_one(
        "SELECT id FROM workspace_invitations WHERE id = ? AND workspace_id = ?",
        (invitation_id, workspace_id),
    )
    if not existing:
        return False
    await execute("DELETE FROM workspace_invitations WHERE id = ?", (invitation_id,))
    return True


def _parse_utc_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00").replace(" ", "T"))
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


async def accept_invitation(token: str, *, user_id: str) -> dict[str, Any] | None:
    """Consume an invitation token: mark accepted + add member row."""
    row = await fetch_one(
        "SELECT * FROM workspace_invitations WHERE token = ?", (token,)
    )
    if not row:
        return None
    if row.get("accepted_at"):
        return _serialize_invitation(row)
    expires_at = _parse_utc_datetime(row.get("expires_at"))
    if expires_at is not None and expires_at <= datetime.now(timezone.utc):
        raise ValueError("INVITATION_EXPIRED")
    member = await add_member(
        row["workspace_id"], user_id=user_id, role=row.get("role") or "viewer"
    )
    await execute(
        f"UPDATE workspace_invitations SET accepted_at = {TIMESTAMP_SQL} WHERE id = ?",
        (row["id"],),
    )
    return {**_serialize_invitation(row), "member": member}

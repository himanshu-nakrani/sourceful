"""Workspace service for multi-tenant document organization."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any



@dataclass
class Workspace:
    id: str
    name: str
    slug: str
    owner_id: str
    settings: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    member_count: int = 0
    document_count: int = 0


@dataclass
class WorkspaceMember:
    id: str
    workspace_id: str
    user_id: str
    role: str  # "owner", "admin", "editor", "viewer"
    joined_at: datetime
    user_email: str | None = None
    user_name: str | None = None


class WorkspaceService:
    """Service for workspace CRUD and member management."""

    ROLES = ["owner", "admin", "editor", "viewer"]
    ROLE_HIERARCHY = {"owner": 4, "admin": 3, "editor": 2, "viewer": 1}

    def __init__(self, db: Any):
        self.db = db

    @staticmethod
    def can_manage_members(actor_role: str, target_role: str | None = None) -> bool:
        """Check if actor can manage (add/remove/change) members."""
        if actor_role not in WorkspaceService.ROLE_HIERARCHY:
            return False
        # Only owner and admin can manage members
        if WorkspaceService.ROLE_HIERARCHY[actor_role] < 3:
            return False
        # Cannot manage someone with equal or higher role
        if target_role and WorkspaceService.ROLE_HIERARCHY.get(target_role, 0) >= WorkspaceService.ROLE_HIERARCHY[actor_role]:
            return False
        return True

    @staticmethod
    def can_edit_documents(role: str) -> bool:
        """Check if role can upload/edit documents."""
        return WorkspaceService.ROLE_HIERARCHY.get(role, 0) >= 2  # editor and above

    @staticmethod
    def can_delete_workspace(role: str) -> bool:
        """Only owner can delete workspace."""
        return role == "owner"

    async def create_workspace(
        self, name: str, owner_id: str, settings: dict[str, Any] | None = None
    ) -> Workspace:
        """Create a new workspace with owner as first member."""
        workspace_id = str(uuid.uuid4())
        slug = self._generate_slug(name)
        now = datetime.now(timezone.utc)

        await self.db.execute(
            """
            INSERT INTO workspaces (id, name, slug, owner_id, settings, created_at, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            """,
            workspace_id, name, slug, owner_id, settings or {}, now, now
        )

        # Add owner as member
        await self.add_member(workspace_id, owner_id, "owner")

        return Workspace(
            id=workspace_id,
            name=name,
            slug=slug,
            owner_id=owner_id,
            settings=settings or {},
            created_at=now,
            updated_at=now,
        )

    async def get_workspace(self, workspace_id: str) -> Workspace | None:
        """Get workspace by ID."""
        row = await self.db.fetchrow(
            """
            SELECT w.*,
                   COUNT(DISTINCT wm.id) as member_count,
                   COUNT(DISTINCT d.id) as document_count
            FROM workspaces w
            LEFT JOIN workspace_members wm ON w.id = wm.workspace_id
            LEFT JOIN documents d ON d.workspace_id = w.id
            WHERE w.id = $1
            GROUP BY w.id
            """,
            workspace_id
        )
        if not row:
            return None
        return self._row_to_workspace(row)

    async def get_workspace_by_slug(self, slug: str) -> Workspace | None:
        """Get workspace by slug."""
        row = await self.db.fetchrow(
            """
            SELECT w.*,
                   COUNT(DISTINCT wm.id) as member_count,
                   COUNT(DISTINCT d.id) as document_count
            FROM workspaces w
            LEFT JOIN workspace_members wm ON w.id = wm.workspace_id
            LEFT JOIN documents d ON d.workspace_id = w.id
            WHERE w.slug = $1
            GROUP BY w.id
            """,
            slug
        )
        if not row:
            return None
        return self._row_to_workspace(row)

    async def list_user_workspaces(self, user_id: str) -> list[Workspace]:
        """List all workspaces where user is a member."""
        rows = await self.db.fetch(
            """
            SELECT w.*,
                   COUNT(DISTINCT wm.id) as member_count,
                   COUNT(DISTINCT d.id) as document_count
            FROM workspaces w
            JOIN workspace_members wm ON w.id = wm.workspace_id
            LEFT JOIN workspace_members wm2 ON w.id = wm2.workspace_id
            LEFT JOIN documents d ON d.workspace_id = w.id
            WHERE wm.user_id = $1
            GROUP BY w.id
            ORDER BY w.updated_at DESC
            """,
            user_id
        )
        return [self._row_to_workspace(r) for r in rows]

    async def update_workspace(
        self, workspace_id: str, updates: dict[str, Any]
    ) -> Workspace | None:
        """Update workspace settings."""
        allowed = {"name", "settings"}
        set_clauses = []
        values = []
        for i, (key, value) in enumerate(updates.items(), start=1):
            if key not in allowed:
                continue
            set_clauses.append(f"{key} = ${i}")
            values.append(value)

        if not set_clauses:
            return await self.get_workspace(workspace_id)

        values.extend([datetime.now(timezone.utc), workspace_id])
        query = f"""
            UPDATE workspaces
            SET {', '.join(set_clauses)}, updated_at = ${len(values) - 1}
            WHERE id = ${len(values)}
            RETURNING *
        """
        row = await self.db.fetchrow(query, *values)
        if row:
            return await self.get_workspace(workspace_id)
        return None

    async def delete_workspace(self, workspace_id: str) -> bool:
        """Delete workspace and all associated data."""
        # Cascade deletes handle related records
        result = await self.db.execute(
            "DELETE FROM workspaces WHERE id = $1",
            workspace_id
        )
        return result != "DELETE 0"

    # Member management

    async def add_member(
        self, workspace_id: str, user_id: str, role: str = "viewer"
    ) -> WorkspaceMember:
        """Add a member to workspace."""
        if role not in self.ROLES:
            raise ValueError(f"Invalid role: {role}")

        member_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        await self.db.execute(
            """
            INSERT INTO workspace_members (id, workspace_id, user_id, role, joined_at)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (workspace_id, user_id) DO UPDATE SET
                role = EXCLUDED.role,
                joined_at = EXCLUDED.joined_at
            """,
            member_id, workspace_id, user_id, role, now
        )

        return WorkspaceMember(
            id=member_id,
            workspace_id=workspace_id,
            user_id=user_id,
            role=role,
            joined_at=now,
        )

    async def remove_member(self, workspace_id: str, user_id: str) -> bool:
        """Remove a member from workspace."""
        result = await self.db.execute(
            "DELETE FROM workspace_members WHERE workspace_id = $1 AND user_id = $2",
            workspace_id, user_id
        )
        return result != "DELETE 0"

    async def update_member_role(
        self, workspace_id: str, user_id: str, new_role: str
    ) -> WorkspaceMember | None:
        """Update member's role."""
        if new_role not in self.ROLES:
            raise ValueError(f"Invalid role: {new_role}")

        await self.db.execute(
            """
            UPDATE workspace_members
            SET role = $1
            WHERE workspace_id = $2 AND user_id = $3
            """,
            new_role, workspace_id, user_id
        )

        row = await self.db.fetchrow(
            """
            SELECT wm.*, u.email as user_email, u.full_name as user_name
            FROM workspace_members wm
            JOIN users u ON wm.user_id = u.id
            WHERE wm.workspace_id = $1 AND wm.user_id = $2
            """,
            workspace_id, user_id
        )
        if row:
            return self._row_to_member(row)
        return None

    async def get_member(
        self, workspace_id: str, user_id: str
    ) -> WorkspaceMember | None:
        """Get member info for a user in workspace."""
        row = await self.db.fetchrow(
            """
            SELECT wm.*, u.email as user_email, u.full_name as user_name
            FROM workspace_members wm
            JOIN users u ON wm.user_id = u.id
            WHERE wm.workspace_id = $1 AND wm.user_id = $2
            """,
            workspace_id, user_id
        )
        if row:
            return self._row_to_member(row)
        return None

    async def list_members(self, workspace_id: str) -> list[WorkspaceMember]:
        """List all members of workspace."""
        rows = await self.db.fetch(
            """
            SELECT wm.*, u.email as user_email, u.full_name as user_name
            FROM workspace_members wm
            JOIN users u ON wm.user_id = u.id
            WHERE wm.workspace_id = $1
            ORDER BY wm.joined_at ASC
            """,
            workspace_id
        )
        return [self._row_to_member(r) for r in rows]

    # Helpers

    def _generate_slug(self, name: str) -> str:
        """Generate URL-friendly slug from name."""
        import re
        base = re.sub(r'[^\w\s-]', '', name.lower())
        base = re.sub(r'[-\s]+', '-', base).strip('-')
        return f"{base}-{str(uuid.uuid4())[:8]}"

    def _row_to_workspace(self, row: Any) -> Workspace:
        return Workspace(
            id=row["id"],
            name=row["name"],
            slug=row["slug"],
            owner_id=row["owner_id"],
            settings=row.get("settings", {}),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            member_count=row.get("member_count", 0),
            document_count=row.get("document_count", 0),
        )

    def _row_to_member(self, row: Any) -> WorkspaceMember:
        return WorkspaceMember(
            id=row["id"],
            workspace_id=row["workspace_id"],
            user_id=row["user_id"],
            role=row["role"],
            joined_at=row["joined_at"],
            user_email=row.get("user_email"),
            user_name=row.get("user_name"),
        )

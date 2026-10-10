"use client";

import React, { useEffect, useState, useMemo } from "react";
import { useOnChange } from "../lib/use-on-change";
import { Check, Copy, Loader2, Trash2, Users, X } from "lucide-react";
import {
  addWorkspaceMember,
  createWorkspaceInvitation,
  listWorkspaceInvitations,
  listWorkspaceMembers,
  removeWorkspaceMember,
  revokeWorkspaceInvitation,
  updateWorkspaceMember,
  type ClientAuthContext,
  type WorkspaceInvitation,
  type WorkspaceMember,
  type WorkspaceRole,
} from "../lib/api";
import { useWorkspaceRole } from "../lib/use-workspace-role";
import { Button, ConfirmDialog, EmptyState, ErrorBanner, Modal, SelectField, TextField } from "./ui";

interface WorkspaceMembersPanelProps {
  open: boolean;
  onClose: () => void;
  workspaceId: string;
  workspaceName: string;
  auth: ClientAuthContext;
}

const ROLE_OPTIONS: WorkspaceRole[] = ["owner", "admin", "editor", "viewer"];

const ROLE_SELECT_OPTIONS = ROLE_OPTIONS.map((role) => ({ value: role, label: role }));

/** Eyebrow label for the two panel sections. */
function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <h3
      className="text-[10px] font-medium uppercase tracking-widest mb-2"
      style={{ color: "var(--text-tertiary)" }}
    >
      {children}
    </h3>
  );
}

/**
 * Phase 3: workspace members + invitations management.
 *
 * The panel adapts to the auth context: anonymous (session-only) workspaces
 * have no real users to invite, so we surface a guidance message and disable
 * the invite form. Authenticated workspaces get the full add-member,
 * change-role, remove-member, and create/revoke-invitation flow.
 */
export default function WorkspaceMembersPanel({
  open,
  onClose,
  workspaceId,
  workspaceName,
  auth,
}: WorkspaceMembersPanelProps) {

  const [members, setMembers] = useState<WorkspaceMember[]>([]);
  const [invitations, setInvitations] = useState<WorkspaceInvitation[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // Phase 3: role-aware UI disabling via backend-resolved role.
  const { canManage } = useWorkspaceRole(auth, workspaceId);

  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState<WorkspaceRole>("editor");
  const [memberUserId, setMemberUserId] = useState("");
  const [memberRole, setMemberRole] = useState<WorkspaceRole>("editor");
  const [copiedToken, setCopiedToken] = useState<string | null>(null);
  const [pendingAction, setPendingAction] = useState<
    | { kind: "remove"; member: WorkspaceMember }
    | { kind: "revoke"; invitation: WorkspaceInvitation }
    | null
  >(null);


  // One key per load request: set while the panel is open, and replaced when
  // its inputs change (same triggers as before). The spinner/error reset is
  // applied during render; the request runs in the effect and only sets state
  // after it resolves.
  const loadRequest = useMemo(
    () => (open ? { auth, workspaceId } : null),
    [open, auth, workspaceId],
  );
  useOnChange(loadRequest, (request) => {
    if (request) {
      setLoading(true);
      setError(null);
    }
  });
  useEffect(() => {
    if (!loadRequest) return;
    const { auth, workspaceId } = loadRequest;
    const run = async () => {
      try {
        const [mem, inv] = await Promise.all([
          listWorkspaceMembers(auth, workspaceId),
          listWorkspaceInvitations(auth, workspaceId).catch(() => []),
        ]);
        setMembers(mem);
        setInvitations(inv);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load members.");
      } finally {
        setLoading(false);
      }
    };
    void run();
  }, [loadRequest]);

  const handleAddMember = async () => {
    if (!memberUserId.trim()) {
      setError("User ID is required.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const created = await addWorkspaceMember(auth, workspaceId, {
        user_id: memberUserId.trim(),
        role: memberRole,
      });
      setMembers((prev) => {
        const without = prev.filter((m) => m.id !== created.id);
        return [...without, created];
      });
      setMemberUserId("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to add member.");
    } finally {
      setBusy(false);
    }
  };

  const handleRoleChange = async (member: WorkspaceMember, role: WorkspaceRole) => {
    if (!canManage) return;
    setBusy(true);
    setError(null);
    try {
      const updated = await updateWorkspaceMember(
        auth,
        workspaceId,
        member.id,
        role
      );
      setMembers((prev) => prev.map((m) => (m.id === updated.id ? updated : m)));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update role.");
    } finally {
      setBusy(false);
    }
  };

  const handleRemoveMember = (member: WorkspaceMember) => {
    if (!canManage) return;
    setPendingAction({ kind: "remove", member });
  };

  const handleInvite = async () => {
    if (!inviteEmail.trim()) {
      setError("Email is required.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const created = await createWorkspaceInvitation(auth, workspaceId, {
        email: inviteEmail.trim(),
        role: inviteRole,
      });
      setInvitations((prev) => [created, ...prev]);
      setInviteEmail("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create invitation.");
    } finally {
      setBusy(false);
    }
  };

  const handleRevoke = (invitation: WorkspaceInvitation) => {
    if (!canManage) return;
    setPendingAction({ kind: "revoke", invitation });
  };

  const confirmPendingAction = async () => {
    if (!pendingAction) return;
    setBusy(true);
    setError(null);
    try {
      if (pendingAction.kind === "remove") {
        await removeWorkspaceMember(auth, workspaceId, pendingAction.member.id);
        setMembers((prev) => prev.filter((m) => m.id !== pendingAction.member.id));
      } else {
        await revokeWorkspaceInvitation(auth, workspaceId, pendingAction.invitation.id);
        setInvitations((prev) => prev.filter((i) => i.id !== pendingAction.invitation.id));
      }
      setPendingAction(null);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : pendingAction.kind === "remove"
            ? "Failed to remove member."
            : "Failed to revoke invitation.",
      );
    } finally {
      setBusy(false);
    }
  };

  const copyToken = async (token: string) => {
    try {
      await navigator.clipboard.writeText(token);
      setCopiedToken(token);
      setTimeout(() => setCopiedToken(null), 1500);
    } catch {
      // Older browsers without async clipboard — ignore.
    }
  };

  return (
    <>
    <Modal
      open={open}
      onClose={onClose}
      busy={busy}
      title="Workspace members"
      width={680}
      height="min(640px, 86vh)"
      align="top"
    >
      <div className="flex flex-col h-full min-h-0">
        <header
          className="flex items-center justify-between gap-3 px-5 py-3.5 flex-shrink-0"
          style={{ borderBottom: "1px solid var(--border)" }}
        >
          <div className="flex items-baseline gap-2.5 min-w-0">
            <h2 className="display text-[15px] font-semibold truncate">Workspace members</h2>
            <span
              className="text-[10px] uppercase tracking-widest truncate"
              style={{ color: "var(--text-muted)" }}
            >
              {workspaceName}
            </span>
          </div>
          <Button variant="ghost" size="sm" onClick={onClose} aria-label="Close members panel">
            <X size={14} />
          </Button>
        </header>

        {error ? (
          <div className="px-4 pt-3 flex-shrink-0">
            <ErrorBanner message={error} />
          </div>
        ) : null}

        {!canManage ? (
          <div className="px-4 pt-3 flex-shrink-0">
            <p
              className="text-[11px] leading-relaxed px-3 py-2.5 rounded-lg"
              style={{
                background: "var(--bg-surface)",
                border: "1px solid var(--border)",
                color: "var(--text-tertiary)",
              }}
            >
              You don&rsquo;t have permission to manage members. Contact a workspace
              owner or admin for access.
            </p>
          </div>
        ) : null}

        <div className="flex-1 min-h-0 overflow-y-auto px-4 py-4 flex flex-col gap-6">
          {/* Members section */}
          <section>
            <SectionLabel>Members</SectionLabel>
            {loading && members.length === 0 ? (
              <div
                className="flex items-center gap-2 text-[11px]"
                style={{ color: "var(--text-muted)" }}
              >
                <Loader2 size={11} className="animate-spin" /> Loading members…
              </div>
            ) : null}
            {!loading && members.length === 0 ? (
              <EmptyState
                icon={<Users size={16} />}
                title="No additional members"
                description="The workspace owner has full access by default."
              />
            ) : null}
            <ul className="flex flex-col gap-2">
              {members.map((member) => (
                <li
                  key={member.id}
                  className="flex items-center gap-3 px-3.5 py-2.5 rounded-lg"
                  style={{
                    background: "var(--bg-surface)",
                    border: "1px solid var(--border)",
                  }}
                >
                  <div className="flex-1 min-w-0">
                    <div className="text-[13px] font-medium truncate">
                      {member.email || member.user_id}
                    </div>
                    <div
                      className="data-num text-[10px] truncate"
                      style={{ color: "var(--text-muted)" }}
                    >
                      {member.user_id}
                    </div>
                  </div>
                  {canManage ? (
                    <SelectField
                      label="Role"
                      aria-label={`Role for ${member.email || member.user_id}`}
                      className="[&_label]:sr-only w-28 flex-shrink-0"
                      options={ROLE_SELECT_OPTIONS}
                      value={member.role}
                      disabled={busy}
                      onChange={(e) =>
                        void handleRoleChange(member, e.target.value as WorkspaceRole)
                      }
                    />
                  ) : (
                    <span
                      className="text-[13px] w-28 flex-shrink-0 capitalize"
                      style={{ color: "var(--text-secondary)" }}
                    >
                      {member.role}
                    </span>
                  )}
                  {canManage ? (
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => handleRemoveMember(member)}
                      disabled={busy}
                      style={{ color: "var(--error)" }}
                      title="Remove member"
                      aria-label="Remove member"
                      className="flex-shrink-0"
                    >
                      <Trash2 size={13} />
                    </Button>
                  ) : null}
                </li>
              ))}
            </ul>

            {canManage ? (
              <div className="mt-3 flex flex-wrap items-end gap-2">
                <TextField
                  label="User ID"
                  placeholder="User ID"
                  className="flex-1 min-w-[180px]"
                  value={memberUserId}
                  onChange={(e) => setMemberUserId(e.target.value)}
                />
                <SelectField
                  label="Role"
                  className="w-28"
                  options={ROLE_SELECT_OPTIONS}
                  value={memberRole}
                  onChange={(e) => setMemberRole(e.target.value as WorkspaceRole)}
                />
                <Button variant="secondary" size="md" onClick={() => void handleAddMember()} disabled={busy}>
                  Add member
                </Button>
              </div>
            ) : null}
          </section>

          {/* Invitations section */}
          <section>
            <SectionLabel>Pending invitations</SectionLabel>
            {loading && invitations.length === 0 ? null : invitations.length === 0 ? (
              <div className="text-[11px]" style={{ color: "var(--text-muted)" }}>
                No pending invitations.
              </div>
            ) : null}
            <ul className="flex flex-col gap-2">
              {invitations.map((invitation) => (
                <li
                  key={invitation.id}
                  className="flex items-center gap-3 px-3.5 py-2.5 rounded-lg"
                  style={{
                    background: "var(--bg-surface)",
                    border: "1px solid var(--border)",
                  }}
                >
                  <div className="flex-1 min-w-0">
                    <div className="text-[13px] font-medium truncate">
                      {invitation.email}
                    </div>
                    <div
                      className="text-[10px] flex items-center gap-1.5 min-w-0"
                      style={{ color: "var(--text-muted)" }}
                    >
                      <span className="uppercase tracking-widest flex-shrink-0">
                        {invitation.role}
                      </span>
                      <span>{invitation.accepted_at ? "accepted" : "pending"}</span>
                      {invitation.expires_at ? (
                        <span className="truncate">
                          expires{" "}
                          <span className="data-num">
                            {new Date(invitation.expires_at).toLocaleDateString()}
                          </span>
                        </span>
                      ) : null}
                      <span
                        className="data-num text-[10px] truncate px-1 rounded-sm flex-1 min-w-0"
                        title={invitation.token}
                        style={{
                          background: "var(--bg-primary)",
                          border: "1px solid var(--border)",
                          color: "var(--text-tertiary)",
                        }}
                      >
                        {invitation.token}
                      </span>
                    </div>
                  </div>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => void copyToken(invitation.token)}
                    disabled={busy}
                    title="Copy invitation token"
                    className="flex-shrink-0"
                  >
                    {copiedToken === invitation.token ? (
                      <Check size={11} style={{ color: "var(--success)" }} />
                    ) : (
                      <Copy size={11} />
                    )}
                    {copiedToken === invitation.token ? "Copied" : "Copy"}
                  </Button>
                  {canManage ? (
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => handleRevoke(invitation)}
                      disabled={busy}
                      style={{ color: "var(--error)" }}
                      title="Revoke invitation"
                      aria-label="Revoke invitation"
                      className="flex-shrink-0"
                    >
                      <Trash2 size={13} />
                    </Button>
                  ) : null}
                </li>
              ))}
            </ul>

            {canManage ? (
              <div className="mt-3 flex flex-wrap items-end gap-2">
                <TextField
                  label="Email"
                  placeholder="teammate@example.com"
                  type="email"
                  className="flex-1 min-w-[200px]"
                  value={inviteEmail}
                  onChange={(e) => setInviteEmail(e.target.value)}
                />
                <SelectField
                  label="Role"
                  className="w-28"
                  options={ROLE_SELECT_OPTIONS}
                  value={inviteRole}
                  onChange={(e) => setInviteRole(e.target.value as WorkspaceRole)}
                />
                <Button variant="primary" size="md" onClick={() => void handleInvite()} disabled={busy}>
                  Create invitation
                </Button>
              </div>
            ) : null}
          </section>
        </div>
      </div>
    </Modal>
    <ConfirmDialog
      open={pendingAction !== null}
      title={pendingAction?.kind === "revoke" ? "Revoke invitation" : "Remove member"}
      message={
        pendingAction?.kind === "revoke"
          ? `Revoke invitation for ${pendingAction.invitation.email}?`
          : pendingAction?.kind === "remove"
            ? `Remove ${pendingAction.member.email ?? pendingAction.member.user_id} from this workspace?`
            : ""
      }
      confirmLabel={pendingAction?.kind === "revoke" ? "Revoke" : "Remove"}
      danger
      busy={busy}
      onConfirm={() => void confirmPendingAction()}
      onCancel={() => {
        if (!busy) setPendingAction(null);
      }}
    />
    </>
  );
}

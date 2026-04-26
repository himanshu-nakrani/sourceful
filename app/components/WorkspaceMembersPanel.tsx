"use client";

import React, { useCallback, useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Copy, Loader2, Trash2, Users, X } from "lucide-react";
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
import { EASE_OUT } from "../lib/motion";

interface WorkspaceMembersPanelProps {
  open: boolean;
  onClose: () => void;
  workspaceId: string;
  workspaceName: string;
  auth: ClientAuthContext;
}

const ROLE_OPTIONS: WorkspaceRole[] = ["owner", "admin", "editor", "viewer"];

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
  const isAnonymous = !auth.clientSessionId
    ? false
    : !((auth as { authToken?: string }).authToken);
  const [members, setMembers] = useState<WorkspaceMember[]>([]);
  const [invitations, setInvitations] = useState<WorkspaceInvitation[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // Phase 3: role-aware UI disabling via backend-resolved role.
  const { role: currentUserRole, canManage } = useWorkspaceRole(auth, workspaceId);

  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState<WorkspaceRole>("editor");
  const [memberUserId, setMemberUserId] = useState("");
  const [memberRole, setMemberRole] = useState<WorkspaceRole>("editor");
  const [copiedToken, setCopiedToken] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!open) return;
    setLoading(true);
    setError(null);
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
  }, [auth, workspaceId, open]);

  useEffect(() => {
    if (open) void refresh();
  }, [open, refresh]);

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

  const handleRemoveMember = async (member: WorkspaceMember) => {
    if (!window.confirm(`Remove ${member.email ?? member.user_id} from this workspace?`)) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await removeWorkspaceMember(auth, workspaceId, member.id);
      setMembers((prev) => prev.filter((m) => m.id !== member.id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to remove member.");
    } finally {
      setBusy(false);
    }
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

  const handleRevoke = async (invitation: WorkspaceInvitation) => {
    if (!window.confirm(`Revoke invitation for ${invitation.email}?`)) return;
    setBusy(true);
    setError(null);
    try {
      await revokeWorkspaceInvitation(auth, workspaceId, invitation.id);
      setInvitations((prev) => prev.filter((i) => i.id !== invitation.id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to revoke invitation.");
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
    <AnimatePresence>
      {open ? (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.18, ease: EASE_OUT }}
          className="fixed inset-0 z-50 flex items-center justify-center"
          style={{ background: "rgba(0,0,0,0.5)" }}
          onMouseDown={(e) => {
            if (e.target === e.currentTarget) onClose();
          }}
        >
          <motion.div
            initial={{ opacity: 0, scale: 0.96 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.96 }}
            transition={{ duration: 0.2, ease: EASE_OUT }}
            className="w-[min(820px,94vw)] h-[min(680px,86vh)] flex flex-col rounded-2xl overflow-hidden"
            style={{
              background: "var(--bg-primary)",
              border: "1px solid var(--border)",
              boxShadow: "0 24px 48px rgba(0,0,0,0.35)",
            }}
          >
            <header
              className="flex items-center justify-between px-4 py-3 flex-shrink-0"
              style={{ borderBottom: "1px solid var(--border)" }}
            >
              <div className="flex items-center gap-2">
                <Users size={14} style={{ color: "var(--accent-brand)" }} />
                <h2 className="text-sm font-semibold">Members &amp; invitations</h2>
                <span
                  className="text-[10px] uppercase tracking-widest"
                  style={{ color: "var(--text-muted)" }}
                >
                  {workspaceName}
                </span>
              </div>
              <button
                type="button"
                onClick={onClose}
                className="p-1.5 rounded-lg"
                style={{ color: "var(--text-muted)" }}
                aria-label="Close members panel"
              >
                <X size={14} />
              </button>
            </header>

            {error ? (
              <div
                className="px-4 py-2 text-[11px] flex-shrink-0"
                style={{ background: "var(--error-soft)", color: "var(--error)" }}
              >
                {error}
              </div>
            ) : null}

            {isAnonymous ? (
              <div
                className="px-4 py-3 text-[11px] flex-shrink-0"
                style={{
                  background: "var(--bg-surface)",
                  color: "var(--text-muted)",
                  borderBottom: "1px solid var(--border)",
                }}
              >
                You&rsquo;re using an anonymous session. Members and invitations apply to
                authenticated workspaces only — sign in to share this workspace with
                teammates.
              </div>
            ) : null}

            <div className="flex-1 min-h-0 overflow-y-auto px-4 py-4 flex flex-col gap-6">
              {/* Members section */}
              <section>
                <h3 className="text-xs font-semibold mb-2">Members</h3>
                {loading && members.length === 0 ? (
                  <div
                    className="flex items-center gap-2 text-[11px]"
                    style={{ color: "var(--text-muted)" }}
                  >
                    <Loader2 size={11} className="animate-spin" /> Loading members…
                  </div>
                ) : null}
                {!loading && members.length === 0 ? (
                  <div className="text-[11px]" style={{ color: "var(--text-muted)" }}>
                    No additional members. The workspace owner has full access by
                    default.
                  </div>
                ) : null}
                <ul className="flex flex-col gap-1">
                  {members.map((member) => (
                    <li
                      key={member.id}
                      className="flex items-center gap-2 px-3 py-2 rounded-lg"
                      style={{
                        background: "var(--bg-surface)",
                        border: "1px solid var(--border)",
                      }}
                    >
                      <div className="flex-1 min-w-0">
                        <div className="text-xs font-medium truncate">
                          {member.email || member.user_id}
                        </div>
                        <div
                          className="text-[10px] truncate"
                          style={{ color: "var(--text-muted)" }}
                        >
                          {member.user_id}
                        </div>
                      </div>
                      <select
                        value={member.role}
                        onChange={(e) =>
                          void handleRoleChange(member, e.target.value as WorkspaceRole)
                        }
                        disabled={busy}
                        className="text-[11px] px-2 py-1 rounded-md outline-none"
                        style={{
                          background: "var(--bg-primary)",
                          color: "var(--text-primary)",
                          border: "1px solid var(--border)",
                        }}
                      >
                        {ROLE_OPTIONS.map((role) => (
                          <option key={role} value={role}>
                            {role}
                          </option>
                        ))}
                      </select>
                      <button
                        type="button"
                        onClick={() => void handleRemoveMember(member)}
                        disabled={busy}
                        className="p-1.5 rounded-md"
                        style={{ color: "var(--error)" }}
                        title="Remove member"
                      >
                        <Trash2 size={13} />
                      </button>
                    </li>
                  ))}
                </ul>

                {!isAnonymous ? (
                  <div className="mt-3 flex flex-wrap items-center gap-2">
                    <input
                      value={memberUserId}
                      onChange={(e) => setMemberUserId(e.target.value)}
                      placeholder="User ID"
                      className="flex-1 min-w-[180px] bg-transparent text-xs outline-none rounded-lg px-2 py-1.5"
                      style={{
                        color: "var(--text-primary)",
                        background: "var(--bg-surface)",
                        border: "1px solid var(--border)",
                      }}
                    />
                    <select
                      value={memberRole}
                      onChange={(e) => setMemberRole(e.target.value as WorkspaceRole)}
                      className="text-xs px-2 py-1.5 rounded-lg outline-none"
                      style={{
                        color: "var(--text-primary)",
                        background: "var(--bg-surface)",
                        border: "1px solid var(--border)",
                      }}
                    >
                      {ROLE_OPTIONS.map((role) => (
                        <option key={role} value={role}>
                          {role}
                        </option>
                      ))}
                    </select>
                    <motion.button
                      type="button"
                      onClick={() => void handleAddMember()}
                      disabled={busy}
                      whileTap={{ scale: 0.97 }}
                      className="px-3 py-1.5 rounded-lg text-xs font-medium"
                      style={{
                        background: busy ? "var(--bg-elevated)" : "var(--accent)",
                        color: busy ? "var(--text-muted)" : "var(--accent-fg)",
                      }}
                    >
                      Add member
                    </motion.button>
                  </div>
                ) : null}
              </section>

              {/* Invitations section */}
              <section>
                <h3 className="text-xs font-semibold mb-2">Pending invitations</h3>
                {loading && invitations.length === 0 ? null : invitations.length === 0 ? (
                  <div className="text-[11px]" style={{ color: "var(--text-muted)" }}>
                    No pending invitations.
                  </div>
                ) : null}
                <ul className="flex flex-col gap-1">
                  {invitations.map((invitation) => (
                    <li
                      key={invitation.id}
                      className="flex items-center gap-2 px-3 py-2 rounded-lg"
                      style={{
                        background: "var(--bg-surface)",
                        border: "1px solid var(--border)",
                      }}
                    >
                      <div className="flex-1 min-w-0">
                        <div className="text-xs font-medium truncate">
                          {invitation.email}
                        </div>
                        <div
                          className="text-[10px] truncate"
                          style={{ color: "var(--text-muted)" }}
                        >
                          {invitation.role}
                          {invitation.accepted_at ? " · accepted" : " · pending"}
                          {invitation.expires_at
                            ? ` · expires ${new Date(invitation.expires_at).toLocaleDateString()}`
                            : ""}
                        </div>
                      </div>
                      <button
                        type="button"
                        onClick={() => void copyToken(invitation.token)}
                        disabled={busy}
                        className="text-[11px] px-2 py-1 rounded-md flex items-center gap-1"
                        style={{
                          color: "var(--text-muted)",
                          background: "var(--bg-primary)",
                          border: "1px solid var(--border)",
                        }}
                        title="Copy invitation token"
                      >
                        <Copy size={11} />
                        {copiedToken === invitation.token ? "Copied" : "Token"}
                      </button>
                      <button
                        type="button"
                        onClick={() => void handleRevoke(invitation)}
                        disabled={busy}
                        className="p-1.5 rounded-md"
                        style={{ color: "var(--error)" }}
                        title="Revoke invitation"
                      >
                        <Trash2 size={13} />
                      </button>
                    </li>
                  ))}
                </ul>

                {!isAnonymous ? (
                  <div className="mt-3 flex flex-wrap items-center gap-2">
                    <input
                      value={inviteEmail}
                      onChange={(e) => setInviteEmail(e.target.value)}
                      placeholder="teammate@example.com"
                      type="email"
                      className="flex-1 min-w-[200px] bg-transparent text-xs outline-none rounded-lg px-2 py-1.5"
                      style={{
                        color: "var(--text-primary)",
                        background: "var(--bg-surface)",
                        border: "1px solid var(--border)",
                      }}
                    />
                    <select
                      value={inviteRole}
                      onChange={(e) => setInviteRole(e.target.value as WorkspaceRole)}
                      className="text-xs px-2 py-1.5 rounded-lg outline-none"
                      style={{
                        color: "var(--text-primary)",
                        background: "var(--bg-surface)",
                        border: "1px solid var(--border)",
                      }}
                    >
                      {ROLE_OPTIONS.map((role) => (
                        <option key={role} value={role}>
                          {role}
                        </option>
                      ))}
                    </select>
                    <motion.button
                      type="button"
                      onClick={() => void handleInvite()}
                      disabled={busy}
                      whileTap={{ scale: 0.97 }}
                      className="px-3 py-1.5 rounded-lg text-xs font-medium"
                      style={{
                        background: busy ? "var(--bg-elevated)" : "var(--accent)",
                        color: busy ? "var(--text-muted)" : "var(--accent-fg)",
                      }}
                    >
                      Invite
                    </motion.button>
                  </div>
                ) : null}
              </section>
            </div>
          </motion.div>
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}

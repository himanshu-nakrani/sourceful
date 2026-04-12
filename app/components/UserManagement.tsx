"use client";

import React from "react";
import { Loader2, RefreshCcw, Shield, ShieldCheck, UserCheck, UserX, Users } from "lucide-react";

import { listUsers, updateUser, type AuthUser } from "../lib/api";
import { useStore } from "../lib/store";

export default function UserManagement() {
  const { state } = useStore();
  const [users, setUsers] = React.useState<AuthUser[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [actionLoading, setActionLoading] = React.useState<string | null>(null);

  const load = React.useCallback(async () => {
    setLoading(true);
    try {
      setUsers(await listUsers());
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load users.");
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    void load();
  }, [load]);

  const handleToggleActive = async (user: AuthUser) => {
    setActionLoading(user.id);
    try {
      const next = await updateUser(user.id, { is_active: !user.is_active });
      setUsers((current) => current.map((u) => (u.id === next.id ? next : u)));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to update user.");
    } finally {
      setActionLoading(null);
    }
  };

  const handleToggleRole = async (user: AuthUser) => {
    const nextRole = user.role === "admin" ? "user" : "admin";
    setActionLoading(user.id);
    try {
      const next = await updateUser(user.id, { role: nextRole });
      setUsers((current) => current.map((u) => (u.id === next.id ? next : u)));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to update role.");
    } finally {
      setActionLoading(null);
    }
  };

  const isAdmin = state.currentUser?.role === "admin";
  const activeCount = users.filter((u) => u.is_active).length;
  const adminCount = users.filter((u) => u.role === "admin").length;

  return (
    <div className="flex-1 overflow-y-auto px-4 py-6" style={{ background: "var(--bg-primary)" }}>
      <div className="mx-auto flex max-w-4xl flex-col gap-6 animate-fade-in">
        {/* Header */}
        <div
          className="rounded-[28px] border px-5 sm:px-6 py-6"
          style={{
            borderColor: "var(--border)",
            background:
              "radial-gradient(circle at top right, rgba(139,92,246,0.15), transparent 32%), linear-gradient(180deg, var(--bg-secondary), var(--bg-primary))",
          }}
        >
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <p className="text-xs font-semibold uppercase tracking-wider" style={{ color: "var(--text-tertiary)" }}>
                Administration
              </p>
              <h2 className="mt-2 text-xl sm:text-2xl font-semibold" style={{ color: "var(--text-primary)" }}>
                User Management
              </h2>
              <p className="mt-2 max-w-2xl text-sm" style={{ color: "var(--text-secondary)" }}>
                View, activate, deactivate, and manage roles for all registered users in the workspace.
              </p>
            </div>
            <button
              type="button"
              onClick={() => void load()}
              className="inline-flex items-center gap-2 rounded-lg px-3 py-2 text-sm"
              style={{ border: "1px solid var(--border)", background: "var(--bg-surface)", color: "var(--text-primary)" }}
            >
              <RefreshCcw size={14} className={loading ? "animate-spin" : ""} />
              Refresh
            </button>
          </div>
        </div>

        {/* Stats row */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <StatCard icon={<Users size={16} />} label="Total Users" value={users.length} />
          <StatCard icon={<UserCheck size={16} />} label="Active" value={activeCount} />
          <StatCard icon={<ShieldCheck size={16} />} label="Admins" value={adminCount} />
        </div>

        {error ? (
          <div className="rounded-xl px-4 py-3 text-sm" style={{ background: "var(--error-soft)", color: "var(--error)" }}>
            {error}
          </div>
        ) : null}

        {/* User table */}
        <div
          className="rounded-2xl border overflow-hidden"
          style={{ borderColor: "var(--border)", background: "var(--bg-surface)" }}
        >
          {/* Table header */}
          <div
            className="hidden sm:grid grid-cols-[1fr_100px_100px_120px] gap-4 px-5 py-3 text-xs font-semibold uppercase tracking-wider"
            style={{ borderBottom: "1px solid var(--border)", color: "var(--text-tertiary)", background: "var(--bg-secondary)" }}
          >
            <span>Email</span>
            <span>Role</span>
            <span>Status</span>
            <span className="text-right">Actions</span>
          </div>

          {loading ? (
            <div className="flex items-center justify-center gap-2 py-12" style={{ color: "var(--text-tertiary)" }}>
              <Loader2 size={16} className="animate-spin" />
              Loading users…
            </div>
          ) : users.length === 0 ? (
            <div className="py-12 text-center text-sm" style={{ color: "var(--text-tertiary)" }}>
              No users found.
            </div>
          ) : (
            users.map((user) => (
              <div
                key={user.id}
                className="flex flex-col sm:grid sm:grid-cols-[1fr_100px_100px_120px] gap-2 sm:gap-4 px-5 py-4 items-start sm:items-center"
                style={{ borderBottom: "1px solid var(--border)" }}
              >
                <div className="min-w-0">
                  <p className="text-sm font-medium truncate" style={{ color: "var(--text-primary)" }}>
                    {user.email}
                  </p>
                  <p className="text-xs mt-0.5 sm:hidden" style={{ color: "var(--text-tertiary)" }}>
                    {user.role} · {user.is_active ? "Active" : "Disabled"}
                  </p>
                </div>
                <div className="hidden sm:block">
                  <span
                    className="inline-flex items-center gap-1 text-xs px-2 py-1 rounded-full"
                    style={{
                      background: user.role === "admin" ? "rgba(139,92,246,0.12)" : "var(--accent-soft)",
                      color: user.role === "admin" ? "#a78bfa" : "var(--text-secondary)",
                    }}
                  >
                    {user.role === "admin" ? <Shield size={10} /> : null}
                    {user.role}
                  </span>
                </div>
                <div className="hidden sm:block">
                  <span
                    className="inline-flex items-center gap-1 text-xs px-2 py-1 rounded-full"
                    style={{
                      background: user.is_active ? "var(--success-soft)" : "var(--error-soft)",
                      color: user.is_active ? "var(--success)" : "var(--error)",
                    }}
                  >
                    <span className="h-1.5 w-1.5 rounded-full" style={{ background: "currentColor" }} />
                    {user.is_active ? "Active" : "Disabled"}
                  </span>
                </div>
                <div className="flex items-center gap-2 sm:justify-end">
                  {isAdmin ? (
                    <>
                      <button
                        type="button"
                        disabled={actionLoading === user.id}
                        onClick={() => void handleToggleActive(user)}
                        className="px-2.5 py-1.5 rounded-lg text-xs inline-flex items-center gap-1"
                        style={{
                          border: "1px solid var(--border)",
                          background: "var(--bg-secondary)",
                          color: user.is_active ? "var(--error)" : "var(--success)",
                        }}
                        title={user.is_active ? "Disable user" : "Enable user"}
                      >
                        {user.is_active ? <UserX size={12} /> : <UserCheck size={12} />}
                        {user.is_active ? "Disable" : "Enable"}
                      </button>
                      <button
                        type="button"
                        disabled={actionLoading === user.id}
                        onClick={() => void handleToggleRole(user)}
                        className="px-2.5 py-1.5 rounded-lg text-xs inline-flex items-center gap-1"
                        style={{
                          border: "1px solid var(--border)",
                          background: "var(--bg-secondary)",
                          color: "var(--text-secondary)",
                        }}
                        title={user.role === "admin" ? "Demote to user" : "Promote to admin"}
                      >
                        <Shield size={12} />
                        {user.role === "admin" ? "Demote" : "Promote"}
                      </button>
                    </>
                  ) : (
                    <span className="text-xs" style={{ color: "var(--text-muted)" }}>—</span>
                  )}
                </div>
              </div>
            ))
          )}
        </div>

        {!isAdmin ? (
          <div
            className="rounded-xl px-4 py-3 text-sm"
            style={{ background: "var(--warning-soft)", color: "var(--warning)" }}
          >
            You need admin privileges to manage users. Contact your workspace administrator.
          </div>
        ) : null}
      </div>
    </div>
  );
}

function StatCard({ icon, label, value }: { icon: React.ReactNode; label: string; value: number }) {
  return (
    <div
      className="rounded-2xl border px-4 py-4"
      style={{ borderColor: "var(--border)", background: "var(--bg-surface)" }}
    >
      <div className="flex items-center justify-between">
        <span className="text-sm" style={{ color: "var(--text-secondary)" }}>{label}</span>
        <span style={{ color: "var(--accent-brand)" }}>{icon}</span>
      </div>
      <p className="mt-3 text-3xl font-semibold" style={{ color: "var(--text-primary)" }}>{value}</p>
    </div>
  );
}

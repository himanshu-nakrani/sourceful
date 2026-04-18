"use client";

import React from "react";
import { motion } from "framer-motion";
import { Loader2, RefreshCcw, Shield, ShieldCheck, UserCheck, UserX, Users } from "lucide-react";

import { listUsers, updateUser, type AuthUser } from "../lib/api";
import { useStore } from "../lib/store";

const container = {
  hidden: { opacity: 0 },
  show: { opacity: 1, transition: { staggerChildren: 0.06, delayChildren: 0.1 } },
};

const fadeUp = {
  hidden: { opacity: 0, y: 12 },
  show: { opacity: 1, y: 0, transition: { duration: 0.4, ease: [0.22, 1, 0.36, 1] } },
};

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
      <motion.div
        className="mx-auto flex max-w-4xl flex-col gap-5"
        variants={container}
        initial="hidden"
        animate="show"
      >
        {/* Header */}
        <motion.div
          className="rounded-2xl px-5 sm:px-6 py-6"
          style={{
            background: "var(--bg-secondary)",
            border: "1px solid var(--border)",
          }}
          variants={fadeUp}
        >
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <p className="text-[10px] font-semibold uppercase tracking-widest" style={{ color: "var(--text-muted)" }}>
                Administration
              </p>
              <h2 className="mt-2 text-xl font-semibold" style={{ color: "var(--text-primary)", letterSpacing: "-0.02em" }}>
                User Management
              </h2>
              <p className="mt-2 max-w-2xl text-sm" style={{ color: "var(--text-tertiary)" }}>
                View, activate, deactivate, and manage roles for all registered users.
              </p>
            </div>
            <motion.button
              type="button"
              onClick={() => void load()}
              className="inline-flex items-center gap-2 rounded-xl px-3 py-2 text-xs"
              style={{ border: "1px solid var(--border)", background: "var(--bg-surface)", color: "var(--text-secondary)" }}
              whileHover={{ borderColor: "var(--border-hover)" }}
              whileTap={{ scale: 0.95 }}
            >
              <RefreshCcw size={12} className={loading ? "animate-spin" : ""} />
              Refresh
            </motion.button>
          </div>
        </motion.div>

        {/* Stats row */}
        <motion.div className="grid grid-cols-1 sm:grid-cols-3 gap-3" variants={fadeUp}>
          <StatCard icon={<Users size={14} />} label="Total Users" value={users.length} />
          <StatCard icon={<UserCheck size={14} />} label="Active" value={activeCount} />
          <StatCard icon={<ShieldCheck size={14} />} label="Admins" value={adminCount} />
        </motion.div>

        {error ? (
          <div className="rounded-xl px-4 py-3 text-sm" style={{ background: "var(--error-soft)", color: "var(--error)" }}>
            {error}
          </div>
        ) : null}

        {/* User table */}
        <motion.div
          className="rounded-2xl overflow-hidden"
          style={{ background: "var(--bg-surface)", border: "1px solid var(--border)" }}
          variants={fadeUp}
        >
          {/* Table header */}
          <div
            className="hidden sm:grid grid-cols-[1fr_100px_100px_120px] gap-4 px-5 py-3 text-[10px] font-semibold uppercase tracking-widest"
            style={{ borderBottom: "1px solid var(--border)", color: "var(--text-muted)", background: "var(--bg-secondary)" }}
          >
            <span>Email</span>
            <span>Role</span>
            <span>Status</span>
            <span className="text-right">Actions</span>
          </div>

          {loading ? (
            <div className="flex items-center justify-center gap-2 py-12" style={{ color: "var(--text-muted)" }}>
              <Loader2 size={14} className="animate-spin" />
              <span className="text-xs">Loading users…</span>
            </div>
          ) : users.length === 0 ? (
            <div className="py-12 text-center text-sm" style={{ color: "var(--text-muted)" }}>
              No users found.
            </div>
          ) : (
            users.map((user, i) => (
              <motion.div
                key={user.id}
                className="flex flex-col sm:grid sm:grid-cols-[1fr_100px_100px_120px] gap-2 sm:gap-4 px-5 py-4 items-start sm:items-center"
                style={{ borderBottom: "1px solid var(--border)" }}
                initial={{ opacity: 0, x: -8 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: i * 0.03, duration: 0.25 }}
              >
                <div className="min-w-0">
                  <p className="text-sm font-medium truncate" style={{ color: "var(--text-primary)" }}>
                    {user.email}
                  </p>
                  <p className="text-[11px] mt-0.5 sm:hidden" style={{ color: "var(--text-muted)" }}>
                    {user.role} · {user.is_active ? "Active" : "Disabled"}
                  </p>
                </div>
                <div className="hidden sm:block">
                  <span
                    className="inline-flex items-center gap-1 text-[10px] px-2 py-1 rounded-full"
                    style={{
                      background: user.role === "admin" ? "rgba(99,102,241,0.08)" : "var(--accent-soft)",
                      color: user.role === "admin" ? "var(--accent-brand)" : "var(--text-secondary)",
                    }}
                  >
                    {user.role === "admin" ? <Shield size={9} /> : null}
                    {user.role}
                  </span>
                </div>
                <div className="hidden sm:block">
                  <span
                    className="inline-flex items-center gap-1 text-[10px] px-2 py-1 rounded-full"
                    style={{
                      background: user.is_active ? "var(--success-soft)" : "var(--error-soft)",
                      color: user.is_active ? "var(--success)" : "var(--error)",
                    }}
                  >
                    <span className="h-1.5 w-1.5 rounded-full" style={{ background: "currentColor" }} />
                    {user.is_active ? "Active" : "Disabled"}
                  </span>
                </div>
                <div className="flex items-center gap-1.5 sm:justify-end">
                  {isAdmin ? (
                    <>
                      <motion.button
                        type="button"
                        disabled={actionLoading === user.id}
                        onClick={() => void handleToggleActive(user)}
                        className="px-2.5 py-1.5 rounded-xl text-[11px] inline-flex items-center gap-1"
                        style={{
                          border: "1px solid var(--border)",
                          background: "var(--bg-secondary)",
                          color: user.is_active ? "var(--error)" : "var(--success)",
                        }}
                        title={user.is_active ? "Disable user" : "Enable user"}
                        whileTap={{ scale: 0.93 }}
                      >
                        {user.is_active ? <UserX size={10} /> : <UserCheck size={10} />}
                        {user.is_active ? "Disable" : "Enable"}
                      </motion.button>
                      <motion.button
                        type="button"
                        disabled={actionLoading === user.id}
                        onClick={() => void handleToggleRole(user)}
                        className="px-2.5 py-1.5 rounded-xl text-[11px] inline-flex items-center gap-1"
                        style={{
                          border: "1px solid var(--border)",
                          background: "var(--bg-secondary)",
                          color: "var(--text-secondary)",
                        }}
                        title={user.role === "admin" ? "Demote to user" : "Promote to admin"}
                        whileTap={{ scale: 0.93 }}
                      >
                        <Shield size={10} />
                        {user.role === "admin" ? "Demote" : "Promote"}
                      </motion.button>
                    </>
                  ) : (
                    <span className="text-[11px]" style={{ color: "var(--text-muted)" }}>—</span>
                  )}
                </div>
              </motion.div>
            ))
          )}
        </motion.div>

        {!isAdmin ? (
          <motion.div
            className="rounded-xl px-4 py-3 text-sm"
            style={{ background: "var(--warning-soft)", color: "var(--warning)" }}
            variants={fadeUp}
          >
            Admin privileges required to manage users.
          </motion.div>
        ) : null}
      </motion.div>
    </div>
  );
}

function StatCard({ icon, label, value }: { icon: React.ReactNode; label: string; value: number }) {
  return (
    <motion.div
      className="rounded-2xl px-4 py-4"
      style={{ background: "var(--bg-surface)", border: "1px solid var(--border)" }}
      whileHover={{ borderColor: "var(--border-hover)", y: -2 }}
      transition={{ duration: 0.2 }}
    >
      <div className="flex items-center justify-between">
        <span className="text-xs" style={{ color: "var(--text-tertiary)" }}>{label}</span>
        <span style={{ color: "var(--accent-brand)" }}>{icon}</span>
      </div>
      <motion.p
        className="mt-2.5 text-2xl font-semibold"
        style={{ color: "var(--text-primary)", letterSpacing: "-0.03em" }}
        initial={{ opacity: 0, scale: 0.8 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ delay: 0.2, duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
      >
        {value}
      </motion.p>
    </motion.div>
  );
}

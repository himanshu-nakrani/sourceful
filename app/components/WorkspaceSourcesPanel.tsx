"use client";

import React, { useCallback, useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  AlertTriangle,
  Check,
  FileText,
  Globe,
  Loader2,
  RefreshCw,
  X,
} from "lucide-react";
import {
  listWorkspaceSources,
  reprocessWorkspaceSource,
  type ClientAuthContext,
  type WorkspaceSource,
} from "../lib/api";
import { useWorkspaceRole } from "../lib/use-workspace-role";
import { EASE_OUT } from "../lib/motion";

interface WorkspaceSourcesPanelProps {
  open: boolean;
  onClose: () => void;
  workspaceId: string;
  workspaceName: string;
  auth: ClientAuthContext;
}

/**
 * Phase 1 + Phase 3: workspace sources list with type/status badges and a
 * Resync action that drives the durable refetch pipeline. The panel is the
 * only place where URL-source sync state surfaces today (the chat sidebar
 * still scopes by document, not by source).
 */
export default function WorkspaceSourcesPanel({
  open,
  onClose,
  workspaceId,
  workspaceName,
  auth,
}: WorkspaceSourcesPanelProps) {
  const [sources, setSources] = useState<WorkspaceSource[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const { canEdit } = useWorkspaceRole(auth, workspaceId);

  const refresh = useCallback(async () => {
    if (!open) return;
    setLoading(true);
    setError(null);
    try {
      const list = await listWorkspaceSources(auth, workspaceId);
      setSources(list);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load sources.");
    } finally {
      setLoading(false);
    }
  }, [auth, workspaceId, open]);

  useEffect(() => {
    if (open) void refresh();
  }, [open, refresh]);

  const handleResync = async (source: WorkspaceSource) => {
    setBusyId(source.id);
    setError(null);
    try {
      const refreshed = await reprocessWorkspaceSource(
        auth,
        workspaceId,
        source.id
      );
      setSources((prev) => prev.map((s) => (s.id === refreshed.id ? refreshed : s)));
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to resync source."
      );
    } finally {
      setBusyId(null);
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
            className="w-[min(820px,94vw)] h-[min(640px,86vh)] flex flex-col rounded-2xl overflow-hidden"
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
                <FileText size={14} style={{ color: "var(--accent-brand)" }} />
                <h2 className="text-sm font-semibold">Workspace sources</h2>
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
                aria-label="Close sources panel"
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

            <div className="flex-1 min-h-0 overflow-y-auto px-4 py-3">
              {loading && sources.length === 0 ? (
                <div
                  className="flex items-center gap-2 text-[11px]"
                  style={{ color: "var(--text-muted)" }}
                >
                  <Loader2 size={11} className="animate-spin" /> Loading sources…
                </div>
              ) : null}
              {!loading && sources.length === 0 ? (
                <div
                  className="text-[11px]"
                  style={{ color: "var(--text-muted)" }}
                >
                  No sources in this workspace yet. Upload a file or import a
                  URL to get started.
                </div>
              ) : null}
              <ul className="flex flex-col gap-1">
                {sources.map((source) => {
                  const isUrl = source.source_type === "url";
                  const Icon = isUrl ? Globe : FileText;
                  const statusColor =
                    source.status === "ready"
                      ? "var(--success, #10b981)"
                      : source.status === "error"
                        ? "var(--error)"
                        : "var(--warning, #f59e0b)";
                  return (
                    <li
                      key={source.id}
                      className="flex items-center gap-2 px-3 py-2 rounded-lg"
                      style={{
                        background: "var(--bg-surface)",
                        border: "1px solid var(--border)",
                      }}
                    >
                      <Icon
                        size={13}
                        style={{ color: "var(--text-muted)", flexShrink: 0 }}
                      />
                      <div className="flex-1 min-w-0">
                        <div className="text-xs font-medium truncate">
                          {source.source_title}
                        </div>
                        <div
                          className="text-[10px] truncate flex items-center gap-2"
                          style={{ color: "var(--text-muted)" }}
                        >
                          <span
                            className="uppercase tracking-widest"
                            style={{ color: statusColor }}
                          >
                            {source.status}
                          </span>
                          {isUrl && source.source_url ? (
                            <span className="truncate">{source.source_url}</span>
                          ) : null}
                          {isUrl && source.last_sync_status ? (
                            <span
                              className="inline-flex items-center gap-1 px-1 rounded"
                              style={{
                                background:
                                  source.last_sync_status === "running"
                                    ? "var(--warning-soft, rgba(245,158,11,0.12))"
                                    : source.last_sync_status === "error"
                                      ? "var(--error-soft)"
                                      : "var(--success-soft, rgba(16,185,129,0.12))",
                                color:
                                  source.last_sync_status === "running"
                                    ? "var(--warning, #d97706)"
                                    : source.last_sync_status === "error"
                                      ? "var(--error)"
                                      : "var(--success, #10b981)",
                              }}
                              title={source.last_sync_error ?? undefined}
                            >
                              {source.last_sync_status === "running" && (
                                <Loader2 size={9} className="animate-spin" />
                              )}
                              {source.last_sync_status === "error" && (
                                <AlertTriangle size={9} />
                              )}
                              {source.last_sync_status === "success" && (
                                <Check size={9} />
                              )}
                              {source.last_sync_status}
                            </span>
                          ) : null}
                          {source.last_fetched_at ? (
                            <span>
                              ·{" "}
                              {new Date(
                                source.last_fetched_at
                              ).toLocaleString()}
                            </span>
                          ) : null}
                        </div>
                      </div>
                      {isUrl && canEdit ? (
                        <button
                          type="button"
                          onClick={() => void handleResync(source)}
                          disabled={busyId === source.id}
                          className="text-[11px] px-2 py-1 rounded-md flex items-center gap-1"
                          style={{
                            color: "var(--text-secondary)",
                            background: "var(--bg-primary)",
                            border: "1px solid var(--border)",
                            opacity: busyId === source.id ? 0.6 : 1,
                          }}
                          title="Re-fetch the URL and re-index its content"
                        >
                          <RefreshCw
                            size={11}
                            className={busyId === source.id ? "animate-spin" : ""}
                          />
                          {busyId === source.id ? "Syncing…" : "Resync"}
                        </button>
                      ) : null}
                    </li>
                  );
                })}
              </ul>
            </div>
          </motion.div>
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}

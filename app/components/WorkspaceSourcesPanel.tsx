"use client";

import React, { useCallback, useEffect, useState, useMemo } from "react";
import { useOnChange } from "../lib/use-on-change";
import { FileText, Globe, Loader2, RefreshCw, X } from "lucide-react";
import {
  listWorkspaceSources,
  reprocessWorkspaceSource,
  type ClientAuthContext,
  type JobStatus,
  type WorkspaceSource,
} from "../lib/api";
import { useWorkspaceRole } from "../lib/use-workspace-role";
import { Button, EmptyState, ErrorBanner, Modal, StatusDot } from "./ui";
import type { StatusTone } from "./ui";

interface WorkspaceSourcesPanelProps {
  open: boolean;
  onClose: () => void;
  workspaceId: string;
  workspaceName: string;
  auth: ClientAuthContext;
}

/** Ingestion status -> semantic text color. */
const STATUS_COLOR: Record<JobStatus, string> = {
  ready: "var(--success)",
  processing: "var(--info)",
  queued: "var(--warning)",
  error: "var(--error)",
};

/** URL sync status -> StatusDot tone (running pulses while work is in flight). */
const SYNC_TONE: Record<NonNullable<WorkspaceSource["last_sync_status"]>, StatusTone> = {
  running: "processing",
  error: "error",
  success: "success",
};

const SYNC_COLOR: Record<NonNullable<WorkspaceSource["last_sync_status"]>, string> = {
  running: "var(--info)",
  error: "var(--error)",
  success: "var(--success)",
};

const SYNC_SOFT: Record<NonNullable<WorkspaceSource["last_sync_status"]>, string> = {
  running: "var(--info-soft)",
  error: "var(--error-soft)",
  success: "var(--success-soft)",
};

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

  // Bumped by refresh() (retry button) to force a reload with the same inputs.
  const [reloadToken, setReloadToken] = useState(0);
  const refresh = useCallback(() => setReloadToken((token) => token + 1), []);

  // One key per load request: set while the panel is open, and replaced when
  // its inputs change (same triggers as before). The spinner/error reset is
  // applied during render; the request runs in the effect and only sets state
  // after it resolves.
  const loadRequest = useMemo(
    () => (open ? { auth, workspaceId, reloadToken } : null),
    [open, auth, workspaceId, reloadToken],
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
        const list = await listWorkspaceSources(auth, workspaceId);
        setSources(list);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load sources.");
      } finally {
        setLoading(false);
      }
    };
    void run();
  }, [loadRequest]);

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
    <Modal
      open={open}
      onClose={onClose}
      busy={busyId !== null}
      title="Workspace sources"
      width={820}
      height="min(640px, 86vh)"
      align="top"
    >
      <div className="flex flex-col h-full min-h-0">
        <header
          className="flex items-center justify-between gap-3 px-5 py-3.5 flex-shrink-0"
          style={{ borderBottom: "1px solid var(--border)" }}
        >
          <div className="flex items-baseline gap-2.5 min-w-0">
            <h2 className="display text-[15px] font-semibold truncate">Workspace sources</h2>
            <span
              className="text-[10px] uppercase tracking-widest truncate"
              style={{ color: "var(--text-muted)" }}
            >
              {workspaceName}
            </span>
          </div>
          <Button variant="ghost" size="sm" onClick={onClose} aria-label="Close sources panel">
            <X size={14} />
          </Button>
        </header>

        {error ? (
          <div className="px-4 pt-3 flex-shrink-0">
            <ErrorBanner message={error} onRetry={() => void refresh()} />
          </div>
        ) : null}

        <div className="flex-1 min-h-0 overflow-y-auto px-4 py-4">
          {loading && sources.length === 0 ? (
            <div
              className="flex items-center gap-2 text-[11px] px-1"
              style={{ color: "var(--text-muted)" }}
            >
              <Loader2 size={11} className="animate-spin" /> Loading sources…
            </div>
          ) : null}
          {!loading && sources.length === 0 ? (
            <EmptyState
              icon={<Globe size={16} />}
              title="No sources yet"
              description="Upload a file or import a URL to get started."
            />
          ) : null}
          <ul className="flex flex-col gap-2">
            {sources.map((source) => {
              const isUrl = source.source_type === "url";
              const Icon = isUrl ? Globe : FileText;
              const statusColor = STATUS_COLOR[source.status] ?? "var(--warning)";
              const syncTone = source.last_sync_status
                ? SYNC_TONE[source.last_sync_status]
                : null;
              return (
                <li
                  key={source.id}
                  className="flex items-center gap-3 px-3.5 py-2.5 rounded-lg"
                  style={{
                    background: "var(--bg-surface)",
                    border: "1px solid var(--border)",
                  }}
                >
                  <Icon
                    size={14}
                    style={{ color: "var(--text-tertiary)", flexShrink: 0 }}
                  />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 min-w-0">
                      <span className="text-[13px] font-medium truncate">
                        {source.source_title}
                      </span>
                      <span
                        className="text-[10px] uppercase tracking-widest font-medium flex-shrink-0"
                        style={{ color: statusColor }}
                      >
                        {source.status}
                      </span>
                    </div>
                    <div className="flex items-center gap-2 mt-1 min-w-0">
                      {isUrl && source.source_url ? (
                        <span
                          className="text-[11px] truncate flex-1 min-w-0"
                          style={{ color: "var(--text-tertiary)" }}
                        >
                          {source.source_url}
                        </span>
                      ) : (
                        <span className="flex-1" />
                      )}
                      {isUrl && syncTone && source.last_sync_status ? (
                        <span
                          className="inline-flex items-center gap-1.5 px-1.5 py-0.5 rounded-sm flex-shrink-0"
                          style={{
                            background: SYNC_SOFT[source.last_sync_status],
                            border: "1px solid var(--border)",
                          }}
                          title={source.last_sync_error ?? undefined}
                        >
                          <StatusDot
                            tone={syncTone}
                            pulse={source.last_sync_status === "running"}
                          />
                          <span
                            className="text-[10px] font-medium"
                            style={{ color: SYNC_COLOR[source.last_sync_status] }}
                          >
                            {source.last_sync_status}
                          </span>
                        </span>
                      ) : null}
                      {source.last_fetched_at ? (
                        <span
                          className="data-num text-[10px] flex-shrink-0"
                          style={{ color: "var(--text-muted)" }}
                        >
                          {new Date(source.last_fetched_at).toLocaleString()}
                        </span>
                      ) : null}
                    </div>
                  </div>
                  {isUrl && canEdit ? (
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => void handleResync(source)}
                      disabled={busyId === source.id}
                      title="Re-fetch the URL and re-index its content"
                      className="flex-shrink-0"
                    >
                      <RefreshCw
                        size={11}
                        className={busyId === source.id ? "animate-spin" : ""}
                      />
                      {busyId === source.id ? "Syncing…" : "Resync"}
                    </Button>
                  ) : null}
                </li>
              );
            })}
          </ul>
        </div>
      </div>
    </Modal>
  );
}

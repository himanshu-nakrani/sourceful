"use client";

import React, { useCallback, useEffect, useState, useMemo } from "react";
import { useOnChange } from "../lib/use-on-change";
import {
  BarChart3,
  FileText,
  Globe,
  Loader2,
  MessageSquare,
  NotebookPen,
  StickyNote,
  X,
} from "lucide-react";
import {
  getWorkspaceAnalytics,
  getWorkspaceActivity,
  type ClientAuthContext,
  type WorkspaceActivityItem,
  type WorkspaceAnalytics,
} from "../lib/api";
import { Button, EmptyState, ErrorBanner, Modal } from "./ui";

interface WorkspaceAnalyticsPanelProps {
  open: boolean;
  onClose: () => void;
  workspaceId: string;
  workspaceName: string;
  auth: ClientAuthContext;
}

/**
 * Module-level metric cache: breakdown bars only need the max count per
 * breakdown, keyed weakly by the (stable between refreshes) items array so
 * re-renders never recompute it and stale arrays get collected.
 */
const breakdownMaxCache = new WeakMap<
  Array<{ type: string; count: number }>,
  number
>();

function breakdownMax(items: Array<{ type: string; count: number }>): number {
  const cached = breakdownMaxCache.get(items);
  if (cached !== undefined) return cached;
  const max = items.length ? Math.max(...items.map((i) => i.count)) : 0;
  breakdownMaxCache.set(items, max);
  return max;
}

/** Compact relative-time stamp for activity rows ("3m ago", "2h ago", …). */
function relativeTime(iso: string): string {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "";
  const seconds = Math.max(0, Math.floor((Date.now() - then) / 1000));
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}d ago`;
  const months = Math.floor(days / 30);
  if (months < 12) return `${months}mo ago`;
  return `${Math.floor(months / 12)}y ago`;
}

export default function WorkspaceAnalyticsPanel({
  open,
  onClose,
  workspaceId,
  workspaceName,
  auth,
}: WorkspaceAnalyticsPanelProps) {
  const [tab, setTab] = useState<"analytics" | "activity">("analytics");
  const [analytics, setAnalytics] = useState<WorkspaceAnalytics | null>(null);
  const [activity, setActivity] = useState<WorkspaceActivityItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
        const [aData, actData] = await Promise.all([
          getWorkspaceAnalytics(auth, workspaceId),
          getWorkspaceActivity(auth, workspaceId, 20),
        ]);
        setAnalytics(aData);
        setActivity(actData.activities);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load analytics.");
      } finally {
        setLoading(false);
      }
    };
    void run();
  }, [loadRequest]);

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Workspace analytics"
      width={720}
      height="min(640px, 86vh)"
      align="top"
    >
      <div className="flex flex-col h-full min-h-0">
        <header
          className="flex items-center justify-between gap-3 px-5 py-3.5 flex-shrink-0"
          style={{ borderBottom: "1px solid var(--border)" }}
        >
          <div className="flex items-baseline gap-2.5 min-w-0">
            <h2 className="display text-[15px] font-semibold truncate">Workspace analytics</h2>
            <span
              className="text-[10px] uppercase tracking-widest truncate"
              style={{ color: "var(--text-muted)" }}
            >
              {workspaceName}
            </span>
          </div>
          <Button variant="ghost" size="sm" onClick={onClose} aria-label="Close analytics panel">
            <X size={14} />
          </Button>
        </header>

        <div
          className="flex items-center gap-2 px-5 py-2.5 flex-shrink-0"
          style={{ borderBottom: "1px solid var(--border)" }}
        >
          <div
            role="tablist"
            aria-label="Analytics views"
            className="inline-flex gap-1 p-1 rounded-lg"
            style={{ background: "var(--bg-surface)", border: "1px solid var(--border)" }}
          >
            {(["analytics", "activity"] as const).map((key) => {
              const active = tab === key;
              return (
                <button
                  key={key}
                  type="button"
                  role="tab"
                  aria-selected={active}
                  onClick={() => setTab(key)}
                  className="px-3 py-1 rounded-sm text-[11px] font-medium capitalize transition-colors focus-ring"
                  style={{
                    background: active ? "var(--bg-elevated)" : "transparent",
                    color: active ? "var(--accent-primary)" : "var(--text-tertiary)",
                  }}
                >
                  {key}
                </button>
              );
            })}
          </div>
        </div>

        {error ? (
          <div className="px-4 pt-3 flex-shrink-0">
            <ErrorBanner message={error} onRetry={() => void refresh()} />
          </div>
        ) : null}

        <div className="flex-1 min-h-0 overflow-y-auto px-4 py-4">
          {loading && !analytics ? (
            <div
              className="flex items-center gap-2 text-[11px] px-1"
              style={{ color: "var(--text-muted)" }}
            >
              <Loader2 size={11} className="animate-spin" /> Loading…
            </div>
          ) : tab === "analytics" && analytics ? (
            <div className="flex flex-col gap-5">
              <div className="grid grid-cols-3 gap-2">
                <StatCard label="Sources" value={analytics.totals.sources} ready={analytics.totals.ready_sources} icon={<Globe size={12} />} />
                <StatCard label="Artifacts" value={analytics.totals.artifacts} icon={<NotebookPen size={12} />} />
                <StatCard label="Conversations" value={analytics.totals.conversations} icon={<MessageSquare size={12} />} />
                <StatCard label="Messages" value={analytics.totals.messages} icon={<StickyNote size={12} />} />
                <StatCard label="Messages (7d)" value={analytics.recent.messages_7d} icon={<MessageSquare size={12} />} />
                <StatCard label="Artifacts (7d)" value={analytics.recent.artifacts_7d} icon={<NotebookPen size={12} />} />
              </div>

              <BreakdownSection
                title="Sources by type"
                items={analytics.breakdown.sources_by_type}
                barColor="var(--accent-secondary)"
              />
              <BreakdownSection
                title="Artifacts by type"
                items={analytics.breakdown.artifacts_by_type}
                barColor="var(--accent-primary)"
              />
            </div>
          ) : tab === "activity" ? (
            activity.length === 0 && !loading ? (
              <EmptyState
                icon={<BarChart3 size={16} />}
                title="No recent activity"
                description="Workspace activity will appear here as sources, notes, and conversations change."
              />
            ) : (
              <ul
                className="flex flex-col rounded-lg overflow-hidden"
                style={{ border: "1px solid var(--border)" }}
              >
                {activity.map((item, index) => (
                  <li
                    key={`${item.type}-${item.id}`}
                    className="flex items-start gap-2.5 px-3 py-2.5"
                    style={{
                      background: "var(--bg-surface)",
                      borderBottom:
                        index === activity.length - 1
                          ? "none"
                          : "1px solid var(--border)",
                    }}
                  >
                    <span className="mt-0.5 flex-shrink-0">
                      <ActivityIcon type={item.type} />
                    </span>
                    <div className="flex-1 min-w-0">
                      <div className="text-xs font-medium truncate">
                        {item.type === "message"
                          ? `${item.role === "user" ? "Question" : "Answer"} in ${item.conversation_title || "Conversation"}`
                          : item.type === "artifact"
                            ? item.title
                            : item.source_title}
                      </div>
                      <div
                        className="text-[10px] truncate"
                        style={{ color: "var(--text-tertiary)" }}
                      >
                        {item.type === "message" && item.content_preview ? (
                          <span className="truncate">{item.content_preview}</span>
                        ) : item.type === "source_update" ? (
                          <span className="uppercase tracking-wider">{item.status}</span>
                        ) : item.type === "artifact" ? (
                          <span className="uppercase tracking-wider">{item.artifact_type}</span>
                        ) : null}
                      </div>
                    </div>
                    {item.created_at ? (
                      <span
                        className="data-num text-[10px] flex-shrink-0 mt-0.5"
                        style={{ color: "var(--text-tertiary)" }}
                        title={new Date(item.created_at).toLocaleString()}
                      >
                        {relativeTime(item.created_at)}
                      </span>
                    ) : null}
                  </li>
                ))}
              </ul>
            )
          ) : null}
        </div>
      </div>
    </Modal>
  );
}

function StatCard({
  label,
  value,
  ready,
  icon,
}: {
  label: string;
  value: number;
  ready?: number;
  icon: React.ReactNode;
}) {
  return (
    <div
      className="flex flex-col gap-1.5 px-3.5 py-3 rounded-lg"
      style={{ background: "var(--bg-surface)", border: "1px solid var(--border)" }}
    >
      <div
        className="flex items-center gap-1.5"
        style={{ color: "var(--text-muted)" }}
      >
        {icon}
        <span className="text-[10px] uppercase tracking-widest font-medium">{label}</span>
      </div>
      <div className="flex items-baseline gap-1.5 flex-wrap">
        <span
          className="data-num font-semibold leading-none"
          style={{ color: "var(--text-primary)", fontSize: "1.5rem" }}
        >
          {value}
        </span>
        {ready !== undefined ? (
          <span className="text-[10px] font-medium" style={{ color: "var(--success)" }}>
            {ready} ready
          </span>
        ) : null}
      </div>
    </div>
  );
}

function BreakdownSection({
  title,
  items,
  barColor,
}: {
  title: string;
  items: Array<{ type: string; count: number }>;
  barColor: string;
}) {
  if (!items.length) return null;
  const max = breakdownMax(items);
  return (
    <div className="flex flex-col gap-2">
      <h3
        className="text-[10px] font-medium uppercase tracking-widest"
        style={{ color: "var(--text-tertiary)" }}
      >
        {title}
      </h3>
      <div className="flex flex-col gap-1.5">
        {items.map((item) => (
          <div key={item.type} className="flex items-center gap-2">
            <span
              className="text-[10px] w-24 truncate capitalize"
              style={{ color: "var(--text-secondary)" }}
            >
              {item.type.replace(/_/g, " ")}
            </span>
            <div
              className="flex-1 h-1.5 rounded-full overflow-hidden"
              style={{ background: "var(--bg-highest)" }}
            >
              <div
                className="h-full rounded-full transition-[width]"
                style={{
                  width: `${max ? (item.count / max) * 100 : 0}%`,
                  background: barColor,
                }}
              />
            </div>
            <span
              className="data-num text-[10px] w-6 text-right"
              style={{ color: "var(--text-secondary)" }}
            >
              {item.count}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

function ActivityIcon({ type }: { type: WorkspaceActivityItem["type"] }) {
  const color = "var(--text-tertiary)";
  switch (type) {
    case "message":
      return <MessageSquare size={12} style={{ color }} />;
    case "artifact":
      return <NotebookPen size={12} style={{ color }} />;
    case "source_update":
      return <FileText size={12} style={{ color }} />;
    default:
      return <BarChart3 size={12} style={{ color }} />;
  }
}

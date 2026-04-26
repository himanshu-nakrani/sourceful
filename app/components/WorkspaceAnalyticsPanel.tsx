"use client";

import React, { useCallback, useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
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
import { EASE_OUT } from "../lib/motion";

interface WorkspaceAnalyticsPanelProps {
  open: boolean;
  onClose: () => void;
  workspaceId: string;
  workspaceName: string;
  auth: ClientAuthContext;
}

const TAB_CLASS =
  "text-[11px] font-medium px-3 py-1.5 rounded-md transition-colors";

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

  const refresh = useCallback(async () => {
    if (!open) return;
    setLoading(true);
    setError(null);
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
  }, [auth, workspaceId, open]);

  useEffect(() => {
    if (open) void refresh();
  }, [open, refresh]);

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
            className="w-[min(720px,94vw)] h-[min(640px,86vh)] flex flex-col rounded-2xl overflow-hidden"
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
                <BarChart3 size={14} style={{ color: "var(--accent-brand)" }} />
                <h2 className="text-sm font-semibold">Workspace overview</h2>
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
                aria-label="Close analytics panel"
              >
                <X size={14} />
              </button>
            </header>

            <div className="flex items-center gap-2 px-4 py-2 flex-shrink-0" style={{ borderBottom: "1px solid var(--border)" }}>
              <button
                type="button"
                onClick={() => setTab("analytics")}
                className={TAB_CLASS}
                style={{
                  background: tab === "analytics" ? "var(--accent-brand-soft)" : "transparent",
                  color: tab === "analytics" ? "var(--accent-brand)" : "var(--text-muted)",
                  border: "1px solid var(--border)",
                }}
              >
                Analytics
              </button>
              <button
                type="button"
                onClick={() => setTab("activity")}
                className={TAB_CLASS}
                style={{
                  background: tab === "activity" ? "var(--accent-brand-soft)" : "transparent",
                  color: tab === "activity" ? "var(--accent-brand)" : "var(--text-muted)",
                  border: "1px solid var(--border)",
                }}
              >
                Activity
              </button>
            </div>

            {error ? (
              <div
                className="px-4 py-2 text-[11px] flex-shrink-0"
                style={{ background: "var(--error-soft)", color: "var(--error)" }}
              >
                {error}
              </div>
            ) : null}

            <div className="flex-1 min-h-0 overflow-y-auto px-4 py-3">
              {loading && !analytics ? (
                <div className="flex items-center gap-2 text-[11px]" style={{ color: "var(--text-muted)" }}>
                  <Loader2 size={11} className="animate-spin" /> Loading…
                </div>
              ) : tab === "analytics" && analytics ? (
                <div className="flex flex-col gap-4">
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
                  />
                  <BreakdownSection
                    title="Artifacts by type"
                    items={analytics.breakdown.artifacts_by_type}
                  />
                </div>
              ) : tab === "activity" ? (
                <ul className="flex flex-col gap-2">
                  {activity.length === 0 && !loading ? (
                    <div className="text-[11px]" style={{ color: "var(--text-muted)" }}>
                      No recent activity.
                    </div>
                  ) : null}
                  {activity.map((item) => (
                    <li
                      key={`${item.type}-${item.id}`}
                      className="flex items-start gap-2 px-3 py-2 rounded-lg"
                      style={{
                        background: "var(--bg-surface)",
                        border: "1px solid var(--border)",
                      }}
                    >
                      <ActivityIcon type={item.type} />
                      <div className="flex-1 min-w-0">
                        <div className="text-[11px] font-medium truncate">
                          {item.type === "message"
                            ? `${item.role === "user" ? "Question" : "Answer"} in ${item.conversation_title || "Conversation"}`
                            : item.type === "artifact"
                              ? item.title
                              : item.source_title}
                        </div>
                        <div className="text-[10px] truncate" style={{ color: "var(--text-muted)" }}>
                          {item.type === "message" && item.content_preview ? (
                            <span className="truncate">{item.content_preview}</span>
                          ) : item.type === "source_update" ? (
                            <span className="uppercase tracking-wider">{item.status}</span>
                          ) : item.type === "artifact" ? (
                            <span className="uppercase tracking-wider">{item.artifact_type}</span>
                          ) : null}
                          {item.created_at ? (
                            <span> · {new Date(item.created_at).toLocaleString()}</span>
                          ) : null}
                        </div>
                      </div>
                    </li>
                  ))}
                </ul>
              ) : null}
            </div>
          </motion.div>
        </motion.div>
      ) : null}
    </AnimatePresence>
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
      className="flex flex-col gap-1 px-3 py-2 rounded-lg"
      style={{ background: "var(--bg-surface)", border: "1px solid var(--border)" }}
    >
      <div className="flex items-center gap-1" style={{ color: "var(--text-muted)" }}>
        {icon}
        <span className="text-[10px] uppercase tracking-widest">{label}</span>
      </div>
      <div className="text-lg font-semibold" style={{ color: "var(--text-primary)" }}>
        {value}
        {ready !== undefined ? (
          <span className="text-[10px] font-normal ml-1" style={{ color: "var(--success, #10b981)" }}>
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
}: {
  title: string;
  items: Array<{ type: string; count: number }>;
}) {
  if (!items.length) return null;
  const max = Math.max(...items.map((i) => i.count));
  return (
    <div className="flex flex-col gap-2">
      <h3 className="text-[11px] font-semibold uppercase tracking-widest" style={{ color: "var(--text-muted)" }}>
        {title}
      </h3>
      <div className="flex flex-col gap-1">
        {items.map((item) => (
          <div key={item.type} className="flex items-center gap-2">
            <span className="text-[10px] w-24 truncate capitalize">{item.type.replace(/_/g, " ")}</span>
            <div className="flex-1 h-1.5 rounded-full overflow-hidden" style={{ background: "var(--bg-surface)" }}>
              <div
                className="h-full rounded-full"
                style={{
                  width: `${max ? (item.count / max) * 100 : 0}%`,
                  background: "var(--accent-brand)",
                }}
              />
            </div>
            <span className="text-[10px] w-6 text-right">{item.count}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function ActivityIcon({ type }: { type: WorkspaceActivityItem["type"] }) {
  const color = "var(--text-muted)";
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

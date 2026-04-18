"use client";

import React from "react";
import { motion } from "framer-motion";
import { Activity, BarChart3, Database, MessagesSquare, RefreshCcw, Users } from "lucide-react";

import { getAnalyticsOverview, type AnalyticsOverview } from "../lib/api";

const container = {
  hidden: { opacity: 0 },
  show: { opacity: 1, transition: { staggerChildren: 0.06, delayChildren: 0.1 } },
};

const fadeUp = {
  hidden: { opacity: 0, y: 12 },
  show: { opacity: 1, y: 0, transition: { duration: 0.4, ease: [0.22, 1, 0.36, 1] } },
};

export default function InsightsDashboard() {
  const [data, setData] = React.useState<AnalyticsOverview | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);

  const load = React.useCallback(async () => {
    setLoading(true);
    try {
      const next = await getAnalyticsOverview();
      setData(next);
      setError(null);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Unable to load analytics.");
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    void load();
  }, [load]);

  const cards = data
    ? [
        { label: "Users", value: data.totals.users, note: `${data.totals.active_users_7d} active in 7d`, icon: <Users size={16} />, color: "#6366f1" },
        { label: "Documents", value: data.totals.documents, note: `${data.totals.ready_documents} ready`, icon: <Database size={16} />, color: "#22c55e" },
        { label: "Conversations", value: data.totals.conversations, note: `${data.totals.messages} messages`, icon: <MessagesSquare size={16} />, color: "#f59e0b" },
        { label: "Chunks", value: data.totals.chunks, note: `${data.recent.questions_24h} queries 24h`, icon: <BarChart3 size={16} />, color: "#ec4899" },
      ]
    : [];

  const recentActivity = [
    { label: "Signups (7d)", value: data?.recent.signups_7d ?? 0, color: "#6366f1" },
    { label: "Uploads (7d)", value: data?.recent.uploads_7d ?? 0, color: "#22c55e" },
    { label: "Questions (24h)", value: data?.recent.questions_24h ?? 0, color: "#a855f7" },
    { label: "Sessions (24h)", value: data?.recent.sessions_24h ?? 0, color: "#f59e0b" },
  ];

  const footprint = [
    { label: "Documents", value: data?.totals.documents ?? 0, color: "#0ea5e9" },
    { label: "Conversations", value: data?.totals.conversations ?? 0, color: "#22c55e" },
    { label: "Messages", value: data?.totals.messages ?? 0, color: "#a855f7" },
    { label: "Chunks", value: data?.totals.chunks ?? 0, color: "#f97316" },
  ];

  const providerTotal = (data?.provider_breakdown ?? []).reduce((sum, item) => sum + item.documents, 0);
  const readyDocuments = data?.totals.ready_documents ?? 0;
  const totalDocuments = data?.totals.documents ?? 0;
  const readyPercent = totalDocuments > 0 ? Math.round((readyDocuments / totalDocuments) * 100) : 0;

  return (
    <div className="flex-1 overflow-y-auto px-4 py-6" style={{ background: "var(--bg-primary)" }}>
      <motion.div
        className="mx-auto flex max-w-5xl flex-col gap-5"
        variants={container}
        initial="hidden"
        animate="show"
      >
        {/* Header */}
        <motion.div
          className="rounded-2xl px-6 py-6"
          style={{
            background: "var(--bg-secondary)",
            border: "1px solid var(--border)",
          }}
          variants={fadeUp}
        >
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <p className="text-[10px] font-semibold uppercase tracking-widest" style={{ color: "var(--text-muted)" }}>
                Shared Insights
              </p>
              <h2 className="mt-2 text-xl font-semibold" style={{ color: "var(--text-primary)", letterSpacing: "-0.02em" }}>
                Workspace analytics
              </h2>
              <p className="mt-2 max-w-2xl text-sm" style={{ color: "var(--text-tertiary)" }}>
                Product activity across users, documents, and chat usage.
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

        {error ? (
          <div className="rounded-xl px-4 py-3 text-sm" style={{ background: "var(--error-soft)", color: "var(--error)" }}>
            {error}
          </div>
        ) : null}

        {/* Metric cards */}
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
          {cards.map((card, i) => (
            <motion.div
              key={card.label}
              className="rounded-2xl px-4 py-4"
              style={{
                background: "var(--bg-surface)",
                border: "1px solid var(--border)",
              }}
              variants={fadeUp}
              whileHover={{ borderColor: "var(--border-hover)", y: -2 }}
              transition={{ duration: 0.2 }}
            >
              <div className="flex items-center justify-between">
                <span className="text-xs" style={{ color: "var(--text-tertiary)" }}>
                  {card.label}
                </span>
                <span style={{ color: card.color }}>{card.icon}</span>
              </div>
              <motion.p
                className="mt-3 text-3xl font-semibold"
                style={{ color: "var(--text-primary)", letterSpacing: "-0.03em" }}
                initial={{ opacity: 0, scale: 0.8 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={{ delay: 0.2 + i * 0.05, duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
              >
                {card.value}
              </motion.p>
              <p className="mt-1 text-[11px]" style={{ color: "var(--text-muted)" }}>
                {card.note}
              </p>
            </motion.div>
          ))}
        </div>

        <div className="grid grid-cols-1 gap-4 lg:grid-cols-[1.1fr_0.9fr]">
          {/* Recent activity */}
          <motion.div
            className="rounded-2xl px-5 py-5"
            style={{ background: "var(--bg-surface)", border: "1px solid var(--border)" }}
            variants={fadeUp}
          >
            <div className="flex items-center gap-2">
              <Activity size={14} style={{ color: "var(--accent-brand)" }} />
              <h3 className="text-sm font-semibold" style={{ color: "var(--text-primary)", letterSpacing: "-0.01em" }}>
                Recent activity
              </h3>
            </div>
            <div className="mt-4 grid grid-cols-2 gap-2">
              <MetricMini label="Signups (7d)" value={data?.recent.signups_7d ?? 0} />
              <MetricMini label="Uploads (7d)" value={data?.recent.uploads_7d ?? 0} />
              <MetricMini label="Questions (24h)" value={data?.recent.questions_24h ?? 0} />
              <MetricMini label="Sessions (24h)" value={data?.recent.sessions_24h ?? 0} />
            </div>
            <div className="mt-5">
              <MiniBarChart rows={recentActivity} />
            </div>
          </motion.div>

          {/* Document health */}
          <motion.div
            className="rounded-2xl px-5 py-5"
            style={{ background: "var(--bg-surface)", border: "1px solid var(--border)" }}
            variants={fadeUp}
          >
            <div className="flex items-center gap-2">
              <BarChart3 size={14} style={{ color: "var(--accent-brand)" }} />
              <h3 className="text-sm font-semibold" style={{ color: "var(--text-primary)", letterSpacing: "-0.01em" }}>
                Document health
              </h3>
            </div>
            <div
              className="mt-4 flex items-center gap-4 rounded-xl px-4 py-4"
              style={{ background: "var(--bg-secondary)", border: "1px solid var(--border)" }}
            >
              <ProgressDonut percent={readyPercent} />
              <div>
                <p className="text-sm font-medium" style={{ color: "var(--text-primary)" }}>
                  {readyDocuments}/{totalDocuments} ready
                </p>
                <p className="mt-1 text-[11px]" style={{ color: "var(--text-muted)" }}>
                  {totalDocuments - readyDocuments} processing or failed
                </p>
              </div>
            </div>
            <div className="mt-4 flex flex-col gap-3">
              {(data?.provider_breakdown ?? []).map((provider) => (
                <div key={provider.provider}>
                  <div className="mb-1 flex items-center justify-between text-xs">
                    <span style={{ color: "var(--text-primary)", textTransform: "capitalize" }}>
                      {provider.provider}
                    </span>
                    <span style={{ color: "var(--text-tertiary)" }}>
                      {provider.ready_documents}/{provider.documents}
                    </span>
                  </div>
                  <div className="h-1.5 rounded-full overflow-hidden" style={{ background: "var(--bg-tertiary)" }}>
                    <motion.div
                      className="h-full rounded-full"
                      style={{ background: "var(--accent-brand)" }}
                      initial={{ width: 0 }}
                      animate={{ width: `${provider.documents > 0 ? (provider.ready_documents / provider.documents) * 100 : 0}%` }}
                      transition={{ duration: 0.6, ease: "easeOut", delay: 0.3 }}
                    />
                  </div>
                  <p className="mt-1 text-[10px]" style={{ color: "var(--text-muted)" }}>
                    {providerTotal > 0 ? `${Math.round((provider.documents / providerTotal) * 100)}% of docs` : "No docs"}
                  </p>
                </div>
              ))}
              {!data?.provider_breakdown.length && !loading ? (
                <p className="text-xs" style={{ color: "var(--text-muted)" }}>
                  No provider activity yet.
                </p>
              ) : null}
            </div>
          </motion.div>
        </div>

        {/* Footprint */}
        <motion.div
          className="rounded-2xl px-5 py-5"
          style={{ background: "var(--bg-surface)", border: "1px solid var(--border)" }}
          variants={fadeUp}
        >
          <div className="flex items-center gap-2">
            <Database size={14} style={{ color: "var(--accent-brand)" }} />
            <h3 className="text-sm font-semibold" style={{ color: "var(--text-primary)", letterSpacing: "-0.01em" }}>
              Knowledge base footprint
            </h3>
          </div>
          <p className="mt-1 text-[11px]" style={{ color: "var(--text-muted)" }}>
            Relative size across indexed entities
          </p>
          <div className="mt-4">
            <MiniBarChart rows={footprint} animated />
          </div>
        </motion.div>
      </motion.div>
    </div>
  );
}

function MetricMini({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-xl px-3 py-3" style={{ background: "var(--bg-secondary)", border: "1px solid var(--border)" }}>
      <p className="text-[10px] uppercase tracking-widest" style={{ color: "var(--text-muted)" }}>
        {label}
      </p>
      <p className="mt-1.5 text-xl font-semibold" style={{ color: "var(--text-primary)", letterSpacing: "-0.02em" }}>
        {value}
      </p>
    </div>
  );
}

function MiniBarChart({
  rows,
  animated = false,
}: {
  rows: Array<{ label: string; value: number; color: string }>;
  animated?: boolean;
}) {
  const max = rows.reduce((peak, row) => Math.max(peak, row.value), 0);

  return (
    <div className="flex flex-col gap-3">
      {rows.map((row, i) => {
        const width = max > 0 ? (row.value / max) * 100 : 0;
        return (
          <div key={row.label}>
            <div className="mb-1 flex items-center justify-between text-xs">
              <span style={{ color: "var(--text-secondary)" }}>{row.label}</span>
              <span style={{ color: "var(--text-primary)" }}>{formatNumber(row.value)}</span>
            </div>
            <div className="h-1.5 rounded-full overflow-hidden" style={{ background: "var(--bg-tertiary)" }}>
              {animated ? (
                <motion.div
                  className="h-full rounded-full"
                  style={{ background: row.color }}
                  initial={{ width: 0 }}
                  animate={{ width: `${width}%` }}
                  transition={{ duration: 0.6, ease: "easeOut", delay: 0.1 + i * 0.05 }}
                />
              ) : (
                <div className="h-full rounded-full" style={{ width: `${width}%`, background: row.color }} />
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function ProgressDonut({ percent }: { percent: number }) {
  const normalized = Math.min(100, Math.max(0, percent));
  const circumference = 2 * Math.PI * 22;
  const offset = circumference - (normalized / 100) * circumference;

  return (
    <div className="relative h-14 w-14 flex-shrink-0">
      <svg width="56" height="56" viewBox="0 0 56 56" className="transform -rotate-90">
        <circle cx="28" cy="28" r="22" stroke="var(--bg-tertiary)" strokeWidth="4" fill="none" />
        <motion.circle
          cx="28" cy="28" r="22"
          stroke="var(--accent-brand)"
          strokeWidth="4"
          fill="none"
          strokeLinecap="round"
          strokeDasharray={circumference}
          initial={{ strokeDashoffset: circumference }}
          animate={{ strokeDashoffset: offset }}
          transition={{ duration: 0.8, ease: "easeOut", delay: 0.3 }}
        />
      </svg>
      <div className="absolute inset-0 flex items-center justify-center">
        <span className="text-[11px] font-semibold" style={{ color: "var(--text-primary)" }}>
          {normalized}%
        </span>
      </div>
    </div>
  );
}

function formatNumber(value: number): string {
  return Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 1 }).format(value);
}

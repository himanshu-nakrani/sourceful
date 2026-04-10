"use client";

import React from "react";
import { Activity, BarChart3, Database, MessagesSquare, RefreshCcw, Users } from "lucide-react";

import { getAnalyticsOverview, type AnalyticsOverview } from "../lib/api";

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
        { label: "Users", value: data.totals.users, note: `${data.totals.active_users_7d} active in 7d`, icon: <Users size={16} /> },
        { label: "Documents", value: data.totals.documents, note: `${data.totals.ready_documents} ready`, icon: <Database size={16} /> },
        { label: "Conversations", value: data.totals.conversations, note: `${data.totals.messages} total messages`, icon: <MessagesSquare size={16} /> },
        { label: "Chunks", value: data.totals.chunks, note: `${data.recent.questions_24h} questions in 24h`, icon: <BarChart3 size={16} /> },
      ]
    : [];

  const recentActivity = [
    { label: "Signups (7d)", value: data?.recent.signups_7d ?? 0, color: "#3b82f6" },
    { label: "Uploads (7d)", value: data?.recent.uploads_7d ?? 0, color: "#14b8a6" },
    { label: "Questions (24h)", value: data?.recent.questions_24h ?? 0, color: "#8b5cf6" },
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
      <div className="mx-auto flex max-w-5xl flex-col gap-6 animate-fade-in">
        <div
          className="rounded-[28px] border px-6 py-6"
          style={{
            borderColor: "var(--border)",
            background:
              "radial-gradient(circle at top left, rgba(59,130,246,0.18), transparent 32%), linear-gradient(180deg, var(--bg-secondary), var(--bg-primary))",
          }}
        >
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              {/* [typography] Standardized tracking to tracking-wider for consistency */}
              <p className="text-xs font-semibold uppercase tracking-wider" style={{ color: "var(--text-tertiary)" }}>
                Shared Insights
              </p>
              <h2 className="mt-2 text-2xl font-semibold" style={{ color: "var(--text-primary)" }}>
                Workspace analytics for every signed-in user
              </h2>
              <p className="mt-2 max-w-2xl text-sm" style={{ color: "var(--text-secondary)" }}>
                This view rolls up product activity across users, documents, and chat usage so the whole team can track adoption at a glance.
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

        {error ? (
          <div className="rounded-xl px-4 py-3 text-sm" style={{ background: "var(--error-soft)", color: "var(--error)" }}>
            {error}
          </div>
        ) : null}

        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
          {cards.map((card) => (
            <div
              key={card.label}
              className="rounded-2xl border px-4 py-4"
              style={{ borderColor: "var(--border)", background: "var(--bg-surface)" }}
            >
              <div className="flex items-center justify-between">
                <span className="text-sm" style={{ color: "var(--text-secondary)" }}>
                  {card.label}
                </span>
                <span style={{ color: "var(--accent-brand)" }}>{card.icon}</span>
              </div>
              <p className="mt-3 text-3xl font-semibold" style={{ color: "var(--text-primary)" }}>
                {card.value}
              </p>
              <p className="mt-1 text-xs" style={{ color: "var(--text-tertiary)" }}>
                {card.note}
              </p>
            </div>
          ))}
        </div>

        <div className="grid grid-cols-1 gap-4 lg:grid-cols-[1.1fr_0.9fr]">
          <div
            className="rounded-2xl border px-5 py-5"
            style={{ borderColor: "var(--border)", background: "var(--bg-surface)" }}
          >
            <div className="flex items-center gap-2">
              <Activity size={16} style={{ color: "var(--accent-brand)" }} />
              <h3 className="text-sm font-semibold" style={{ color: "var(--text-primary)" }}>
                Recent activity
              </h3>
            </div>
            <div className="mt-4 grid grid-cols-2 gap-3">
              <MetricMini label="New signups (7d)" value={data?.recent.signups_7d ?? 0} />
              <MetricMini label="Uploads (7d)" value={data?.recent.uploads_7d ?? 0} />
              <MetricMini label="Questions (24h)" value={data?.recent.questions_24h ?? 0} />
              <MetricMini label="Sessions (24h)" value={data?.recent.sessions_24h ?? 0} />
            </div>
            <div className="mt-5">
              <MiniBarChart rows={recentActivity} />
            </div>
          </div>

          <div
            className="rounded-2xl border px-5 py-5"
            style={{ borderColor: "var(--border)", background: "var(--bg-surface)" }}
          >
            <div className="flex items-center gap-2">
              <BarChart3 size={16} style={{ color: "var(--accent-brand)" }} />
              <h3 className="text-sm font-semibold" style={{ color: "var(--text-primary)" }}>
                Document health
              </h3>
            </div>
            <div
              className="mt-4 flex items-center gap-4 rounded-xl border px-4 py-4"
              style={{ borderColor: "var(--border)", background: "var(--bg-secondary)" }}
            >
              <ProgressDonut percent={readyPercent} />
              <div>
                <p className="text-sm font-medium" style={{ color: "var(--text-primary)" }}>
                  {readyDocuments}/{totalDocuments} ready
                </p>
                <p className="mt-1 text-xs" style={{ color: "var(--text-tertiary)" }}>
                  {totalDocuments - readyDocuments} still processing or failed
                </p>
              </div>
            </div>
            <div className="mt-4 flex flex-col gap-3">
              {(data?.provider_breakdown ?? []).map((provider) => (
                <div key={provider.provider}>
                  <div className="mb-1 flex items-center justify-between text-sm">
                    <span style={{ color: "var(--text-primary)", textTransform: "capitalize" }}>
                      {provider.provider}
                    </span>
                    <span style={{ color: "var(--text-secondary)" }}>
                      {provider.ready_documents}/{provider.documents} ready
                    </span>
                  </div>
                  <div className="h-2 rounded-full" style={{ background: "var(--bg-tertiary)" }}>
                    <div
                      className="h-2 rounded-full"
                      style={{
                        width: `${provider.documents > 0 ? (provider.ready_documents / provider.documents) * 100 : 0}%`,
                        background: "linear-gradient(90deg, #3b82f6, #60a5fa)",
                      }}
                    />
                  </div>
                  <p className="mt-1 text-xs" style={{ color: "var(--text-tertiary)" }}>
                    {providerTotal > 0 ? `${Math.round((provider.documents / providerTotal) * 100)}% of docs` : "No docs"}
                  </p>
                </div>
              ))}
              {!data?.provider_breakdown.length && !loading ? (
                <p className="text-sm" style={{ color: "var(--text-tertiary)" }}>
                  No provider activity yet.
                </p>
              ) : null}
            </div>
          </div>
        </div>

        <div
          className="rounded-2xl border px-5 py-5"
          style={{ borderColor: "var(--border)", background: "var(--bg-surface)" }}
        >
          <div className="flex items-center gap-2">
            <Database size={16} style={{ color: "var(--accent-brand)" }} />
            <h3 className="text-sm font-semibold" style={{ color: "var(--text-primary)" }}>
              Knowledge base footprint
            </h3>
          </div>
          <p className="mt-1 text-xs" style={{ color: "var(--text-tertiary)" }}>
            Relative size across indexed entities
          </p>
          <div className="mt-4">
            <MiniBarChart rows={footprint} />
          </div>
        </div>
      </div>
    </div>
  );
}

function MetricMini({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-xl px-4 py-3" style={{ background: "var(--bg-secondary)", border: "1px solid var(--border)" }}>
      {/* [typography] Changed text-[11px] to text-xs for minimum readable size */}
      <p className="text-xs uppercase tracking-wider" style={{ color: "var(--text-tertiary)" }}>
        {label}
      </p>
      <p className="mt-2 text-2xl font-semibold" style={{ color: "var(--text-primary)" }}>
        {value}
      </p>
    </div>
  );
}

function MiniBarChart({
  rows,
}: {
  rows: Array<{ label: string; value: number; color: string }>;
}) {
  const max = rows.reduce((peak, row) => Math.max(peak, row.value), 0);

  return (
    <div className="flex flex-col gap-3">
      {rows.map((row) => {
        const width = max > 0 ? (row.value / max) * 100 : 0;
        return (
          <div key={row.label}>
            <div className="mb-1 flex items-center justify-between text-xs">
              <span style={{ color: "var(--text-secondary)" }}>{row.label}</span>
              <span style={{ color: "var(--text-primary)" }}>{formatNumber(row.value)}</span>
            </div>
            <div className="h-2 rounded-full" style={{ background: "var(--bg-tertiary)" }}>
              <div className="h-2 rounded-full" style={{ width: `${width}%`, background: row.color }} />
            </div>
          </div>
        );
      })}
    </div>
  );
}

function ProgressDonut({ percent }: { percent: number }) {
  const normalized = Math.min(100, Math.max(0, percent));
  return (
    <div
      className="grid h-16 w-16 place-items-center rounded-full"
      style={{
        background: `conic-gradient(#3b82f6 0% ${normalized}%, var(--bg-tertiary) ${normalized}% 100%)`,
      }}
    >
      <div className="grid h-12 w-12 place-items-center rounded-full" style={{ background: "var(--bg-surface)" }}>
        <span className="text-xs font-semibold" style={{ color: "var(--text-primary)" }}>
          {normalized}%
        </span>
      </div>
    </div>
  );
}

function formatNumber(value: number): string {
  return Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 1 }).format(value);
}

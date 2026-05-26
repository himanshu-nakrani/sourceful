"use client";

import React, { useMemo } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { BarChart3, CheckCircle2, AlertCircle, X, Clock } from "lucide-react";
import { EASE_OUT } from "../lib/motion";
import type { Citation, Message } from "../lib/api";

interface TrustAnalyticsPanelProps {
  open: boolean;
  onClose: () => void;
  messages: Message[];
  latencyMs?: number | null;
}

interface TrustMetrics {
  totalResponses: number;
  avgScore: number;
  highConfidence: number;
  lowConfidence: number;
  citationDensity: number;
  avgLatencyMs: number | null;
  sourceDepth: number;
}

// ⚡ BOLT OPTIMIZATION:
// Cached computationally expensive regex matching and string splitting for
// TrustAnalyticsPanel messages. Messages maintain referential equality across
// renders during SSE streaming, allowing O(1) retrieval instead of O(N) recalculation.
const _messageMetricsCache = new WeakMap<Message, { wordCount: number; citations: number }>();

function computeMetrics(messages: Message[], latencyMs?: number | null): TrustMetrics {
  const assistantMsgs = messages.filter((m) => m.role === "assistant");
  const totalResponses = assistantMsgs.length;

  const allSources: Citation[] = [];
  let totalWords = 0;
  let totalCitations = 0;

  for (const msg of assistantMsgs) {
    if (msg.sources) allSources.push(...msg.sources);

    let cached = _messageMetricsCache.get(msg);
    if (!cached) {
      cached = {
        wordCount: msg.content.split(/\s+/).filter(Boolean).length,
        citations: msg.content.match(/\[\d+\]/g)?.length ?? 0
      };
      _messageMetricsCache.set(msg, cached);
    }

    totalWords += cached.wordCount;
    totalCitations += cached.citations;
  }

  const avgScore =
    allSources.length > 0
      ? allSources.reduce((s, c) => s + c.score, 0) / allSources.length
      : 0;

  const highConfidence = allSources.filter((s) => s.score >= 0.75).length;
  const lowConfidence = allSources.filter((s) => s.score < 0.45).length;
  const citationDensity = totalWords > 0 ? (totalCitations / totalWords) * 100 : 0;
  const sourceDepth = totalResponses > 0 ? allSources.length / totalResponses : 0;

  return {
    totalResponses,
    avgScore,
    highConfidence,
    lowConfidence,
    citationDensity,
    avgLatencyMs: latencyMs ?? null,
    sourceDepth,
  };
}

function MiniBar({ value, max, color }: { value: number; max: number; color: string }) {
  const pct = max > 0 ? Math.min(100, (value / max) * 100) : 0;
  return (
    <div className="h-1 rounded-full overflow-hidden" style={{ background: "var(--bg-elevated)" }}>
      <motion.div
        className="h-full rounded-full"
        style={{ background: color }}
        initial={{ width: 0 }}
        animate={{ width: `${pct}%` }}
        transition={{ duration: 0.6, ease: EASE_OUT }}
      />
    </div>
  );
}

export default function TrustAnalyticsPanel({ open, onClose, messages, latencyMs }: TrustAnalyticsPanelProps) {
  // ⚡ BOLT OPTIMIZATION:
  // Short-circuit expensive metrics computation when the panel is logically closed.
  // Because older messages maintain referential equality across state updates, we can avoid
  // recalculating the entire array by returning a placeholder when `!open`.
  // This reduces CPU overhead during SSE streaming, ensuring high-frequency re-renders
  // are buttery smooth for hidden elements without breaking the AnimatePresence exit animations.
  const metrics = useMemo(() => {
    if (!open) {
      return {
        totalResponses: 0,
        avgScore: 0,
        highConfidence: 0,
        lowConfidence: 0,
        citationDensity: 0,
        avgLatencyMs: null,
        sourceDepth: 0,
      };
    }
    return computeMetrics(messages, latencyMs);
  }, [messages, latencyMs, open]);

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className="absolute right-4 top-14 z-40 rounded-2xl overflow-hidden shadow-xl"
          style={{
            width: 280,
            background: "var(--bg-secondary)",
            border: "1px solid var(--border-hover)",
            boxShadow: "var(--shadow-lg)",
          }}
          initial={{ opacity: 0, y: -8, scale: 0.97 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: -8, scale: 0.97 }}
          transition={{ duration: 0.2, ease: EASE_OUT }}
        >
          {/* Header */}
          <div
            className="flex items-center justify-between px-4 py-3"
            style={{ borderBottom: "1px solid var(--border)" }}
          >
            <div className="flex items-center gap-2">
              <BarChart3 size={13} style={{ color: "var(--accent-brand)" }} />
              <span className="text-xs font-semibold" style={{ color: "var(--text-primary)" }}>
                Trust Analytics
              </span>
            </div>
            <button
              type="button"
              onClick={onClose}
              style={{ color: "var(--text-muted)" }}
              aria-label="Close trust analytics"
            >
              <X size={13} />
            </button>
          </div>

          {/* Metrics */}
          <div className="px-4 py-3 flex flex-col gap-3">
            {metrics.totalResponses === 0 ? (
              <p className="text-xs text-center py-4" style={{ color: "var(--text-muted)" }}>
                Send a few messages to see analytics.
              </p>
            ) : (
              <>
                {/* Avg retrieval score */}
                <div
                  className="flex flex-col gap-1"
                  title="Average similarity score of all retrieved chunks across this session. Higher = better grounding."
                >
                  <div className="flex items-center justify-between">
                    <span className="text-[11px]" style={{ color: "var(--text-secondary)" }}>Avg. Retrieval Score</span>
                    <span
                      className="text-[11px] font-semibold"
                      style={{
                        color:
                          metrics.avgScore >= 0.75
                            ? "var(--confidence-high)"
                            : metrics.avgScore >= 0.45
                            ? "var(--confidence-med)"
                            : "var(--confidence-low)",
                      }}
                    >
                      {(metrics.avgScore * 100).toFixed(0)}%
                    </span>
                  </div>
                  <MiniBar
                    value={metrics.avgScore}
                    max={1}
                    color={
                      metrics.avgScore >= 0.75
                        ? "var(--confidence-high)"
                        : metrics.avgScore >= 0.45
                        ? "var(--confidence-med)"
                        : "var(--confidence-low)"
                    }
                  />
                </div>

                {/* Source depth */}
                <div
                  className="flex flex-col gap-1"
                  title="Average number of retrieved sources per assistant response. Higher suggests more thorough grounding."
                >
                  <div className="flex items-center justify-between">
                    <span className="text-[11px]" style={{ color: "var(--text-secondary)" }}>Sources / Response</span>
                    <span className="text-[11px] font-semibold" style={{ color: "var(--text-primary)" }}>
                      {metrics.sourceDepth.toFixed(1)}
                    </span>
                  </div>
                  <MiniBar value={metrics.sourceDepth} max={10} color="var(--accent-brand)" />
                </div>

                {/* Citation density */}
                <div
                  className="flex flex-col gap-1"
                  title="Percentage of words in assistant responses that carry inline [n] citations. Higher = more verifiable claims."
                >
                  <div className="flex items-center justify-between">
                    <span className="text-[11px]" style={{ color: "var(--text-secondary)" }}>Citation Density</span>
                    <span className="text-[11px] font-semibold" style={{ color: "var(--text-primary)" }}>
                      {metrics.citationDensity.toFixed(1)}%
                    </span>
                  </div>
                  <MiniBar value={metrics.citationDensity} max={10} color="var(--accent-brand)" />
                </div>

                {/* Confidence breakdown */}
                <div
                  className="grid grid-cols-2 gap-2 rounded-xl p-3"
                  style={{ background: "var(--bg-tertiary)" }}
                >
                  <div className="flex items-center gap-1.5">
                    <CheckCircle2 size={11} style={{ color: "var(--confidence-high)" }} />
                    <div>
                      <div className="text-[10px]" style={{ color: "var(--text-muted)" }}>Strong</div>
                      <div className="text-xs font-semibold" style={{ color: "var(--confidence-high)" }}>
                        {metrics.highConfidence}
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <AlertCircle size={11} style={{ color: "var(--confidence-low)" }} />
                    <div>
                      <div className="text-[10px]" style={{ color: "var(--text-muted)" }}>Weak</div>
                      <div className="text-xs font-semibold" style={{ color: "var(--confidence-low)" }}>
                        {metrics.lowConfidence}
                      </div>
                    </div>
                  </div>
                </div>

                {/* Latency */}
                {metrics.avgLatencyMs != null && (
                  <div className="flex items-center gap-2">
                    <Clock size={11} style={{ color: "var(--text-muted)" }} />
                    <span className="text-[11px]" style={{ color: "var(--text-secondary)" }}>Last latency</span>
                    <span className="text-[11px] font-semibold ml-auto" style={{ color: "var(--text-primary)" }}>
                      {metrics.avgLatencyMs < 1000
                        ? `${metrics.avgLatencyMs}ms`
                        : `${(metrics.avgLatencyMs / 1000).toFixed(1)}s`}
                    </span>
                  </div>
                )}

                {/* Responses count */}
                <div className="pt-1" style={{ borderTop: "1px solid var(--border)" }}>
                  <span className="text-[10px] uppercase tracking-widest" style={{ color: "var(--text-muted)" }}>
                    {metrics.totalResponses} response{metrics.totalResponses !== 1 ? "s" : ""} analyzed
                  </span>
                </div>
              </>
            )}
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

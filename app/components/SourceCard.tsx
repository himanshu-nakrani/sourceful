"use client";

import React, { useMemo, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { BookOpen, ChevronDown, FileText } from "lucide-react";
import type { Citation } from "../lib/api";
import { EASE_OUT } from "../lib/motion";
import { useServerState } from "../lib/server-state";
import { Meter } from "./ui";

interface SourceCardProps {
  sources: Citation[];
}

interface SourceGroup {
  documentId: string;
  title: string;
  citations: Array<{ citation: Citation; globalIndex: number }>;
}

type ScoreTier = { label: string; textColor: string; rail: string };

function getScoreTier(score: number): ScoreTier {
  if (score >= 0.75) {
    return {
      label: "Strong match",
      textColor: "var(--confidence-high)",
      rail: "var(--confidence-high)",
    };
  }
  if (score >= 0.45) {
    return {
      label: "Good match",
      textColor: "var(--confidence-med)",
      rail: "var(--confidence-med)",
    };
  }
  return {
    label: "Weak match",
    textColor: "var(--confidence-low)",
    rail: "var(--confidence-low)",
  };
}

const SourceCard = React.memo(function SourceCard({ sources }: SourceCardProps) {
  const [expanded, setExpanded] = useState(false);
  const { documents } = useServerState();

  const groups: SourceGroup[] = useMemo(() => {
    const map = new Map<string, SourceGroup>();
    sources.forEach((citation, index) => {
      const key = citation.document_id || "__unknown__";
      const doc = documents.find((d) => d.id === citation.document_id);
      const title = doc?.filename || (citation.document_id ? "Untitled document" : "Unknown source");
      const existing = map.get(key);
      const entry = { citation, globalIndex: index + 1 };
      if (existing) {
        existing.citations.push(entry);
      } else {
        map.set(key, { documentId: key, title, citations: [entry] });
      }
    });
    return Array.from(map.values());
  }, [sources, documents]);

  const scoreStats = useMemo(() => {
    const scores = sources.map((source) => source.score).filter((score) => Number.isFinite(score));
    if (!scores.length) return null;
    return {
      average: scores.reduce((sum, score) => sum + score, 0) / scores.length,
      minimum: Math.min(...scores),
      maximum: Math.max(...scores),
    };
  }, [sources]);

  if (!sources.length) return null;

  return (
    <motion.div
      className="overflow-hidden rounded-xl"
      style={{
        background: "var(--bg-surface)",
        border: "1px solid var(--border)",
      }}
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25, ease: EASE_OUT }}
    >
      <button
        type="button"
        onClick={() => setExpanded((current) => !current)}
        aria-expanded={expanded}
        aria-label={`${expanded ? "Hide" : "Show"} ${sources.length} source ${sources.length === 1 ? "passage" : "passages"}`}
        className="w-full flex items-center gap-3 px-4 py-3 text-left transition-colors hover:bg-[var(--bg-surface-hover)] focus-ring"
        style={{ background: "transparent" }}
      >
        <BookOpen size={16} style={{ color: "var(--accent-primary)", flexShrink: 0 }} aria-hidden="true" />
        <span className="text-sm font-medium" style={{ color: "var(--text-primary)" }}>
          Sources
        </span>
        <span className="text-xs" style={{ color: "var(--text-secondary)" }}>
          {sources.length} {sources.length === 1 ? "passage" : "passages"}
          {" · "}
          {groups.length} {groups.length === 1 ? "document" : "documents"}
        </span>
        <span className="flex-1" />
        <span className="flex items-center justify-center p-1" style={{ color: "var(--text-muted)" }} aria-hidden="true">
          <motion.div animate={{ rotate: expanded ? 180 : 0 }} transition={{ duration: 0.15 }}>
            <ChevronDown size={15} />
          </motion.div>
        </span>
      </button>

      <AnimatePresence>
        {expanded ? (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.25, ease: EASE_OUT }}
            className="overflow-hidden"
          >
            <div className="px-4 py-4 flex flex-col gap-4" style={{ borderTop: "1px solid var(--border)" }}>
              {groups.map((group) => (
                <section key={group.documentId} className="flex flex-col gap-1" aria-label={`Sources from ${group.title}`}>
                  <div className="flex items-center gap-2 min-w-0 pb-1">
                    <FileText size={14} style={{ color: "var(--accent-primary)", flexShrink: 0 }} aria-hidden="true" />
                    <h3 className="text-sm font-medium truncate" style={{ color: "var(--text-primary)" }} title={group.title}>
                      {group.title}
                    </h3>
                    <span className="text-xs flex-shrink-0" style={{ color: "var(--text-tertiary)" }}>
                      {group.citations.length} {group.citations.length === 1 ? "passage" : "passages"}
                    </span>
                  </div>
                  <div className="flex flex-col">
                    {group.citations.map(({ citation, globalIndex }, index) => {
                      const tier = getScoreTier(citation.score);
                      return (
                        <motion.article
                          key={`${group.documentId}-${globalIndex}`}
                          className="relative py-3 pl-4 first:pt-1 last:pb-1"
                          style={{ borderBottom: index < group.citations.length - 1 ? "1px solid var(--border)" : undefined }}
                          initial={{ opacity: 0, x: -6 }}
                          animate={{ opacity: 1, x: 0 }}
                          transition={{ delay: index * 0.04, duration: 0.25, ease: EASE_OUT }}
                          aria-label={`Source ${globalIndex} excerpt`}
                        >
                          <div
                            className="absolute left-0 top-0 bottom-0 w-[2px]"
                            style={{ background: tier.rail, opacity: 0.85 }}
                            aria-hidden="true"
                          />
                          <div className="flex flex-wrap items-center gap-x-2 gap-y-1 mb-2">
                            <span className="data-num text-xs font-medium" style={{ color: "var(--accent-primary)" }}>
                              [{globalIndex}]
                            </span>
                            {citation.page_number ? (
                              <span className="text-xs" style={{ color: "var(--text-tertiary)" }}>
                                Page {citation.page_number}
                              </span>
                            ) : null}
                            <span className="text-xs font-medium" style={{ color: tier.textColor }}>
                              {tier.label}
                            </span>
                          </div>
                          <p className="text-sm leading-relaxed whitespace-pre-wrap break-words" style={{ color: "var(--text-secondary)" }}>
                            {citation.excerpt}
                          </p>
                        </motion.article>
                      );
                    })}
                  </div>
                </section>
              ))}

              {scoreStats ? (
                <details className="pt-3" style={{ borderTop: "1px solid var(--border)" }}>
                  <summary className="cursor-pointer rounded-sm text-sm font-medium focus-ring" style={{ color: "var(--text-secondary)" }}>
                    Retrieval details
                  </summary>
                  <div className="pt-3 flex flex-col gap-4">
                    <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
                      <Meter value={scoreStats.average} label="Average relevance" compact showValue />
                      <span className="text-xs" style={{ color: "var(--text-tertiary)" }}>
                        Score range{" "}
                        <span className="data-num" style={{ color: "var(--text-secondary)" }}>
                          {scoreStats.minimum.toFixed(2)}–{scoreStats.maximum.toFixed(2)}
                        </span>
                      </span>
                    </div>
                    {groups.map((group) => {
                      const groupScores = group.citations
                        .map(({ citation }) => citation.score)
                        .filter((score) => Number.isFinite(score));
                      const groupAverage = groupScores.length
                        ? groupScores.reduce((sum, score) => sum + score, 0) / groupScores.length
                        : null;
                      return (
                        <section key={`details-${group.documentId}`} className="flex flex-col gap-2">
                          <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1 text-xs">
                            <span className="font-medium" style={{ color: "var(--text-secondary)" }}>
                              {group.title}
                            </span>
                            {groupAverage !== null ? (
                              <span style={{ color: "var(--text-tertiary)" }}>
                                {group.citations.length} {group.citations.length === 1 ? "passage" : "passages"} · average score{" "}
                                <span className="data-num" style={{ color: "var(--text-secondary)" }}>
                                  {groupAverage.toFixed(2)}
                                </span>
                              </span>
                            ) : null}
                          </div>
                          <div className="flex flex-col">
                            {group.citations.map(({ citation, globalIndex }, index) => (
                              <div
                                key={`metadata-${group.documentId}-${globalIndex}`}
                                className="py-2"
                                style={{ borderTop: index > 0 ? "1px solid var(--border)" : undefined }}
                              >
                                <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 text-xs">
                                  <span className="font-medium" style={{ color: "var(--text-secondary)" }}>
                                    Passage [{globalIndex}]
                                  </span>
                                  <span style={{ color: "var(--text-tertiary)" }}>
                                    Score{" "}
                                    <span className="data-num" style={{ color: "var(--text-secondary)" }}>
                                      {citation.score.toFixed(2)}
                                    </span>
                                  </span>
                                </div>
                                <div className="mt-1 grid min-w-0 gap-x-4 gap-y-1 text-xs sm:grid-cols-2">
                                  <p className="min-w-0 break-all" style={{ color: "var(--text-tertiary)" }}>
                                    Document ID{" "}
                                    <span className="data-num" style={{ color: "var(--text-secondary)" }}>
                                      {citation.document_id || "Unknown"}
                                    </span>
                                  </p>
                                  <p className="min-w-0 break-all" style={{ color: "var(--text-tertiary)" }}>
                                    Chunk ID{" "}
                                    <span className="data-num" style={{ color: "var(--text-secondary)" }}>
                                      {citation.chunk_id}
                                    </span>
                                  </p>
                                </div>
                              </div>
                            ))}
                          </div>
                        </section>
                      );
                    })}
                  </div>
                </details>
              ) : null}
            </div>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </motion.div>
  );
});

export default SourceCard;

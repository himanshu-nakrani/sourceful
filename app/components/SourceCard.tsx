"use client";

import React, { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { BookOpen, ChevronDown, CheckCircle2, AlertCircle, MinusCircle } from "lucide-react";
import type { Citation } from "../lib/api";
import { EASE_OUT } from "../lib/motion";

interface SourceCardProps {
  sources: Citation[];
}

// ⚡ BOLT OPTIMIZATION:
// Wrapped SourceCard in React.memo to prevent unnecessary re-renders of source
// citations for older messages during rapid state updates from token streaming.
const SourceCard = React.memo(function SourceCard({ sources }: SourceCardProps) {
  const [expanded, setExpanded] = useState(false);

  if (!sources.length) return null;

  return (
    <motion.div
      className="rounded-2xl overflow-hidden"
      style={{
        background: "var(--bg-surface)",
        border: "1px solid var(--border)",
      }}
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: EASE_OUT }}
    >
      {/* [a11y] Added aria-expanded to communicate toggle state to assistive technology */}
      <button
        type="button"
        onClick={() => setExpanded((current) => !current)}
        aria-expanded={expanded}
        className="w-full flex items-center gap-2 px-4 py-2.5 transition-colors"
        style={{ background: expanded ? "var(--bg-tertiary)" : "transparent" }}
      >
        <BookOpen size={13} style={{ color: "var(--accent-brand)", flexShrink: 0 }} />
        <span className="text-xs font-medium" style={{ color: "var(--text-secondary)" }}>
          {sources.length} source{sources.length !== 1 ? "s" : ""} retrieved
        </span>
        <div className="flex-1" />
        <motion.div
          animate={{ rotate: expanded ? 180 : 0 }}
          transition={{ duration: 0.2 }}
        >
          <ChevronDown size={13} style={{ color: "var(--text-muted)" }} />
        </motion.div>
      </button>

      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.25, ease: EASE_OUT }}
            className="overflow-hidden"
          >
            <div className="px-4 pb-3 flex flex-col gap-2" style={{ borderTop: "1px solid var(--border)" }}>
              {sources.map((source, index) => (
                <motion.div
                  key={source.chunk_id}
                  className="relative rounded-xl px-3 py-3 mt-2 overflow-hidden"
                  style={{
                    background: "var(--bg-tertiary)",
                    border: "1px solid var(--border)",
                  }}
                  initial={{ opacity: 0, x: -6 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: index * 0.04, duration: 0.25 }}
                  whileHover={{ borderColor: "var(--border-hover)" }}
                >
                  {/* [typography] Changed text-[11px] to text-xs for minimum readable size */}
                  {(() => {
                    const pct = Math.max(0, Math.min(100, Math.round(source.score * 100)));
                    const tier =
                      source.score >= 0.75
                        ? { label: "Strong", icon: <CheckCircle2 size={10} />, color: "var(--provenance-strong)", bg: "var(--provenance-strong-soft)" }
                        : source.score >= 0.45
                        ? { label: "Good", icon: <MinusCircle size={10} />, color: "var(--confidence-med)", bg: "var(--confidence-med-soft)" }
                        : { label: "Weak", icon: <AlertCircle size={10} />, color: "var(--provenance-weak)", bg: "var(--provenance-weak-soft)" };
                    return (
                      <>
                        <div
                          className="absolute left-0 top-0 bottom-0 w-[3px] rounded-l-xl"
                          style={{ background: tier.color, opacity: 0.7 }}
                          aria-hidden="true"
                        />
                        <div className="flex items-center gap-2 mb-1.5 text-[10px] flex-wrap">
                          <span
                            className="px-1.5 py-0.5 rounded-md font-semibold"
                            style={{ background: "var(--accent-brand-soft)", color: "var(--accent-brand)" }}
                          >
                            [{index + 1}]
                          </span>
                          <span
                            className="flex items-center gap-1 px-1.5 py-0.5 rounded-md font-medium"
                            style={{ background: tier.bg, color: tier.color }}
                          >
                            {tier.icon}
                            {tier.label} · {pct}%
                          </span>
                          {source.page_number ? (
                            <span className="uppercase tracking-widest" style={{ color: "var(--text-muted)" }}>p.{source.page_number}</span>
                          ) : null}
                          <span className="uppercase tracking-widest truncate max-w-[120px]" style={{ color: "var(--text-muted)" }} title={source.chunk_id}>
                            {source.chunk_id}
                          </span>
                        </div>
                      </>
                    );
                  })()}
                  <p className="text-xs leading-relaxed" style={{ color: "var(--text-secondary)" }}>
                    {source.excerpt}
                  </p>
                </motion.div>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
});

export default SourceCard;

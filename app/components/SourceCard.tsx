"use client";

import React, { useState } from "react";
import { BookOpen, ChevronDown, ChevronUp } from "lucide-react";
import type { Citation } from "../lib/api";

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
    <div
      className="rounded-xl animate-fade-in"
      style={{
        background: "var(--bg-surface)",
        border: "1px solid var(--border)",
        overflow: "hidden",
      }}
    >
      {/* [a11y] Added aria-expanded to communicate toggle state to assistive technology */}
      <button
        type="button"
        onClick={() => setExpanded((current) => !current)}
        aria-expanded={expanded}
        className="w-full flex items-center gap-2 px-4 py-2.5 transition-colors"
        style={{ background: expanded ? "var(--bg-tertiary)" : "transparent" }}
      >
        <BookOpen size={14} style={{ color: "var(--accent)", flexShrink: 0 }} />
        <span className="text-xs font-semibold" style={{ color: "var(--text-secondary)" }}>
          {sources.length} source{sources.length !== 1 ? "s" : ""} retrieved
        </span>
        <div className="flex-1" />
        {expanded ? (
          <ChevronUp size={14} style={{ color: "var(--text-tertiary)" }} />
        ) : (
          <ChevronDown size={14} style={{ color: "var(--text-tertiary)" }} />
        )}
      </button>

      {expanded && (
        <div className="px-4 pb-3 flex flex-col gap-3" style={{ borderTop: "1px solid var(--border)" }}>
          {sources.map((source, index) => (
            <div
              key={source.chunk_id}
              className="rounded-lg px-3 py-3 mt-3"
              style={{
                background: "var(--bg-tertiary)",
                border: "1px solid var(--border)",
              }}
            >
              {/* [typography] Changed text-[11px] to text-xs for minimum readable size */}
              <div className="flex items-center gap-2 mb-2 text-xs uppercase tracking-wider">
                <span
                  className="px-1.5 py-0.5 rounded"
                  style={{ background: "var(--accent)", color: "var(--accent-fg)" }}
                >
                  [{index + 1}]
                </span>
                <span style={{ color: "var(--text-tertiary)" }}>{source.chunk_id}</span>
                {source.page_number ? (
                  <span style={{ color: "var(--text-tertiary)" }}>Page {source.page_number}</span>
                ) : null}
                <span style={{ color: "var(--text-tertiary)" }}>
                  {Math.max(0, Math.min(100, Math.round(source.score * 100)))}% match
                </span>
              </div>
              <p className="text-xs leading-relaxed" style={{ color: "var(--text-secondary)" }}>
                {source.excerpt}
              </p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
});

export default SourceCard;

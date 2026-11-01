"use client";

import { AnimatePresence, motion } from "framer-motion";
import React, {
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
} from "react";
import { createPortal } from "react-dom";

import { type Citation } from "../lib/api";
import { EASE_OUT } from "../lib/motion";

/**
 * Hover/focus preview card for a citation chip.
 *
 * Replaces native `title` tooltips, whose ~1s browser-imposed delay and
 * unstyled OS rendering made citation previews feel broken. The card is
 * portaled and position: fixed so it never clips inside the chat scroller.
 *
 * Wrap any chip element as this component's child; the wrapper listens for
 * hover/focus, so the chip keeps its own styling and click behavior.
 */

const OPEN_DELAY_MS = 150;
const CLOSE_DELAY_MS = 90;
const CARD_WIDTH = 320;
const ESTIMATED_CARD_HEIGHT = 230;

function scoreColor(score: number): string {
  if (!Number.isFinite(score)) return "var(--text-muted)";
  if (score >= 0.8) return "var(--confidence-high)";
  if (score >= 0.6) return "var(--confidence-med)";
  return "var(--confidence-low)";
}

export function CitationPreview({
  citation,
  children,
}: {
  citation: Citation;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const [position, setPosition] = useState<{
    top: number;
    left: number;
    placeAbove: boolean;
  } | null>(null);
  const openTimer = useRef<number | null>(null);
  const closeTimer = useRef<number | null>(null);
  const tooltipId = useId();

  const clearTimers = useCallback(() => {
    if (openTimer.current !== null) {
      window.clearTimeout(openTimer.current);
      openTimer.current = null;
    }
    if (closeTimer.current !== null) {
      window.clearTimeout(closeTimer.current);
      closeTimer.current = null;
    }
  }, []);

  const show = useCallback(
    (target: HTMLElement) => {
      clearTimers();
      openTimer.current = window.setTimeout(() => {
        const rect = target.getBoundingClientRect();
        const placeAbove =
          rect.bottom + ESTIMATED_CARD_HEIGHT > window.innerHeight &&
          rect.top > ESTIMATED_CARD_HEIGHT;
        const left = Math.min(
          Math.max(12, rect.left),
          Math.max(12, window.innerWidth - CARD_WIDTH - 12),
        );
        setPosition({
          top: placeAbove ? rect.top - 10 : rect.bottom + 10,
          left,
          placeAbove,
        });
        setOpen(true);
      }, OPEN_DELAY_MS);
    },
    [clearTimers],
  );

  const hide = useCallback(() => {
    clearTimers();
    closeTimer.current = window.setTimeout(() => setOpen(false), CLOSE_DELAY_MS);
  }, [clearTimers]);

  useEffect(() => clearTimers, [clearTimers]);

  useEffect(() => {
    if (!open) return;
    const closeNow = () => {
      clearTimers();
      setOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") closeNow();
    };
    document.addEventListener("keydown", onKey);
    window.addEventListener("scroll", closeNow, true);
    return () => {
      document.removeEventListener("keydown", onKey);
      window.removeEventListener("scroll", closeNow, true);
    };
  }, [open, clearTimers]);

  return (
    <span
      className="inline-flex"
      aria-describedby={open ? tooltipId : undefined}
      onMouseEnter={(event) => show(event.currentTarget)}
      onMouseLeave={hide}
      onFocus={(event) => show(event.currentTarget)}
      onBlur={hide}
      onClickCapture={() => { clearTimers(); setOpen(false); }}
    >
      {children}
      {createPortal(
        <AnimatePresence>
          {open && position ? (
            <motion.div
              id={tooltipId}
              role="tooltip"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.12, ease: EASE_OUT }}
              style={{
                position: "fixed",
                top: position.top,
                left: position.left,
                width: CARD_WIDTH,
                maxWidth: "calc(100vw - 24px)",
                transform: position.placeAbove ? "translateY(-100%)" : undefined,
                background: "var(--bg-elevated)",
                border: "1px solid var(--border-hover)",
                borderRadius: "var(--radius-md)",
                boxShadow: "var(--shadow-lg)",
                padding: 12,
                zIndex: 70,
                pointerEvents: "none",
              }}
            >
              <div
                className="flex items-center justify-between gap-3 pb-2 mb-2"
                style={{ borderBottom: "1px solid var(--border)" }}
              >
                <span
                  className="text-[10px] font-semibold uppercase tracking-widest"
                  style={{ color: "var(--text-tertiary)" }}
                >
                  {citation.page_number ? `Page ${citation.page_number}` : "Excerpt"}
                </span>
                {Number.isFinite(citation.score) ? (
                  <span className="flex items-baseline gap-1.5">
                    <span
                      className="text-[10px] uppercase tracking-widest"
                      style={{ color: "var(--text-tertiary)" }}
                    >
                      relevance
                    </span>
                    <span
                      className="data-num text-[12px] font-semibold"
                      style={{ color: scoreColor(citation.score) }}
                    >
                      {citation.score.toFixed(2)}
                    </span>
                  </span>
                ) : null}
              </div>
              <p
                className="text-[12px] leading-relaxed"
                style={{
                  color: "var(--text-secondary)",
                  maxHeight: 132,
                  overflow: "hidden",
                }}
              >
                {citation.excerpt?.trim() || "(no excerpt available)"}
              </p>
            </motion.div>
          ) : null}
        </AnimatePresence>,
        document.body,
      )}
    </span>
  );
}

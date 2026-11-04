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

export function CitationPreview({
  citation,
  children,
  suppressMobilePreview = false,
}: {
  citation: Citation;
  children: React.ReactNode;
  suppressMobilePreview?: boolean;
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
      if (suppressMobilePreview && window.matchMedia("(max-width: 767px)").matches) return;
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
    [clearTimers, suppressMobilePreview],
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
    window.addEventListener("resize", closeNow);
    return () => {
      document.removeEventListener("keydown", onKey);
      window.removeEventListener("scroll", closeNow, true);
      window.removeEventListener("resize", closeNow);
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
      onClickCapture={(event) => {
        if (!suppressMobilePreview && window.matchMedia("(max-width: 767px)").matches && !open) {
          show(event.currentTarget);
          return;
        }
        clearTimers();
        setOpen(false);
      }}
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

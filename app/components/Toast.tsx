"use client";

import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { CheckCircle2, AlertCircle, Info, X, AlertTriangle } from "lucide-react";
import { EASE_OUT } from "../lib/motion";

export type ToastVariant = "success" | "error" | "info" | "warning";

export interface Toast {
  id: string;
  title: string;
  description?: string;
  variant: ToastVariant;
  duration?: number;
}

interface ToastContextValue {
  toast: (t: Omit<Toast, "id">) => string;
  dismiss: (id: string) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used inside ToastProvider");
  return ctx;
}

const VARIANT_META: Record<ToastVariant, { color: string; soft: string; icon: React.ReactNode }> = {
  success: { color: "var(--confidence-high)", soft: "var(--confidence-high-soft)", icon: <CheckCircle2 size={14} /> },
  error:   { color: "var(--confidence-low)",  soft: "var(--confidence-low-soft)",  icon: <AlertCircle size={14} /> },
  warning: { color: "var(--confidence-med)",  soft: "var(--confidence-med-soft)",  icon: <AlertTriangle size={14} /> },
  info:    { color: "var(--accent-brand)",    soft: "var(--accent-brand-soft)",    icon: <Info size={14} /> },
};

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const timersRef = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map());

  const dismiss = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
    const timer = timersRef.current.get(id);
    if (timer) {
      clearTimeout(timer);
      timersRef.current.delete(id);
    }
  }, []);

  const toast = useCallback(
    (t: Omit<Toast, "id">): string => {
      const id = crypto.randomUUID?.() ?? Math.random().toString(36).slice(2);
      const duration = t.duration ?? 4000;
      setToasts((prev) => [...prev, { ...t, id }]);
      if (duration > 0) {
        const timer = setTimeout(() => dismiss(id), duration);
        timersRef.current.set(id, timer);
      }
      return id;
    },
    [dismiss]
  );

  useEffect(() => {
    const timers = timersRef.current;
    return () => {
      timers.forEach((t) => clearTimeout(t));
      timers.clear();
    };
  }, []);

  return (
    <ToastContext.Provider value={{ toast, dismiss }}>
      {children}
      <div
        className="fixed top-4 right-4 z-[70] flex flex-col gap-2 pointer-events-none"
        style={{ maxWidth: 380 }}
        aria-live="polite"
        aria-atomic="true"
      >
        <AnimatePresence initial={false}>
          {toasts.map((t) => {
            const meta = VARIANT_META[t.variant];
            return (
              <motion.div
                key={t.id}
                layout
                initial={{ opacity: 0, x: 16, scale: 0.97 }}
                animate={{ opacity: 1, x: 0, scale: 1 }}
                exit={{ opacity: 0, x: 16, scale: 0.97 }}
                transition={{ duration: 0.22, ease: EASE_OUT }}
                className="pointer-events-auto rounded-xl overflow-hidden"
                style={{
                  background: "var(--bg-secondary)",
                  border: "1px solid var(--border-hover)",
                  boxShadow: "var(--shadow-lg)",
                  borderLeft: `3px solid ${meta.color}`,
                }}
                role="status"
              >
                <div className="flex items-start gap-2.5 px-3.5 py-3">
                  <span
                    className="flex items-center justify-center rounded-md shrink-0"
                    style={{ background: meta.soft, color: meta.color, width: 22, height: 22 }}
                  >
                    {meta.icon}
                  </span>
                  <div className="flex-1 min-w-0">
                    <div className="text-xs font-semibold" style={{ color: "var(--text-primary)" }}>
                      {t.title}
                    </div>
                    {t.description && (
                      <div className="text-[11px] mt-0.5 leading-relaxed" style={{ color: "var(--text-secondary)" }}>
                        {t.description}
                      </div>
                    )}
                  </div>
                  <button
                    type="button"
                    onClick={() => dismiss(t.id)}
                    aria-label="Dismiss"
                    className="shrink-0 rounded-md p-0.5"
                    style={{ color: "var(--text-muted)" }}
                  >
                    <X size={12} />
                  </button>
                </div>
              </motion.div>
            );
          })}
        </AnimatePresence>
      </div>
    </ToastContext.Provider>
  );
}

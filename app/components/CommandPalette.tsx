"use client";

import React, { useEffect, useMemo, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Command,
  FileText,
  MessageSquarePlus,
  Moon,
  Settings,
  Sun,
  Upload,
  X,
  Focus,
  LayoutPanelLeft,
  Library,
  Monitor,
  Contrast,
  Wind,
} from "lucide-react";
import { EASE_OUT } from "../lib/motion";
import { useStore } from "../lib/store";
import { useServerState } from "../lib/server-state";
import { useEscapeLayer } from "./ui/Modal";

interface CommandPaletteProps {
  open: boolean;
  onClose: () => void;
  onUpload: () => void;
  onSettings: () => void;
}

interface CommandItem {
  id: string;
  label: string;
  description?: string;
  icon: React.ReactNode;
  group: string;
  action: () => void;
  keywords?: string[];
  shortcut?: string[];
}

const FOCUSABLE =
  'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';

export default function CommandPalette({ open, onClose, onUpload, onSettings }: CommandPaletteProps) {
  return (
    <AnimatePresence>
      {open ? (
        <Palette key="palette" onClose={onClose} onUpload={onUpload} onSettings={onSettings} />
      ) : null}
    </AnimatePresence>
  );
}

/**
 * Mounted fresh on each open so query/selection state starts clean.
 * Implements dialog semantics, listbox navigation with
 * aria-activedescendant, a Tab cycle trap, and focus restore on close.
 */
function Palette({ onClose, onUpload, onSettings }: Omit<CommandPaletteProps, "open">) {
  const { state, dispatch } = useStore();
  const { documents, selectDocument, selectConversation } = useServerState();
  const { settings } = state;
  const [query, setQuery] = useState("");
  const [selectedIdx, setSelectedIdx] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const restoreRef = useRef<HTMLElement | null>(null);

  // DOM-only side effects: focus the input on mount, restore on unmount.
  useEffect(() => {
    restoreRef.current = document.activeElement as HTMLElement | null;
    inputRef.current?.focus();
    return () => restoreRef.current?.focus({ preventScroll: true });
  }, []);

  // Join Modal's Escape stack so Escape closes the palette rather than a
  // Modal stacked underneath it (Modal's document-capture listener calls
  // stopImmediatePropagation, which otherwise swallows the key first).
  useEscapeLayer(true, onClose);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        onClose();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onClose]);

  const staticCommands: CommandItem[] = useMemo(
    () => [
      {
        id: "library",
        label: "Open library",
        description: "Browse and find your documents",
        icon: <Library size={14} />,
        group: "Actions",
        action: () => {
          void selectDocument(null);
          onClose();
        },
        keywords: ["library", "home", "documents", "browse"],
      },
      {
        id: "upload",
        label: "Upload Document",
        description: "Index a new PDF, DOCX, or text file",
        icon: <Upload size={14} />,
        group: "Actions",
        action: () => {
          onUpload();
          onClose();
        },
        keywords: ["upload", "add", "file", "index"],
        shortcut: ["⌘", "U"],
      },
      {
        id: "new-chat",
        label: "New Chat",
        description: "Start a fresh conversation",
        icon: <MessageSquarePlus size={14} />,
        group: "Actions",
        action: () => {
          void selectConversation(null);
          onClose();
        },
        keywords: ["new", "chat", "conversation", "fresh"],
      },
      {
        id: "settings",
        label: "Open Settings",
        description: "Configure provider, models, and display",
        icon: <Settings size={14} />,
        group: "Actions",
        action: () => {
          onSettings();
          onClose();
        },
        keywords: ["settings", "config", "key", "api"],
        shortcut: ["⌘", ","],
      },
      {
        id: "theme",
        label: settings.theme === "dark" ? "Switch to Light Mode" : "Switch to Dark Mode",
        icon: settings.theme === "dark" ? <Sun size={14} /> : <Moon size={14} />,
        group: "Display",
        action: () => {
          dispatch({ type: "SET_SETTINGS", payload: { theme: settings.theme === "dark" ? "light" : "dark" } });
          onClose();
        },
        keywords: ["theme", "dark", "light", "mode"],
      },
      {
        id: "contrast",
        label: settings.highContrast ? "Disable High Contrast" : "Enable High Contrast",
        icon: <Contrast size={14} />,
        group: "Display",
        action: () => {
          dispatch({ type: "SET_SETTINGS", payload: { highContrast: !settings.highContrast } });
          onClose();
        },
        keywords: ["contrast", "accessibility", "a11y"],
      },
      {
        id: "motion",
        label: settings.reducedMotion ? "Enable Motion" : "Reduce Motion",
        icon: <Wind size={14} />,
        group: "Display",
        action: () => {
          dispatch({ type: "SET_SETTINGS", payload: { reducedMotion: !settings.reducedMotion } });
          onClose();
        },
        keywords: ["motion", "animation", "reduce", "accessibility"],
      },
      {
        id: "layout-default",
        label: "Default Layout",
        icon: <Monitor size={14} />,
        group: "Layout",
        action: () => {
          dispatch({ type: "SET_SETTINGS", payload: { chatLayout: "default" } });
          onClose();
        },
        keywords: ["layout", "default", "normal"],
      },
      {
        id: "layout-focus",
        label: "Focus Mode",
        description: "Wider content, minimal chrome",
        icon: <Focus size={14} />,
        group: "Layout",
        action: () => {
          dispatch({ type: "SET_SETTINGS", payload: { chatLayout: "focus" } });
          onClose();
        },
        keywords: ["layout", "focus", "wide", "zen"],
      },
      {
        id: "layout-research",
        label: "Research Mode",
        description: "Maximum content width for dense work",
        icon: <LayoutPanelLeft size={14} />,
        group: "Layout",
        action: () => {
          dispatch({ type: "SET_SETTINGS", payload: { chatLayout: "research" } });
          onClose();
        },
        keywords: ["layout", "research", "full", "wide"],
      },
    ],
    [settings, onUpload, onSettings, onClose, dispatch, selectConversation],
  );

  const docCommands: CommandItem[] = useMemo(
    () =>
      documents.map((doc) => ({
        id: `doc-${doc.id}`,
        label: doc.filename,
        description: `${doc.chunk_count} chunks · ${doc.status}`,
        icon: <FileText size={14} />,
        group: "Documents",
        action: () => {
          void selectDocument(doc.id);
          onClose();
        },
        keywords: [doc.filename.toLowerCase()],
      })),
    [documents, selectDocument, onClose],
  );

  const filtered = useMemo(() => {
    const all = [...staticCommands, ...docCommands];
    const q = query.trim().toLowerCase();
    if (!q) return all;
    return all.filter(
      (cmd) =>
        cmd.label.toLowerCase().includes(q) ||
        cmd.description?.toLowerCase().includes(q) ||
        cmd.keywords?.some((k) => k.includes(q)),
    );
  }, [query, staticCommands, docCommands]);

  const grouped = useMemo(() => {
    const map = new Map<string, CommandItem[]>();
    for (const cmd of filtered) {
      if (!map.has(cmd.group)) map.set(cmd.group, []);
      map.get(cmd.group)!.push(cmd);
    }
    return map;
  }, [filtered]);

  const currentIdx = Math.min(selectedIdx, Math.max(0, filtered.length - 1));
  const activeId = filtered[currentIdx] ? `cmd-opt-${filtered[currentIdx].id}` : undefined;

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Tab") {
      // Cycle focus inside the palette. Bound on the panel (not the input) so
      // Tab from the footer or a result row cannot walk out of an aria-modal
      // dialog; `getClientRects` keeps `position: fixed` children in the cycle.
      const panel = panelRef.current;
      if (!panel) return;
      const focusables = Array.from(panel.querySelectorAll<HTMLElement>(FOCUSABLE)).filter(
        (el) => el.getClientRects().length > 0 || el === document.activeElement,
      );
      if (focusables.length === 0) return;
      const first = focusables[0];
      const last = focusables[focusables.length - 1];
      const active = document.activeElement as HTMLElement | null;
      const outside = !panel.contains(active) || active === panel;
      if (e.shiftKey) {
        if (outside || active === first) {
          e.preventDefault();
          last.focus();
        }
      } else if (outside || active === last) {
        e.preventDefault();
        first.focus();
      }
      return;
    }

    // Arrow/Enter drive the combobox, so only honour them from the search
    // input — otherwise Enter on the footer would fire both the focused
    // button and the highlighted command.
    if (e.target !== inputRef.current) return;

    if (e.key === "ArrowDown") {
      e.preventDefault();
      setSelectedIdx((i) => Math.min(i + 1, filtered.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setSelectedIdx((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      filtered[currentIdx]?.action();
    }
  };

  return (
    <motion.div
      className="fixed inset-0 z-[60] flex items-start justify-center pt-[15vh] px-4"
      style={{ background: "rgba(4, 6, 9, 0.55)" }}
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.15 }}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <motion.div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label="Command palette"
        className="w-full rounded-xl overflow-hidden"
        onKeyDown={handleKeyDown}
        style={{
          maxWidth: 560,
          background: "var(--bg-secondary)",
          border: "1px solid var(--border-hover)",
          boxShadow: "var(--shadow-lg)",
        }}
        initial={{ opacity: 0, scale: 0.98, y: -8 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.98, y: -8 }}
        transition={{ duration: 0.18, ease: EASE_OUT }}
      >
        <div className="flex items-center gap-3 px-4 py-3" style={{ borderBottom: "1px solid var(--border)" }}>
          <Command size={15} style={{ color: "var(--text-muted)", flexShrink: 0 }} />
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setSelectedIdx(0);
            }}
            placeholder="Type a command or search…"
            className="flex-1 bg-transparent text-sm outline-none rounded-lg px-2 py-1 focus-ring"
            style={{ color: "var(--text-primary)" }}
            aria-label="Command palette search"
            role="combobox"
            aria-expanded="true"
            aria-controls="cmd-listbox"
            aria-activedescendant={activeId}
          />
          {query ? (
            <button
              type="button"
              onClick={() => {
                setQuery("");
                setSelectedIdx(0);
                inputRef.current?.focus();
              }}
              style={{ color: "var(--text-muted)" }}
              aria-label="Clear search"
            >
              <X size={13} />
            </button>
          ) : (
            <span
              className="text-[10px] px-1.5 py-0.5 rounded data-num"
              style={{ background: "var(--bg-elevated)", color: "var(--text-muted)", border: "1px solid var(--border)" }}
            >
              ESC
            </span>
          )}
        </div>

        <div className="max-h-80 overflow-y-auto py-1" role="listbox" id="cmd-listbox" aria-label="Commands">
          {grouped.size === 0 ? (
            <p className="px-4 py-6 text-center text-sm" style={{ color: "var(--text-muted)" }}>
              No results for &ldquo;{query}&rdquo;
            </p>
          ) : (
            Array.from(grouped.entries()).map(([group, cmds]) => (
              <div key={group}>
                <p
                  className="px-4 py-1.5 text-[10px] font-semibold uppercase tracking-widest"
                  style={{ color: "var(--text-muted)" }}
                >
                  {group}
                </p>
                {cmds.map((cmd) => {
                  const idx = filtered.indexOf(cmd);
                  const active = idx === currentIdx;
                  return (
                    <button
                      key={cmd.id}
                      id={`cmd-opt-${cmd.id}`}
                      type="button"
                      role="option"
                      aria-selected={active}
                      onClick={cmd.action}
                      onMouseEnter={() => setSelectedIdx(idx)}
                      className="w-full flex items-center gap-3 px-4 py-2.5 text-left"
                      style={{
                        background: active ? "var(--accent-primary-soft)" : "transparent",
                        color: active ? "var(--text-primary)" : "var(--text-secondary)",
                      }}
                    >
                      <span style={{ color: active ? "var(--accent-primary)" : "var(--text-muted)" }}>{cmd.icon}</span>
                      <span className="flex-1 min-w-0">
                        <span className="text-sm font-medium">{cmd.label}</span>
                        {cmd.description ? (
                          <span className="block text-[11px] truncate" style={{ color: "var(--text-muted)" }}>
                            {cmd.description}
                          </span>
                        ) : null}
                      </span>
                      {cmd.shortcut ? (
                        <span className="flex items-center gap-1 flex-shrink-0">
                          {cmd.shortcut.map((k, i) => (
                            <kbd
                              key={i}
                              className="text-[10px] px-1.5 py-0.5 rounded data-num"
                              style={{
                                background: "var(--bg-elevated)",
                                color: "var(--text-tertiary)",
                                border: "1px solid var(--border)",
                                minWidth: 18,
                                textAlign: "center",
                              }}
                            >
                              {k}
                            </kbd>
                          ))}
                        </span>
                      ) : active ? (
                        <span
                          className="text-[10px] px-1.5 py-0.5 rounded flex-shrink-0 data-num"
                          style={{
                            background: "var(--accent-primary-soft)",
                            color: "var(--accent-primary)",
                            border: "1px solid var(--accent-primary)",
                          }}
                        >
                          ↵
                        </span>
                      ) : null}
                    </button>
                  );
                })}
              </div>
            ))
          )}
        </div>

        <div className="flex items-center gap-3 px-4 py-2" style={{ borderTop: "1px solid var(--border)" }}>
          {[
            ["↑↓", "Navigate"],
            ["↵", "Select"],
            ["⌘K", "Close"],
          ].map(([key, label]) => (
            <span key={key} className="flex items-center gap-1 text-[10px]" style={{ color: "var(--text-muted)" }}>
              <span
                className="px-1.5 py-0.5 rounded data-num"
                style={{ background: "var(--bg-elevated)", border: "1px solid var(--border)" }}
              >
                {key}
              </span>
              {label}
            </span>
          ))}
        </div>
      </motion.div>
    </motion.div>
  );
}

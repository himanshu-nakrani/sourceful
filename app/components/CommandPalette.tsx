"use client";

import React, { useEffect, useRef, useState, useMemo } from "react";
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
  Monitor,
  Contrast,
  Wind,
} from "lucide-react";
import { EASE_OUT } from "../lib/motion";
import { useStore } from "../lib/store";
import { useServerState } from "../lib/server-state";

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

export default function CommandPalette({ open, onClose, onUpload, onSettings }: CommandPaletteProps) {
  const { state, dispatch } = useStore();
  const { documents } = useServerState();
  const { settings } = state;
  const [query, setQuery] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (open) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setQuery("");
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [open]);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        if (open) onClose();
      }
      if (e.key === "Escape" && open) onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open, onClose]);

  const { selectDocument } = useServerState();

  const staticCommands: CommandItem[] = useMemo(() => [
    {
      id: "upload",
      label: "Upload Document",
      description: "Index a new PDF, DOCX, or text file",
      icon: <Upload size={14} />,
      group: "Actions",
      action: () => { onUpload(); onClose(); },
      keywords: ["upload", "add", "file", "index"],
      shortcut: ["⌘", "U"],
    },
    {
      id: "new-chat",
      label: "New Chat",
      description: "Start a fresh conversation",
      icon: <MessageSquarePlus size={14} />,
      group: "Actions",
      action: () => { dispatch({ type: "SET_ACTIVE_CONVERSATION", payload: null }); onClose(); },
      keywords: ["new", "chat", "conversation", "fresh"],
    },
    {
      id: "settings",
      label: "Open Settings",
      description: "Configure provider, models, and display",
      icon: <Settings size={14} />,
      group: "Actions",
      action: () => { onSettings(); onClose(); },
      keywords: ["settings", "config", "key", "api"],
      shortcut: ["⌘", ","],
    },
    {
      id: "theme",
      label: settings.theme === "dark" ? "Switch to Light Mode" : "Switch to Dark Mode",
      icon: settings.theme === "dark" ? <Sun size={14} /> : <Moon size={14} />,
      group: "Display",
      action: () => { dispatch({ type: "SET_SETTINGS", payload: { theme: settings.theme === "dark" ? "light" : "dark" } }); onClose(); },
      keywords: ["theme", "dark", "light", "mode"],
    },
    {
      id: "contrast",
      label: settings.highContrast ? "Disable High Contrast" : "Enable High Contrast",
      icon: <Contrast size={14} />,
      group: "Display",
      action: () => { dispatch({ type: "SET_SETTINGS", payload: { highContrast: !settings.highContrast } }); onClose(); },
      keywords: ["contrast", "accessibility", "a11y"],
    },
    {
      id: "motion",
      label: settings.reducedMotion ? "Enable Motion" : "Reduce Motion",
      icon: <Wind size={14} />,
      group: "Display",
      action: () => { dispatch({ type: "SET_SETTINGS", payload: { reducedMotion: !settings.reducedMotion } }); onClose(); },
      keywords: ["motion", "animation", "reduce", "accessibility"],
    },
    {
      id: "layout-default",
      label: "Default Layout",
      icon: <Monitor size={14} />,
      group: "Layout",
      action: () => { dispatch({ type: "SET_SETTINGS", payload: { chatLayout: "default" } }); onClose(); },
      keywords: ["layout", "default", "normal"],
    },
    {
      id: "layout-focus",
      label: "Focus Mode",
      description: "Wider content, minimal chrome",
      icon: <Focus size={14} />,
      group: "Layout",
      action: () => { dispatch({ type: "SET_SETTINGS", payload: { chatLayout: "focus" } }); onClose(); },
      keywords: ["layout", "focus", "wide", "zen"],
    },
    {
      id: "layout-research",
      label: "Research Mode",
      description: "Maximum content width for dense work",
      icon: <LayoutPanelLeft size={14} />,
      group: "Layout",
      action: () => { dispatch({ type: "SET_SETTINGS", payload: { chatLayout: "research" } }); onClose(); },
      keywords: ["layout", "research", "full", "wide"],
    },
  ], [settings, onUpload, onSettings, onClose, dispatch]);

  const docCommands: CommandItem[] = useMemo(() =>
    documents.map((doc) => ({
      id: `doc-${doc.id}`,
      label: doc.filename,
      description: `${doc.chunk_count} chunks · ${doc.status}`,
      icon: <FileText size={14} />,
      group: "Documents",
      action: () => { void selectDocument(doc.id); onClose(); },
      keywords: [doc.filename.toLowerCase()],
    })),
    [documents, selectDocument, onClose]
  );

  const allCommands = useMemo(
    () => [...staticCommands, ...docCommands],
    [staticCommands, docCommands]
  );

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return allCommands;
    return allCommands.filter(
      (cmd) =>
        cmd.label.toLowerCase().includes(q) ||
        cmd.description?.toLowerCase().includes(q) ||
        cmd.keywords?.some((k) => k.includes(q))
    );
  }, [query, allCommands]);

  const grouped = useMemo(() => {
    const map = new Map<string, CommandItem[]>();
    for (const cmd of filtered) {
      if (!map.has(cmd.group)) map.set(cmd.group, []);
      map.get(cmd.group)!.push(cmd);
    }
    return map;
  }, [filtered]);

  const flatList = filtered;
  const [selectedIdx, setSelectedIdx] = useState(0);
  const currentIdx = Math.min(selectedIdx, Math.max(0, flatList.length - 1));

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setSelectedIdx((i) => Math.min(i + 1, flatList.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setSelectedIdx((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      flatList[currentIdx]?.action();
    }
  };

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className="fixed inset-0 z-[60] flex items-start justify-center pt-[15vh] px-4"
          style={{ background: "rgba(0,0,0,0.45)", backdropFilter: "blur(6px)" }}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
        >
          <motion.div
            className="w-full rounded-2xl overflow-hidden shadow-2xl"
            style={{
              maxWidth: 560,
              background: "var(--bg-secondary)",
              border: "1px solid var(--border-hover)",
              boxShadow: "var(--shadow-lg), 0 0 0 1px var(--focus-ring)",
            }}
            initial={{ opacity: 0, scale: 0.96, y: -8 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.96, y: -8 }}
            transition={{ duration: 0.18, ease: EASE_OUT }}
          >
            {/* Search input */}
            <div
              className="flex items-center gap-3 px-4 py-3"
              style={{ borderBottom: "1px solid var(--border)" }}
            >
              <Command size={15} style={{ color: "var(--text-muted)", flexShrink: 0 }} />
              <input
                ref={inputRef}
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Type a command or search…"
                className="flex-1 bg-transparent text-sm outline-none"
                style={{ color: "var(--text-primary)" }}
                aria-label="Command palette search"
              />
              {query ? (
                <button
                  type="button"
                  onClick={() => setQuery("")}
                  style={{ color: "var(--text-muted)" }}
                  aria-label="Clear search"
                >
                  <X size={13} />
                </button>
              ) : (
                <span
                  className="text-[10px] px-1.5 py-0.5 rounded"
                  style={{ background: "var(--bg-elevated)", color: "var(--text-muted)", border: "1px solid var(--border)" }}
                >
                  ESC
                </span>
              )}
            </div>

            {/* Results */}
            <div className="max-h-80 overflow-y-auto py-1">
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
                      const idx = flatList.indexOf(cmd);
                      const active = idx === currentIdx;
                      return (
                        <motion.button
                          key={cmd.id}
                          type="button"
                          onClick={cmd.action}
                          onMouseEnter={() => { setSelectedIdx(idx); }}
                          className="w-full flex items-center gap-3 px-4 py-2.5 text-left"
                          style={{
                            background: active ? "var(--accent-brand-soft)" : "transparent",
                            color: active ? "var(--text-primary)" : "var(--text-secondary)",
                          }}
                        >
                          <span style={{ color: active ? "var(--accent-brand)" : "var(--text-muted)" }}>
                            {cmd.icon}
                          </span>
                          <span className="flex-1 min-w-0">
                            <span className="text-sm font-medium">{cmd.label}</span>
                            {cmd.description && (
                              <span className="block text-[11px] truncate" style={{ color: "var(--text-muted)" }}>
                                {cmd.description}
                              </span>
                            )}
                          </span>
                          {cmd.shortcut ? (
                            <span className="flex items-center gap-1 flex-shrink-0">
                              {cmd.shortcut.map((k, i) => (
                                <kbd
                                  key={i}
                                  className="text-[10px] px-1.5 py-0.5 rounded font-mono"
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
                              className="text-[10px] px-1.5 py-0.5 rounded flex-shrink-0"
                              style={{ background: "var(--accent-brand-soft)", color: "var(--accent-brand)", border: "1px solid var(--accent-brand)" }}
                            >
                              ↵
                            </span>
                          ) : null}
                        </motion.button>
                      );
                    })}
                  </div>
                ))
              )}
            </div>

            {/* Footer hint */}
            <div
              className="flex items-center gap-3 px-4 py-2"
              style={{ borderTop: "1px solid var(--border)" }}
            >
              {[["↑↓", "Navigate"], ["↵", "Select"], ["⌘K", "Close"]].map(([key, label]) => (
                <span key={key} className="flex items-center gap-1 text-[10px]" style={{ color: "var(--text-muted)" }}>
                  <span
                    className="px-1.5 py-0.5 rounded"
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
      )}
    </AnimatePresence>
  );
}

"use client";

import React, { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Check, ChevronDown, FolderPlus, Layers, Loader2 } from "lucide-react";
import { createWorkspace, listWorkspaces, type Workspace } from "../lib/api";
import { EASE_OUT } from "../lib/motion";
import { useStore } from "../lib/store";

/**
 * Phase 1 workspace switcher. Lives in the sidebar header and drives the
 * ``activeWorkspaceId`` in the global store. Also exposes an inline "New
 * workspace" form so users can spin up a workspace without leaving context.
 */
export default function WorkspaceSwitcher() {
  const { state, dispatch } = useStore();
  const { workspaces, activeWorkspaceId, workspacesLoading, workspacesError, settings, currentUser } = state;
  const [open, setOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  const auth = { clientSessionId: settings.clientSessionId, authToken: currentUser?.session_token };
  const active = workspaces.find((w) => w.id === activeWorkspaceId) ?? null;

  useEffect(() => {
    if (!open) return;
    const onDown = (event: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) {
        setOpen(false);
        setCreating(false);
        setSubmitError(null);
      }
    };
    window.addEventListener("mousedown", onDown);
    return () => window.removeEventListener("mousedown", onDown);
  }, [open]);

  const refreshWorkspaces = async () => {
    dispatch({ type: "SET_WORKSPACES_LOADING", payload: true });
    try {
      const next = await listWorkspaces(auth);
      dispatch({ type: "SET_WORKSPACES", payload: next });
      dispatch({ type: "SET_WORKSPACES_ERROR", payload: null });
    } catch (err) {
      dispatch({
        type: "SET_WORKSPACES_ERROR",
        payload: err instanceof Error ? err.message : "Failed to load workspaces.",
      });
    } finally {
      dispatch({ type: "SET_WORKSPACES_LOADING", payload: false });
    }
  };

  const handleSelect = (workspace: Workspace) => {
    dispatch({ type: "SET_ACTIVE_WORKSPACE", payload: workspace.id });
    dispatch({ type: "SET_ACTIVE_DOCUMENT", payload: null });
    setOpen(false);
  };

  const handleCreate = async () => {
    const name = newName.trim();
    if (!name) {
      setSubmitError("Workspace name is required.");
      return;
    }
    setSubmitting(true);
    setSubmitError(null);
    try {
      const created = await createWorkspace(auth, { name });
      dispatch({ type: "UPSERT_WORKSPACE", payload: created });
      dispatch({ type: "SET_ACTIVE_WORKSPACE", payload: created.id });
      dispatch({ type: "SET_ACTIVE_DOCUMENT", payload: null });
      setNewName("");
      setCreating(false);
      setOpen(false);
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : "Failed to create workspace.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div ref={rootRef} className="relative px-3 pt-2 pb-1 flex-shrink-0">
      <motion.button
        type="button"
        onClick={() => {
          setOpen((prev) => !prev);
          if (!open && workspaces.length === 0 && !workspacesLoading) {
            void refreshWorkspaces();
          }
        }}
        className="w-full flex items-center gap-2 px-3 py-2 rounded-xl text-xs"
        style={{
          background: "var(--bg-surface)",
          color: "var(--text-primary)",
          border: "1px solid var(--border)",
        }}
        whileHover={{ borderColor: "var(--border-hover)" }}
        whileTap={{ scale: 0.98 }}
        aria-haspopup="listbox"
        aria-expanded={open}
        title="Switch workspace"
      >
        <Layers size={13} style={{ color: "var(--accent-brand)" }} />
        <div className="flex-1 min-w-0 text-left">
          <div className="text-[10px] uppercase tracking-widest" style={{ color: "var(--text-muted)" }}>
            Workspace
          </div>
          <div className="text-xs font-semibold truncate">
            {workspacesLoading && !active ? "Loading…" : active ? active.name : "Select workspace"}
          </div>
        </div>
        <ChevronDown size={13} style={{ color: "var(--text-muted)" }} />
      </motion.button>

      <AnimatePresence>
        {open ? (
          <motion.div
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            transition={{ duration: 0.18, ease: EASE_OUT }}
            className="absolute left-3 right-3 mt-1 z-40 rounded-xl overflow-hidden"
            style={{
              background: "var(--bg-secondary)",
              border: "1px solid var(--border)",
              boxShadow: "0 12px 24px rgba(0,0,0,0.2)",
            }}
            role="listbox"
          >
            {workspacesError ? (
              <div
                className="px-3 py-2 text-[11px]"
                style={{ background: "var(--error-soft)", color: "var(--error)" }}
              >
                {workspacesError}
                <button
                  type="button"
                  onClick={() => void refreshWorkspaces()}
                  className="ml-2 underline"
                >
                  retry
                </button>
              </div>
            ) : null}
            <ul className="max-h-60 overflow-y-auto">
              {workspaces.length === 0 && !workspacesLoading ? (
                <li className="px-3 py-3 text-[11px]" style={{ color: "var(--text-muted)" }}>
                  No workspaces yet.
                </li>
              ) : null}
              {workspacesLoading && workspaces.length === 0 ? (
                <li
                  className="px-3 py-3 text-[11px] flex items-center gap-2"
                  style={{ color: "var(--text-muted)" }}
                >
                  <Loader2 size={11} className="animate-spin" /> Loading workspaces…
                </li>
              ) : null}
              {workspaces.map((ws) => (
                <li key={ws.id} role="option" aria-selected={ws.id === activeWorkspaceId}>
                  <button
                    type="button"
                    onClick={() => handleSelect(ws)}
                    className="w-full flex items-center gap-2 px-3 py-2 text-left text-xs"
                    style={{
                      background:
                        ws.id === activeWorkspaceId ? "var(--accent-brand-soft)" : "transparent",
                      color: "var(--text-primary)",
                    }}
                  >
                    <span className="flex-1 truncate">
                      {ws.name}
                      {ws.is_default ? (
                        <span
                          className="ml-2 text-[10px] uppercase tracking-widest"
                          style={{ color: "var(--text-muted)" }}
                        >
                          default
                        </span>
                      ) : null}
                    </span>
                    {ws.id === activeWorkspaceId ? (
                      <Check size={12} style={{ color: "var(--accent-brand)" }} />
                    ) : null}
                  </button>
                </li>
              ))}
            </ul>

            <div style={{ borderTop: "1px solid var(--border)" }}>
              {creating ? (
                <div className="px-3 py-2 flex flex-col gap-2">
                  <input
                    autoFocus
                    value={newName}
                    onChange={(e) => setNewName(e.target.value)}
                    placeholder="Workspace name"
                    aria-label="Workspace name"
                    className="w-full bg-transparent text-xs outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[var(--accent)] rounded-lg px-2 py-1.5"
                    style={{
                      color: "var(--text-primary)",
                      background: "var(--bg-surface)",
                      border: "1px solid var(--border)",
                    }}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") {
                        e.preventDefault();
                        void handleCreate();
                      } else if (e.key === "Escape") {
                        setCreating(false);
                        setSubmitError(null);
                      }
                    }}
                  />
                  {submitError ? (
                    <span className="text-[11px]" style={{ color: "var(--error)" }}>
                      {submitError}
                    </span>
                  ) : null}
                  <div className="flex items-center gap-2">
                    <motion.button
                      type="button"
                      onClick={() => void handleCreate()}
                      disabled={submitting}
                      className="px-2 py-1 rounded-lg text-[11px] font-medium"
                      style={{
                        background: submitting ? "var(--bg-elevated)" : "var(--accent)",
                        color: submitting ? "var(--text-muted)" : "var(--accent-fg)",
                      }}
                      whileTap={{ scale: 0.96 }}
                    >
                      {submitting ? "Creating…" : "Create"}
                    </motion.button>
                    <button
                      type="button"
                      onClick={() => {
                        setCreating(false);
                        setSubmitError(null);
                      }}
                      className="px-2 py-1 rounded-lg text-[11px]"
                      style={{ color: "var(--text-muted)" }}
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              ) : (
                <button
                  type="button"
                  onClick={() => {
                    setCreating(true);
                    setSubmitError(null);
                  }}
                  className="w-full flex items-center gap-2 px-3 py-2 text-left text-xs"
                  style={{ color: "var(--accent-brand)" }}
                >
                  <FolderPlus size={12} /> New workspace
                </button>
              )}
            </div>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </div>
  );
}

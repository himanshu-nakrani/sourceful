"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Loader2, Plus, StickyNote, Trash2, X } from "lucide-react";
import {
  createArtifact,
  deleteArtifact,
  listArtifacts,
  updateArtifact,
  type Artifact,
  type ArtifactType,
  type ClientAuthContext,
} from "../lib/api";
import { useWorkspaceRole } from "../lib/use-workspace-role";
import { EASE_OUT } from "../lib/motion";

interface WorkspaceNotesPanelProps {
  open: boolean;
  onClose: () => void;
  workspaceId: string;
  workspaceName: string;
  auth: ClientAuthContext;
}

const TABS: { key: ArtifactType | "all"; label: string }[] = [
  { key: "all", label: "All" },
  { key: "user_note", label: "Notes" },
  { key: "saved_answer", label: "Saved answers" },
  { key: "saved_brief", label: "Briefs" },
  { key: "extraction_result", label: "Extractions" },
];

const TYPE_LABEL: Record<ArtifactType, string> = {
  user_note: "Note",
  saved_answer: "Saved answer",
  saved_brief: "Brief",
  extraction_result: "Extraction",
};

/**
 * Phase 2: durable workspace artifacts (user notes + saved chat answers +
 * extracted briefs). The panel is a focused overlay so it can grow into a
 * dedicated route later without disturbing the chat UI.
 */
export default function WorkspaceNotesPanel({
  open,
  onClose,
  workspaceId,
  workspaceName,
  auth,
}: WorkspaceNotesPanelProps) {
  const [activeTab, setActiveTab] = useState<ArtifactType | "all">("all");
  const [items, setItems] = useState<Artifact[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [draftTitle, setDraftTitle] = useState("");
  const [draftContent, setDraftContent] = useState("");
  const [creating, setCreating] = useState(false);
  const [busy, setBusy] = useState(false);

  const { canEdit } = useWorkspaceRole(auth, workspaceId);

  const filterType: ArtifactType | undefined =
    activeTab === "all" ? undefined : activeTab;

  const refresh = useCallback(async () => {
    if (!open) return;
    setLoading(true);
    setError(null);
    try {
      const list = await listArtifacts(auth, workspaceId, filterType);
      setItems(list);
      // If the previously selected artifact disappeared (deleted or filtered
      // out), drop the selection so the right pane shows the empty state.
      if (selectedId && !list.find((a) => a.id === selectedId)) {
        setSelectedId(null);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load artifacts.");
    } finally {
      setLoading(false);
    }
  }, [auth, workspaceId, filterType, open, selectedId]);

  useEffect(() => {
    if (open) void refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, workspaceId, activeTab]);

  // Hydrate the editor when the user picks an item.
  const selected = useMemo(
    () => items.find((a) => a.id === selectedId) ?? null,
    [items, selectedId]
  );
  useEffect(() => {
    if (selected) {
      setDraftTitle(selected.title);
      setDraftContent(selected.content);
      setCreating(false);
    }
  }, [selected]);

  const startCreate = () => {
    setSelectedId(null);
    setCreating(true);
    setDraftTitle("");
    setDraftContent("");
  };

  const handleSave = async () => {
    if (!draftTitle.trim() || !draftContent.trim()) {
      setError("Title and content are required.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      if (creating) {
        const created = await createArtifact(auth, workspaceId, {
          artifact_type: filterType ?? "user_note",
          title: draftTitle.trim(),
          content: draftContent,
        });
        setItems((prev) => [created, ...prev]);
        setSelectedId(created.id);
        setCreating(false);
      } else if (selected) {
        const updated = await updateArtifact(auth, workspaceId, selected.id, {
          title: draftTitle.trim(),
          content: draftContent,
        });
        setItems((prev) => prev.map((a) => (a.id === updated.id ? updated : a)));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save artifact.");
    } finally {
      setBusy(false);
    }
  };

  const handleDelete = async () => {
    if (!selected) return;
    if (!window.confirm(`Delete "${selected.title}"?`)) return;
    setBusy(true);
    setError(null);
    try {
      await deleteArtifact(auth, workspaceId, selected.id);
      setItems((prev) => prev.filter((a) => a.id !== selected.id));
      setSelectedId(null);
      setCreating(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete artifact.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <AnimatePresence>
      {open ? (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.18, ease: EASE_OUT }}
          className="fixed inset-0 z-50 flex items-center justify-center"
          style={{ background: "rgba(0,0,0,0.5)" }}
          onMouseDown={(e) => {
            if (e.target === e.currentTarget) onClose();
          }}
        >
          <motion.div
            initial={{ opacity: 0, scale: 0.96 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.96 }}
            transition={{ duration: 0.2, ease: EASE_OUT }}
            className="w-[min(960px,94vw)] h-[min(680px,86vh)] flex flex-col rounded-2xl overflow-hidden"
            style={{
              background: "var(--bg-primary)",
              border: "1px solid var(--border)",
              boxShadow: "0 24px 48px rgba(0,0,0,0.35)",
            }}
          >
            <header
              className="flex items-center justify-between px-4 py-3 flex-shrink-0"
              style={{ borderBottom: "1px solid var(--border)" }}
            >
              <div className="flex items-center gap-2">
                <StickyNote size={14} style={{ color: "var(--accent-brand)" }} />
                <h2 className="text-sm font-semibold">Notes &amp; saved answers</h2>
                <span
                  className="text-[10px] uppercase tracking-widest"
                  style={{ color: "var(--text-muted)" }}
                >
                  {workspaceName}
                </span>
              </div>
              <button
                type="button"
                onClick={onClose}
                className="p-1.5 rounded-lg"
                style={{ color: "var(--text-muted)" }}
                aria-label="Close notes panel"
              >
                <X size={14} />
              </button>
            </header>

            <div className="flex-1 min-h-0 flex">
              {/* Left rail — tabs + list */}
              <aside
                className="w-64 flex-shrink-0 flex flex-col"
                style={{ borderRight: "1px solid var(--border)" }}
              >
                <div
                  className="flex flex-wrap gap-1 p-2 flex-shrink-0"
                  style={{ borderBottom: "1px solid var(--border)" }}
                >
                  {TABS.map((tab) => {
                    const active = tab.key === activeTab;
                    return (
                      <button
                        key={tab.key}
                        type="button"
                        onClick={() => setActiveTab(tab.key)}
                        className="text-[10px] px-2 py-0.5 rounded-md"
                        style={{
                          background: active ? "var(--accent-brand-soft)" : "transparent",
                          color: active ? "var(--accent-brand)" : "var(--text-muted)",
                          border: "1px solid var(--border)",
                        }}
                      >
                        {tab.label}
                      </button>
                    );
                  })}
                </div>
                {canEdit ? (
                  <div className="p-2 flex-shrink-0">
                    <button
                      type="button"
                      onClick={startCreate}
                      className="w-full flex items-center gap-1.5 px-2 py-1.5 rounded-lg text-xs"
                      style={{
                        background: "var(--accent-brand-soft)",
                        color: "var(--accent-brand)",
                        border: "1px solid var(--border)",
                      }}
                    >
                      <Plus size={12} /> New note
                    </button>
                  </div>
                ) : null}
                <div className="flex-1 overflow-y-auto">
                  {loading && items.length === 0 ? (
                    <div
                      className="flex items-center gap-2 px-3 py-4 text-[11px]"
                      style={{ color: "var(--text-muted)" }}
                    >
                      <Loader2 size={11} className="animate-spin" /> Loading…
                    </div>
                  ) : null}
                  {!loading && items.length === 0 ? (
                    <div
                      className="px-3 py-4 text-[11px]"
                      style={{ color: "var(--text-muted)" }}
                    >
                      No artifacts yet.
                    </div>
                  ) : null}
                  <ul>
                    {items.map((a) => {
                      const active = a.id === selectedId;
                      return (
                        <li key={a.id}>
                          <button
                            type="button"
                            onClick={() => setSelectedId(a.id)}
                            className="w-full px-3 py-2 text-left flex flex-col gap-0.5"
                            style={{
                              background: active ? "var(--accent-brand-soft)" : "transparent",
                              borderBottom: "1px solid var(--border)",
                            }}
                          >
                            <span className="text-xs font-medium truncate">
                              {a.title || "Untitled"}
                            </span>
                            <span
                              className="text-[10px] uppercase tracking-widest"
                              style={{ color: "var(--text-muted)" }}
                            >
                              {TYPE_LABEL[a.artifact_type]}
                            </span>
                          </button>
                        </li>
                      );
                    })}
                  </ul>
                </div>
              </aside>

              {/* Right pane — editor */}
              <section className="flex-1 min-w-0 flex flex-col">
                {error ? (
                  <div
                    className="px-3 py-2 text-[11px] flex-shrink-0"
                    style={{ background: "var(--error-soft)", color: "var(--error)" }}
                  >
                    {error}
                  </div>
                ) : null}
                {creating || selected ? (
                  <>
                    <div className="p-4 flex-shrink-0 flex items-center gap-2">
                      <input
                        value={draftTitle}
                        onChange={(e) => setDraftTitle(e.target.value)}
                        placeholder="Title"
                        className="flex-1 bg-transparent text-sm font-semibold outline-none rounded-lg px-2 py-1.5"
                        style={{
                          color: "var(--text-primary)",
                          background: "var(--bg-surface)",
                          border: "1px solid var(--border)",
                        }}
                      />
                      {selected && canEdit ? (
                        <button
                          type="button"
                          onClick={handleDelete}
                          disabled={busy}
                          className="p-2 rounded-lg"
                          style={{ color: "var(--error)" }}
                          title="Delete artifact"
                        >
                          <Trash2 size={13} />
                        </button>
                      ) : null}
                    </div>
                    <textarea
                      value={draftContent}
                      onChange={canEdit ? (e) => setDraftContent(e.target.value) : undefined}
                      readOnly={!canEdit}
                      placeholder={canEdit ? "Write your note in markdown…" : "Read-only"}
                      className="flex-1 min-h-0 mx-4 mb-3 p-3 text-xs leading-relaxed resize-none outline-none rounded-lg"
                      style={{
                        background: "var(--bg-surface)",
                        color: "var(--text-primary)",
                        border: "1px solid var(--border)",
                        fontFamily:
                          "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace",
                      }}
                    />
                    <div
                      className="flex items-center justify-between px-4 py-3 flex-shrink-0"
                      style={{ borderTop: "1px solid var(--border)" }}
                    >
                      <span
                        className="text-[11px]"
                        style={{ color: "var(--text-muted)" }}
                      >
                        {selected?.updated_at
                          ? `Updated ${new Date(selected.updated_at).toLocaleString()}`
                          : creating
                            ? "Draft — not yet saved"
                            : ""}
                      </span>
                      {canEdit ? (
                        <div className="flex items-center gap-2">
                          <button
                            type="button"
                            onClick={() => {
                              setCreating(false);
                              setSelectedId(null);
                            }}
                            className="px-3 py-1.5 rounded-lg text-xs"
                            style={{ color: "var(--text-muted)" }}
                          >
                            Cancel
                          </button>
                          <motion.button
                            type="button"
                            onClick={() => void handleSave()}
                            disabled={busy}
                            whileTap={{ scale: 0.97 }}
                            className="px-3 py-1.5 rounded-lg text-xs font-medium"
                            style={{
                              background: busy ? "var(--bg-elevated)" : "var(--accent)",
                              color: busy ? "var(--text-muted)" : "var(--accent-fg)",
                            }}
                          >
                            {busy ? "Saving…" : creating ? "Create" : "Save"}
                          </motion.button>
                        </div>
                      ) : (
                        <span className="text-[11px]" style={{ color: "var(--text-muted)" }}>
                          Read-only
                        </span>
                      )}
                    </div>
                  </>
                ) : (
                  <div
                    className="flex-1 flex items-center justify-center text-xs text-center px-8"
                    style={{ color: "var(--text-muted)" }}
                  >
                    Select an artifact from the left, or create a new note to capture
                    knowledge alongside this workspace&rsquo;s indexed sources.
                  </div>
                )}
              </section>
            </div>
          </motion.div>
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}

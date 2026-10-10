"use client";

import React, { useEffect, useMemo, useState } from "react";
import { useOnChange } from "../lib/use-on-change";
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
import { Button, ConfirmDialog, EmptyState, ErrorBanner, Modal, TextField } from "./ui";

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


  // One key per load request: set while the panel is open, and replaced when
  // its inputs change (same triggers as before). The spinner/error reset is
  // applied during render; the request runs in the effect and only sets state
  // after it resolves.
  const loadRequest = useMemo(
    () => (open ? { auth, workspaceId, filterType } : null),
    [open, auth, workspaceId, filterType],
  );
  useOnChange(loadRequest, (request) => {
    if (request) {
      setLoading(true);
      setError(null);
    }
  });
  useEffect(() => {
    if (!loadRequest) return;
    const { auth, workspaceId, filterType } = loadRequest;
    const run = async () => {
      try {
        const list = await listArtifacts(auth, workspaceId, filterType);
        setItems(list);
        // If the previously selected artifact disappeared (deleted or filtered
        // out), drop the selection so the right pane shows the empty state.
        setSelectedId((current) => (current && !list.some((a) => a.id === current) ? null : current));
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load artifacts.");
      } finally {
        setLoading(false);
      }
    };
    void run();
  }, [loadRequest]);

  // Hydrate the editor when the user picks an item.
  const selected = useMemo(
    () => items.find((a) => a.id === selectedId) ?? null,
    [items, selectedId]
  );
  // Adjusted during render when the selected artifact (object identity)
  // changes, as the previous effect did, minus the extra stale render.
  useOnChange(selected, (next) => {
    if (next) {
      setDraftTitle(next.title);
      setDraftContent(next.content);
      setCreating(false);
    }
  });

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

  const [confirmDelete, setConfirmDelete] = useState(false);

  const handleDelete = async () => {
    if (!selected) return;
    setConfirmDelete(false);
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
    <Modal
      open={open}
      onClose={onClose}
      busy={busy}
      title="Workspace notes"
      width={960}
      height="min(680px, 88vh)"
      align="top"
    >
      <div className="flex flex-col h-full min-h-0">
        <header
          className="flex items-center justify-between gap-3 px-5 py-3.5 flex-shrink-0"
          style={{ borderBottom: "1px solid var(--border)" }}
        >
          <div className="flex items-baseline gap-2.5 min-w-0">
            <h2 className="display text-[15px] font-semibold truncate">Workspace notes</h2>
            <span
              className="text-[10px] uppercase tracking-widest truncate"
              style={{ color: "var(--text-muted)" }}
            >
              {workspaceName}
            </span>
          </div>
          <Button variant="ghost" size="sm" onClick={onClose} aria-label="Close notes panel">
            <X size={14} />
          </Button>
        </header>

        <div className="flex-1 min-h-0 flex">
          {/* Left rail — segmented type filter + artifact list */}
          <aside
            className="w-64 flex-shrink-0 flex flex-col"
            style={{ borderRight: "1px solid var(--border)" }}
          >
            <div className="p-2.5 flex-shrink-0">
              <div
                role="tablist"
                aria-label="Artifact type"
                className="flex flex-wrap gap-1 p-1 rounded-lg"
                style={{ background: "var(--bg-surface)", border: "1px solid var(--border)" }}
              >
                {TABS.map((tab) => {
                  const active = tab.key === activeTab;
                  return (
                    <button
                      key={tab.key}
                      type="button"
                      role="tab"
                      aria-selected={active}
                      onClick={() => setActiveTab(tab.key)}
                      className="px-2 py-1 rounded-sm text-[10px] font-medium transition-colors focus-ring"
                      style={{
                        background: active ? "var(--bg-elevated)" : "transparent",
                        color: active ? "var(--accent-primary)" : "var(--text-tertiary)",
                      }}
                    >
                      {tab.label}
                    </button>
                  );
                })}
              </div>
            </div>
            {canEdit ? (
              <div className="px-2.5 pb-2.5 flex-shrink-0">
                <Button variant="secondary" size="sm" className="w-full" onClick={startCreate}>
                  <Plus size={12} /> New note
                </Button>
              </div>
            ) : null}
            <div className="flex-1 min-h-0 overflow-y-auto">
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
                        className="w-full px-3 py-2 pl-2.5 text-left flex flex-col gap-0.5 transition-colors focus-ring"
                        style={{
                          background: active ? "var(--bg-surface)" : "transparent",
                          borderLeft: `2px solid ${
                            active ? "var(--accent-primary)" : "transparent"
                          }`,
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

          {/* Right pane — editor / read-only viewer */}
          <section className="flex-1 min-w-0 flex flex-col">
            {error ? (
              <div className="px-4 pt-3 flex-shrink-0">
                <ErrorBanner message={error} />
              </div>
            ) : null}
            {creating || selected ? (
              <>
                <div className="p-4 pb-3 flex-shrink-0">
                  <TextField
                    label="Title"
                    placeholder="Untitled"
                    aria-label="Note title"
                    value={draftTitle}
                    onChange={canEdit ? (e) => setDraftTitle(e.target.value) : undefined}
                    readOnly={!canEdit}
                  />
                </div>
                <textarea
                  value={draftContent}
                  onChange={canEdit ? (e) => setDraftContent(e.target.value) : undefined}
                  readOnly={!canEdit}
                  placeholder={canEdit ? "Write your note in markdown…" : "Read-only"}
                  aria-label="Note content"
                  className="flex-1 min-h-0 mx-4 mb-3 p-3 text-xs leading-relaxed resize-none outline-none focus-ring rounded-lg transition-colors"
                  style={{
                    background: "var(--bg-surface)",
                    color: "var(--text-primary)",
                    border: "1px solid var(--border)",
                    fontFamily: "var(--font-mono), monospace",
                  }}
                />
                <div
                  className="flex items-center justify-between gap-3 px-4 py-3 flex-shrink-0"
                  style={{ borderTop: "1px solid var(--border)" }}
                >
                  <span
                    className="text-[11px] truncate"
                    style={{ color: "var(--text-tertiary)" }}
                  >
                    {selected?.updated_at ? (
                      <>
                        Updated{" "}
                        <span className="data-num">
                          {new Date(selected.updated_at).toLocaleString()}
                        </span>
                      </>
                    ) : creating ? (
                      "Draft — not yet saved"
                    ) : (
                      ""
                    )}
                  </span>
                  {canEdit ? (
                    <div className="flex items-center gap-2 flex-shrink-0">
                      {selected ? (
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => setConfirmDelete(true)}
                          disabled={busy}
                          style={{ color: "var(--error)" }}
                          title="Delete artifact"
                          aria-label="Delete note"
                        >
                          <Trash2 size={12} /> Delete
                        </Button>
                      ) : null}
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => {
                          setCreating(false);
                          setSelectedId(null);
                        }}
                      >
                        Cancel
                      </Button>
                      <Button
                        variant="primary"
                        size="sm"
                        onClick={() => void handleSave()}
                        disabled={busy}
                      >
                        {busy ? "Saving…" : creating ? "Create" : "Save"}
                      </Button>
                    </div>
                  ) : (
                    <span
                      className="text-[11px] flex-shrink-0"
                      style={{ color: "var(--text-tertiary)" }}
                    >
                      Read-only
                    </span>
                  )}
                </div>
              </>
            ) : (
              <div className="flex-1 min-h-0 overflow-y-auto">
                <EmptyState
                  icon={<StickyNote size={16} />}
                  title="No artifact selected"
                  description="Select an artifact from the left, or create a new note to capture knowledge alongside this workspace's indexed sources."
                  action={
                    canEdit ? (
                      <Button variant="secondary" size="sm" onClick={startCreate}>
                        <Plus size={12} /> New note
                      </Button>
                    ) : undefined
                  }
                />
              </div>
            )}
          </section>
        </div>
      </div>
      <ConfirmDialog
        open={confirmDelete}
        title="Delete note"
        message={selected ? `Delete "${selected.title}"? This cannot be undone.` : "Delete this artifact?"}
        confirmLabel="Delete"
        danger
        busy={busy}
        onConfirm={handleDelete}
        onCancel={() => setConfirmDelete(false)}
      />
    </Modal>
  );
}

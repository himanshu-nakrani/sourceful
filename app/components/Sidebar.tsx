"use client";

import React, { useMemo, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  BarChart3,
  Download,
  FileText,
  Loader2,
  MessageSquare,
  Moon,
  Pencil,
  Plus,
  RefreshCcw,
  Search,
  Settings,
  StickyNote,
  Sun,
  Trash2,
  Upload,
  Users,
  PanelLeftClose,
  X,
} from "lucide-react";
import {
  deleteConversation,
  deleteDocument,
  exportConversation,
  renameConversation,
  reprocessDocument,
} from "../lib/api";
import type { ConversationListItem, DocumentInfo, JobStatus } from "../lib/api";
import { transitionFast, transitionNormal } from "../lib/motion";
import { useServerState } from "../lib/server-state";
import { useToast } from "./Toast";
import { SidebarDocSkeleton } from "./Skeleton";
import { useStore } from "../lib/store";
import {
  Button,
  ConfirmDialog,
  EmptyState,
  ErrorBanner,
  PromptDialog,
  StatusDot,
} from "./ui";
import type { StatusTone } from "./ui";
import WorkspaceSwitcher from "./WorkspaceSwitcher";
import WorkspaceNotesPanel from "./WorkspaceNotesPanel";
import WorkspaceMembersPanel from "./WorkspaceMembersPanel";
import WorkspaceSourcesPanel from "./WorkspaceSourcesPanel";
import WorkspaceAnalyticsPanel from "./WorkspaceAnalyticsPanel";

interface SidebarProps {
  onUploadClick: () => void;
}

/** Job status -> StatusDot tone (queued=warning, processing pulses). */
const STATUS_TONE: Record<JobStatus, StatusTone> = {
  ready: "success",
  processing: "processing",
  error: "error",
  queued: "warning",
};

const statusTone = (status: JobStatus): StatusTone => STATUS_TONE[status] ?? "idle";
const statusPulse = (status: JobStatus): boolean => status === "processing";

/**
 * Ghost icon button: quiet, tooltip-bearing control for secondary actions
 * (theme, settings, workspace tools, row actions).
 */
function GhostIconButton({
  label,
  onClick,
  children,
  stopPropagation = false,
  className = "",
}: {
  label: string;
  onClick: () => void;
  children: React.ReactNode;
  stopPropagation?: boolean;
  className?: string;
}) {
  return (
    <motion.button
      type="button"
      onClick={(event) => {
        if (stopPropagation) event.stopPropagation();
        onClick();
      }}
      aria-label={label}
      title={label}
      className={`inline-flex items-center justify-center rounded-md transition-colors focus-ring ${className}`}
      style={{ color: "var(--text-muted)", padding: 6 }}
      whileHover={{ color: "var(--text-secondary)", background: "var(--bg-surface)" }}
      whileTap={{ scale: 0.92 }}
      transition={transitionFast}
    >
      {children}
    </motion.button>
  );
}

/**
 * Render the app sidebar for document indexing and conversation management.
 *
 * Displays controls for upload, theme, and settings; a searchable list of documents;
 * multi-document selection and a "Chat" action for selected docs; per-document actions
 * (select, toggle selection, reprocess, delete); conversation management (new chat,
 * rename, delete, export); chunk previews for ready documents; and refresh/error loading states.
 *
 * @param onUploadClick - Callback invoked when the Upload button is clicked
 * @returns The sidebar element used for document navigation and conversation management
 */
const listItem = {
  hidden: { opacity: 0, x: -8 },
  show: { opacity: 1, x: 0, transition: transitionNormal },
};

export default function Sidebar({ onUploadClick }: SidebarProps) {
  const { state, dispatch } = useStore();
  const {
    documents,
    documentsLoading,
    documentsError,
    conversations,
    conversationsLoading,
    conversationsError,
    chunkPreview,
    chunkPreviewLoading,
    refreshDocuments,
    refreshConversations,
    refreshChunkPreview,
    selectConversation,
    selectDocument,
    setMessages,
  } = useServerState();
  const {
    settings,
    activeConversationId,
    activeDocumentId,
    activeDocumentIds,
    sidebarOpen,
    activeWorkspaceId,
  } = state;
  const [search, setSearch] = useState("");
  const [actionError, setActionError] = useState<string | null>(null);
  const [notesOpen, setNotesOpen] = useState(false);
  const [membersOpen, setMembersOpen] = useState(false);
  const [sourcesOpen, setSourcesOpen] = useState(false);
  const [analyticsOpen, setAnalyticsOpen] = useState(false);
  const [searchFocused, setSearchFocused] = useState(false);

  // Dialog state machines (replace window.prompt / window.confirm).
  const [renameOpen, setRenameOpen] = useState(false);
  const [renameBusy, setRenameBusy] = useState(false);
  const [deleteDocTarget, setDeleteDocTarget] = useState<DocumentInfo | null>(null);
  const [deleteDocBusy, setDeleteDocBusy] = useState(false);
  const [deleteConversationTarget, setDeleteConversationTarget] =
    useState<ConversationListItem | null>(null);
  const [deleteConversationBusy, setDeleteConversationBusy] = useState(false);

  // Fix 5.4: memoize the auth context so the workspace panels (which key
  // their fetch effects on this object) do not see a new identity every
  // render — that caused refetch storms while streaming updates re-rendered
  // the sidebar. Same pattern as ChatArea.
  const auth = useMemo(
    () => ({
      clientSessionId: settings.clientSessionId,
      providerApiKey: settings.providerApiKey,
    }),
    [settings.clientSessionId, settings.providerApiKey],
  );

  const visibleDocuments = useMemo(() => {
    const term = search.trim().toLowerCase();
    // Phase 1: scope the sidebar document list to the active workspace when one
    // is selected. Legacy documents without a workspace_id are kept visible so
    // existing flows keep working during migration.
    const scoped = activeWorkspaceId
      ? documents.filter(
          (document) =>
            !document.workspace_id || document.workspace_id === activeWorkspaceId
        )
      : documents;
    if (!term) return scoped;
    return scoped.filter((document) => document.filename.toLowerCase().includes(term));
  }, [documents, search, activeWorkspaceId]);

  const activeConversation = conversations.find(
    (conversation) => conversation.id === activeConversationId
  ) ?? null;

  const { toast } = useToast();

  const handleDeleteDocument = async (documentId: string) => {
    const doc = documents.find((d) => d.id === documentId);
    try {
      await deleteDocument(auth, documentId);
      if (activeDocumentId === documentId) {
        await selectDocument(null);
        setMessages([]);
      }
      await refreshDocuments();
      setActionError(null);
      toast({ variant: "success", title: "Document deleted", description: doc?.filename });
    } catch (error) {
      const msg = error instanceof Error ? error.message : "Unable to delete document.";
      setActionError(msg);
      toast({ variant: "error", title: "Delete failed", description: msg });
    }
  };

  const handleConfirmDeleteDocument = async () => {
    if (!deleteDocTarget) return;
    setDeleteDocBusy(true);
    try {
      await handleDeleteDocument(deleteDocTarget.id);
    } finally {
      setDeleteDocBusy(false);
      setDeleteDocTarget(null);
    }
  };

  const handleReprocess = async (documentId: string) => {
    if (!settings.providerApiKey.trim()) {
      const msg = "Add your provider API key in Settings before reprocessing.";
      setActionError(msg);
      toast({ variant: "warning", title: "API key required", description: msg });
      return;
    }
    const doc = documents.find((d) => d.id === documentId);
    try {
      await reprocessDocument(auth, documentId, settings.embeddingModel);
      await refreshDocuments();
      if (activeDocumentId === documentId) {
        await refreshChunkPreview(documentId);
      }
      setActionError(null);
      toast({ variant: "info", title: "Reprocessing queued", description: doc?.filename });
    } catch (error) {
      const msg = error instanceof Error ? error.message : "Unable to reprocess document.";
      setActionError(msg);
      toast({ variant: "error", title: "Reprocess failed", description: msg });
    }
  };

  const handleDeleteConversation = async (conversationId: string) => {
    try {
      await deleteConversation(auth, conversationId);
      if (activeConversationId === conversationId) {
        await selectConversation(null);
      }
      await refreshConversations(activeDocumentId);
      setActionError(null);
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "Unable to delete conversation.");
    }
  };

  const handleConfirmDeleteConversation = async () => {
    if (!deleteConversationTarget) return;
    setDeleteConversationBusy(true);
    try {
      await handleDeleteConversation(deleteConversationTarget.id);
    } finally {
      setDeleteConversationBusy(false);
      setDeleteConversationTarget(null);
    }
  };

  const handleRenameSubmit = async (nextTitle: string) => {
    if (!activeConversation) return;
    setRenameBusy(true);
    try {
      await renameConversation(auth, activeConversation.id, nextTitle);
      await refreshConversations(activeDocumentId);
      setActionError(null);
      setRenameOpen(false);
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "Unable to rename conversation.");
    } finally {
      setRenameBusy(false);
    }
  };

  const handleExportConversation = async (format: "markdown" | "json") => {
    if (!activeConversation) return;
    try {
      const blob = await exportConversation(auth, activeConversation.id, format);
      const downloadUrl = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = downloadUrl;
      anchor.download = `${activeConversation.title.replace(/[^a-z0-9-_]+/gi, "-") || "conversation"}.${format === "json" ? "json" : "md"}`;
      anchor.click();
      URL.revokeObjectURL(downloadUrl);
      setActionError(null);
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "Unable to export conversation.");
    }
  };

  const activeWorkspace = state.workspaces.find((w) => w.id === activeWorkspaceId) ?? null;
  const multiSelectCount = activeDocumentIds.length;

  return (
    <>
    <aside
      style={{ width: "var(--sidebar-width)" }}
      className={`absolute md:relative z-40 flex flex-col h-full transition-transform duration-300 ease-[cubic-bezier(0.22,1,0.36,1)] flex-shrink-0 ${
        sidebarOpen ? "translate-x-0" : "-translate-x-full md:hidden"
      }`}
      role="navigation"
      aria-label="Sidebar"
    >
      {/* Sidebar surface: flat graphite, hairline right edge */}
      <div
        className="absolute inset-0 pointer-events-none"
        style={{
          background: "var(--bg-secondary)",
          borderRight: "1px solid var(--border)",
        }}
      />

      {/* Header */}
      <div
        className="relative flex items-center justify-between px-4 flex-shrink-0"
        style={{ height: "var(--header-height)" }}
      >
        <div className="flex items-center gap-2.5">
          <div
            className="flex items-center justify-center"
            style={{
              width: 28,
              height: 28,
              borderRadius: "var(--radius-md)",
              background: "var(--bg-surface)",
              border: "1px solid var(--border)",
            }}
          >
            <FileText size={14} style={{ color: "var(--accent-primary)" }} />
          </div>
          <span
            className="display text-sm font-bold"
            style={{ color: "var(--text-primary)", letterSpacing: "-0.02em" }}
          >
            Sourceful
          </span>
        </div>
        <GhostIconButton
          label="Toggle sidebar"
          onClick={() => dispatch({ type: "TOGGLE_SIDEBAR" })}
        >
          <PanelLeftClose size={15} />
        </GhostIconButton>
      </div>

      {/* Workspace switcher (Phase 1) */}
      <WorkspaceSwitcher />

      {/* Phase 2/3 — workspace tools (notes + members) as ghost icon buttons */}
      {activeWorkspaceId ? (
        <div className="relative px-3 pb-1 flex-shrink-0 flex items-center gap-0.5">
          <GhostIconButton
            label="Workspace sources & sync state"
            onClick={() => setSourcesOpen(true)}
          >
            <FileText size={13} />
          </GhostIconButton>
          <GhostIconButton
            label="Workspace notes & saved answers"
            onClick={() => setNotesOpen(true)}
          >
            <StickyNote size={13} />
          </GhostIconButton>
          <GhostIconButton
            label="Members & invitations"
            onClick={() => setMembersOpen(true)}
          >
            <Users size={13} />
          </GhostIconButton>
          <GhostIconButton
            label="Workspace overview"
            onClick={() => setAnalyticsOpen(true)}
          >
            <BarChart3 size={13} />
          </GhostIconButton>
        </div>
      ) : null}

      {/* Primary action — the single lime accent in the shell */}
      <div className="relative px-3 pt-2 pb-1.5 flex-shrink-0">
        <Button variant="primary" size="md" className="w-full" onClick={onUploadClick}>
          <Upload size={13} />
          Upload Document
        </Button>
      </div>

      {/* Maintenance actions — quiet ghost row */}
      <div className="relative px-3 pb-2 flex items-center gap-0.5 flex-shrink-0">
        <GhostIconButton
          label={settings.theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
          onClick={() =>
            dispatch({
              type: "SET_SETTINGS",
              payload: { theme: settings.theme === "dark" ? "light" : "dark" },
            })
          }
        >
          {settings.theme === "dark" ? <Sun size={13} /> : <Moon size={13} />}
        </GhostIconButton>
        <GhostIconButton label="Open settings" onClick={() => dispatch({ type: "TOGGLE_SETTINGS" })}>
          <Settings size={13} />
        </GhostIconButton>
        <div className="flex-1" />
        <span
          className="text-[10px]"
          style={{ color: "var(--text-muted)" }}
          title="Keyboard shortcut for upload"
        >
          ⌘U upload
        </span>
      </div>

      {/* Search */}
      <div className="relative px-3 pb-2 flex-shrink-0">
        <div
          className="flex items-center gap-2 px-2.5 py-1.5 transition-colors relative"
          style={{
            background: "var(--bg-surface)",
            border: `1px solid ${searchFocused ? "var(--border-strong)" : "var(--border)"}`,
            borderRadius: "var(--radius-lg)",
            boxShadow: searchFocused ? "0 0 0 2px var(--accent-primary-soft)" : "none",
          }}
        >
          <Search size={12} style={{ color: "var(--text-muted)", flexShrink: 0 }} />
          {/* [a11y] Added aria-label — input has no associated label element */}
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            onFocus={() => setSearchFocused(true)}
            onBlur={() => setSearchFocused(false)}
            placeholder="Search documents"
            aria-label="Search documents"
            className="w-full bg-transparent text-xs outline-none min-w-0"
            style={{ color: "var(--text-primary)", paddingRight: search ? "24px" : "0" }}
          />
          <AnimatePresence>
            {search ? (
              <motion.div
                initial={{ opacity: 0, scale: 0.8 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.8 }}
                transition={transitionFast}
                className="absolute right-1.5 top-1/2 -translate-y-1/2 flex items-center"
              >
                <GhostIconButton
                  label="Clear search"
                  onClick={() => setSearch("")}
                >
                  <X size={12} />
                </GhostIconButton>
              </motion.div>
            ) : null}
          </AnimatePresence>
        </div>
      </div>

      {/* Document list */}
      <div className="relative flex-1 overflow-y-auto px-2 pb-3">
        {/* Section header — eyebrow label + mono count + hairline divider */}
        <div className="px-2 pt-1.5 pb-1.5 flex items-center justify-between">
          <div className="flex items-baseline gap-1.5">
            <span
              className="text-[10px] font-medium uppercase tracking-widest"
              style={{ color: "var(--text-tertiary)" }}
            >
              Documents
            </span>
            <span className="data-num text-[10px]" style={{ color: "var(--accent-secondary)" }}>
              {visibleDocuments.length}
            </span>
          </div>
          <div className="flex items-center gap-1.5">
            {(documentsLoading || conversationsLoading) && (
              <Loader2
                size={10}
                className="animate-spin"
                style={{ color: "var(--text-muted)" }}
              />
            )}
            <GhostIconButton label="Refresh documents" onClick={() => void refreshDocuments()}>
              <RefreshCcw size={10} />
            </GhostIconButton>
          </div>
        </div>
        <div className="mx-2 mb-2" style={{ borderTop: "1px solid var(--border)" }} />

        <AnimatePresence>
          {documentsError ? (
            <motion.div
              key="documents-error"
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              exit={{ opacity: 0, height: 0 }}
              transition={transitionFast}
              className="mx-1 mb-3 overflow-hidden"
            >
              <ErrorBanner
                message={documentsError}
                onRetry={() => void refreshDocuments()}
              />
            </motion.div>
          ) : null}
          {actionError ? (
            <motion.div
              key="action-error"
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              exit={{ opacity: 0, height: 0 }}
              transition={transitionFast}
              className="mx-1 mb-3 overflow-hidden"
            >
              <ErrorBanner message={actionError} onDismiss={() => setActionError(null)} />
            </motion.div>
          ) : null}
        </AnimatePresence>

        {visibleDocuments.length === 0 && documentsLoading ? (
          <div className="flex flex-col gap-1 px-1">
            <SidebarDocSkeleton />
            <SidebarDocSkeleton />
            <SidebarDocSkeleton />
          </div>
        ) : null}

        {visibleDocuments.length === 0 && !documentsLoading ? (
          <EmptyState
            icon={<FileText size={16} />}
            title={search ? "No matching documents" : "No indexed documents yet"}
            description={
              search
                ? "Try a different search term."
                : "Upload a document to start grounding chat in your sources."
            }
            action={
              search ? (
                <Button variant="secondary" size="sm" onClick={() => setSearch("")}>
                  Clear search
                </Button>
              ) : undefined
            }
          />
        ) : null}

        {visibleDocuments.map((document, index) => {
          const isActive = activeDocumentId === document.id;
          const isSelected = activeDocumentIds.includes(document.id);
          return (
            <motion.div
              key={document.id}
              className="mb-0.5"
              variants={listItem}
              initial="hidden"
              animate="show"
              transition={{ ...transitionNormal, delay: Math.min(index * 0.03, 0.2) }}
            >
              {/* [a11y] Use a keyboard-focusable container so row actions can stay real buttons */}
              <motion.div
                role="button"
                tabIndex={0}
                className={`group relative cursor-pointer w-full text-left overflow-hidden px-2.5 py-2 ${
                  isActive ? "sidebar-item-active" : ""
                }`}
                style={{
                  background: isActive
                    ? "var(--bg-surface)"
                    : isSelected
                      ? "var(--accent-primary-soft)"
                      : "transparent",
                  border: `1px solid ${isActive ? "var(--border)" : "transparent"}`,
                  borderRadius: "var(--radius-md)",
                }}
                whileHover={{
                  background: isActive
                    ? "var(--bg-surface)"
                    : isSelected
                      ? "var(--accent-primary-soft)"
                      : "var(--bg-surface)",
                }}
                transition={transitionFast}
                onClick={(e) => {
                  if (e.shiftKey || e.ctrlKey || e.metaKey) {
                    dispatch({ type: "TOGGLE_DOCUMENT_SELECTION", payload: document.id });
                  } else {
                    void selectDocument(document.id);
                  }
                }}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    void selectDocument(document.id);
                  }
                }}
              >
                <div className="flex items-start gap-2.5">
                  {multiSelectCount > 1 || isSelected ? (
                    <input
                      type="checkbox"
                      checked={isSelected}
                      onChange={() => dispatch({ type: "TOGGLE_DOCUMENT_SELECTION", payload: document.id })}
                      onClick={(e) => e.stopPropagation()}
                      className="mt-1 flex-shrink-0 cursor-pointer"
                      aria-label={`Select ${document.filename}`}
                    />
                  ) : (
                    <span className="mt-1.5 flex-shrink-0">
                      <StatusDot
                        tone={statusTone(document.status)}
                        pulse={statusPulse(document.status)}
                      />
                    </span>
                  )}
                  <div className="flex-1 min-w-0">
                    <p
                      className="text-[13px] font-medium truncate"
                      style={{ color: "var(--text-primary)" }}
                    >
                      {document.filename}
                    </p>
                    {/* Single inline text run: wrapping flex items here used to
                        orphan "·" separators at line breaks in the narrow
                        sidebar. Truncation guards the widest case instead. */}
                    <p
                      className="text-[11px] mt-0.5 truncate"
                      style={{ color: "var(--text-muted)" }}
                    >
                      {document.current_stage && document.status !== "ready"
                        ? `${document.status} · ${document.current_stage}`
                        : document.status}{" "}
                      · <span className="data-num">{document.chunk_count}</span> chunks
                      {document.page_count ? (
                        <>
                          {" "}
                          · <span className="data-num">{document.page_count}</span> pages
                        </>
                      ) : null}
                    </p>
                    {document.last_error ? (
                      <p
                        className="text-[11px] mt-0.5 line-clamp-2"
                        style={{ color: "var(--error)" }}
                      >
                        {document.last_error}
                      </p>
                    ) : null}
                  </div>
                  {/* [a11y] Hover/focus-within reveal keeps row actions keyboard-reachable */}
                  <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 group-focus-within:opacity-100 transition-opacity">
                    {document.status === "error" || document.status === "ready" ? (
                      <GhostIconButton
                        label="Reprocess document"
                        stopPropagation
                        onClick={() => void handleReprocess(document.id)}
                      >
                        <RefreshCcw size={12} />
                      </GhostIconButton>
                    ) : null}
                    {/* [flow] Destructive delete routes through a confirm dialog */}
                    <GhostIconButton
                      label="Delete document"
                      stopPropagation
                      onClick={() => setDeleteDocTarget(document)}
                    >
                      <Trash2 size={12} />
                    </GhostIconButton>
                  </div>
                </div>
              </motion.div>

              <AnimatePresence>
                {isActive ? (
                  <motion.div
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: "auto" }}
                    exit={{ opacity: 0, height: 0 }}
                    transition={transitionNormal}
                    className="ml-5 mt-1 pl-3 overflow-hidden"
                    style={{ borderLeft: "1px solid var(--border)" }}
                  >
                    <div className="flex items-center gap-1 mb-1.5">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => void selectConversation(null)}
                      >
                        <Plus size={11} />
                        New Chat
                      </Button>
                      {/* silent-failure fix: surface conversation load errors */}
                      {conversationsError ? (
                        <span
                          className="text-[10px] truncate"
                          style={{ color: "var(--error)" }}
                          title={conversationsError}
                          role="alert"
                        >
                          couldn&apos;t load chats
                        </span>
                      ) : null}
                      {activeConversation ? (
                        <>
                          <GhostIconButton
                            label="Rename conversation"
                            onClick={() => setRenameOpen(true)}
                          >
                            <Pencil size={11} />
                          </GhostIconButton>
                          <GhostIconButton
                            label="Export conversation"
                            onClick={() => void handleExportConversation("markdown")}
                          >
                            <Download size={11} />
                          </GhostIconButton>
                        </>
                      ) : null}
                    </div>

                    {conversations.map((conversation) => (
                      <motion.div
                        key={conversation.id}
                        className="group flex items-center gap-2 px-2 py-1.5 w-full"
                        style={{
                          background:
                            activeConversationId === conversation.id
                              ? "var(--bg-surface)"
                              : "transparent",
                          borderRadius: "var(--radius-sm)",
                        }}
                        whileHover={{ background: "var(--bg-surface)" }}
                        transition={transitionFast}
                      >
                        <button
                          type="button"
                          className="flex items-center gap-2 flex-1 min-w-0 text-left"
                          onClick={() => void selectConversation(conversation.id)}
                        >
                          <MessageSquare
                            size={10}
                            style={{ color: "var(--text-muted)", flexShrink: 0 }}
                          />
                          <span
                            className="text-[11px] truncate flex-1"
                            style={{
                              color:
                                activeConversationId === conversation.id
                                  ? "var(--text-primary)"
                                  : "var(--text-secondary)",
                            }}
                          >
                            {conversation.title}
                          </span>
                        </button>
                        <button
                          type="button"
                          onClick={() => setDeleteConversationTarget(conversation)}
                          className="opacity-0 group-hover:opacity-100 group-focus-within:opacity-100 p-1 rounded-xs transition-opacity"
                          style={{ color: "var(--text-muted)" }}
                          aria-label="Delete conversation"
                          title="Delete conversation"
                        >
                          <Trash2 size={9} />
                        </button>
                      </motion.div>
                    ))}

                    {document.status === "ready" ? (
                      <div className="mt-3">
                        <div className="flex items-center justify-between mb-1.5">
                          <span
                            className="text-[10px] uppercase tracking-widest"
                            style={{ color: "var(--text-tertiary)" }}
                          >
                            Chunk Preview
                          </span>
                          {chunkPreviewLoading ? (
                            <Loader2
                              size={10}
                              className="animate-spin"
                              style={{ color: "var(--text-muted)" }}
                            />
                          ) : null}
                        </div>
                        {chunkPreview.slice(0, 4).map((chunk) => (
                          <div
                            key={chunk.chunk_id}
                            className="px-2.5 py-1.5 mb-1.5"
                            style={{
                              background: "var(--bg-surface)",
                              border: "1px solid var(--border)",
                              borderRadius: "var(--radius-md)",
                            }}
                          >
                            <div
                              className="flex items-center gap-2 text-[10px] mb-1"
                              style={{ color: "var(--text-muted)" }}
                            >
                              <span>
                                Chunk <span className="data-num">{chunk.chunk_index + 1}</span>
                              </span>
                              {chunk.page_number ? (
                                <span>
                                  p.<span className="data-num">{chunk.page_number}</span>
                                </span>
                              ) : null}
                            </div>
                            <p
                              className="text-[11px] line-clamp-3 leading-relaxed"
                              style={{ color: "var(--text-tertiary)" }}
                            >
                              {chunk.content}
                            </p>
                          </div>
                        ))}
                      </div>
                    ) : null}
                  </motion.div>
                ) : null}
              </AnimatePresence>
            </motion.div>
          );
        })}
      </div>

      {/* Multi-select bar — bottom-fixed strip, hairline top edge */}
      <AnimatePresence>
        {multiSelectCount > 1 ? (
          <motion.div
            key="multi-select-bar"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 8 }}
            transition={transitionFast}
            className="relative flex-shrink-0 flex items-center justify-between gap-2 px-3 py-2"
            style={{ borderTop: "1px solid var(--border)", background: "var(--bg-secondary)" }}
          >
            <span className="text-xs" style={{ color: "var(--text-secondary)" }}>
              <span className="data-num" style={{ color: "var(--accent-secondary)" }}>
                {multiSelectCount}
              </span>{" "}
              docs selected
            </span>
            <Button
              variant="primary"
              size="sm"
              onClick={() => {
                dispatch({ type: "SET_ACTIVE_DOCUMENT_IDS", payload: activeDocumentIds });
                void selectConversation(null);
              }}
            >
              Chat with <span className="data-num">{multiSelectCount}</span>
            </Button>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </aside>

    {/* Dialogs — replace window.prompt / window.confirm */}
    <PromptDialog
      open={renameOpen}
      title="Rename conversation"
      label="Conversation title"
      initialValue={activeConversation?.title ?? ""}
      placeholder="Conversation title"
      submitLabel="Rename"
      busy={renameBusy}
      onSubmit={(value) => void handleRenameSubmit(value)}
      onCancel={() => setRenameOpen(false)}
    />
    <ConfirmDialog
      open={deleteDocTarget !== null}
      title="Delete document"
      message={
        deleteDocTarget
          ? `Delete "${deleteDocTarget.filename}"? This cannot be undone.`
          : ""
      }
      confirmLabel="Delete"
      cancelLabel="Cancel"
      danger
      busy={deleteDocBusy}
      onConfirm={() => void handleConfirmDeleteDocument()}
      onCancel={() => setDeleteDocTarget(null)}
    />
    <ConfirmDialog
      open={deleteConversationTarget !== null}
      title="Delete conversation"
      message={
        deleteConversationTarget
          ? `Delete conversation "${deleteConversationTarget.title}"?`
          : ""
      }
      confirmLabel="Delete"
      cancelLabel="Cancel"
      danger
      busy={deleteConversationBusy}
      onConfirm={() => void handleConfirmDeleteConversation()}
      onCancel={() => setDeleteConversationTarget(null)}
    />

    {activeWorkspaceId && activeWorkspace ? (
      <>
        <WorkspaceSourcesPanel
          open={sourcesOpen}
          onClose={() => setSourcesOpen(false)}
          workspaceId={activeWorkspaceId}
          workspaceName={activeWorkspace.name}
          auth={auth}
        />
        <WorkspaceNotesPanel
          open={notesOpen}
          onClose={() => setNotesOpen(false)}
          workspaceId={activeWorkspaceId}
          workspaceName={activeWorkspace.name}
          auth={auth}
        />
        <WorkspaceMembersPanel
          open={membersOpen}
          onClose={() => setMembersOpen(false)}
          workspaceId={activeWorkspaceId}
          workspaceName={activeWorkspace.name}
          auth={auth}
        />
        <WorkspaceAnalyticsPanel
          open={analyticsOpen}
          onClose={() => setAnalyticsOpen(false)}
          workspaceId={activeWorkspaceId}
          workspaceName={activeWorkspace.name}
          auth={auth}
        />
      </>
    ) : null}
    </>
  );
}

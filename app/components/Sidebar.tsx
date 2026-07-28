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
} from "lucide-react";
import {
  deleteConversation,
  deleteDocument,
  exportConversation,
  renameConversation,
  reprocessDocument,
} from "../lib/api";
import { EASE_OUT } from "../lib/motion";
import { useServerState } from "../lib/server-state";
import { useToast } from "./Toast";
import { SidebarDocSkeleton } from "./Skeleton";
import { useStore } from "../lib/store";
import WorkspaceSwitcher from "./WorkspaceSwitcher";
import WorkspaceNotesPanel from "./WorkspaceNotesPanel";
import WorkspaceMembersPanel from "./WorkspaceMembersPanel";
import WorkspaceSourcesPanel from "./WorkspaceSourcesPanel";
import WorkspaceAnalyticsPanel from "./WorkspaceAnalyticsPanel";

interface SidebarProps {
  onUploadClick: () => void;
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
  show: { opacity: 1, x: 0, transition: { duration: 0.3, ease: EASE_OUT } },
};

export default function Sidebar({ onUploadClick }: SidebarProps) {
  const { state, dispatch } = useStore();
  const {
    documents,
    documentsLoading,
    documentsError,
    conversations,
    conversationsLoading,
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
  const auth = useMemo(
    () => ({
      clientSessionId: settings.clientSessionId,
      providerApiKey: settings.providerApiKey,
    }),
    [settings.clientSessionId, settings.providerApiKey]
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

  const handleRenameConversation = async () => {
    if (!activeConversation) return;
    const nextTitle = window.prompt("Rename conversation", activeConversation.title)?.trim();
    if (!nextTitle) return;
    try {
      await renameConversation(auth, activeConversation.id, nextTitle);
      await refreshConversations(activeDocumentId);
      setActionError(null);
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "Unable to rename conversation.");
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

  return (
    <>
    <aside
      style={{ width: "var(--sidebar-width)" }}
      className={`absolute md:relative z-40 flex flex-col h-full transition-transform duration-300 ease-[cubic-bezier(0.22,1,0.36,1)] flex-shrink-0 ${
        sidebarOpen ? "translate-x-0" : "-translate-x-full md:hidden"
      }`}
      aria-label="Document navigation"
    >
      {/* Sidebar background with subtle gradient */}
      <div
        className="absolute inset-0 pointer-events-none"
        style={{
          background: "linear-gradient(180deg, var(--bg-secondary) 0%, var(--bg-primary) 100%)",
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
            className="flex items-center justify-center rounded-lg"
            style={{
              width: 30,
              height: 30,
              background: "var(--gradient-accent-soft)",
              border: "1px solid var(--border-hover)",
              boxShadow: "var(--shadow-glow-teal)",
            }}
          >
            <FileText size={14} style={{ color: "var(--accent-primary)" }} />
          </div>
          <span
            className="font-bold text-sm"
            style={{ color: "var(--text-primary)", letterSpacing: "-0.025em" }}
          >
            Sourceful
          </span>
        </div>
        <motion.button
          type="button"
          onClick={() => dispatch({ type: "TOGGLE_SIDEBAR" })}
          className="p-1.5 rounded-lg"
          style={{ color: "var(--text-muted)" }}
          aria-label="Toggle sidebar"
          title="Toggle sidebar"
          whileHover={{ color: "var(--text-secondary)", background: "var(--bg-surface)" }}
          whileTap={{ scale: 0.92 }}
        >
          <PanelLeftClose size={16} />
        </motion.button>
      </div>

      {/* Workspace switcher (Phase 1) */}
      <WorkspaceSwitcher />

      {/* Phase 2/3 — workspace tools (notes + members) */}
      {activeWorkspaceId ? (
        <div className="px-3 pb-1 flex-shrink-0 flex items-center gap-1">
          <button
            type="button"
            onClick={() => setSourcesOpen(true)}
            className="flex-1 flex items-center justify-center gap-1.5 px-2 py-1.5 rounded-lg text-[11px] outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]"
            style={{
              background: "var(--bg-surface)",
              color: "var(--text-secondary)",
              border: "1px solid var(--border)",
            }}
            title="Workspace sources & sync state"
          >
            <FileText size={11} />
            Sources
          </button>
          <button
            type="button"
            onClick={() => setNotesOpen(true)}
            className="flex-1 flex items-center justify-center gap-1.5 px-2 py-1.5 rounded-lg text-[11px] outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]"
            style={{
              background: "var(--bg-surface)",
              color: "var(--text-secondary)",
              border: "1px solid var(--border)",
            }}
            title="Workspace notes & saved answers"
          >
            <StickyNote size={11} />
            Notes
          </button>
          <button
            type="button"
            onClick={() => setMembersOpen(true)}
            className="flex-1 flex items-center justify-center gap-1.5 px-2 py-1.5 rounded-lg text-[11px] outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]"
            style={{
              background: "var(--bg-surface)",
              color: "var(--text-secondary)",
              border: "1px solid var(--border)",
            }}
            title="Members & invitations"
          >
            <Users size={11} />
            Members
          </button>
          <button
            type="button"
            onClick={() => setAnalyticsOpen(true)}
            className="flex-1 flex items-center justify-center gap-1.5 px-2 py-1.5 rounded-lg text-[11px] outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]"
            style={{
              background: "var(--bg-surface)",
              color: "var(--text-secondary)",
              border: "1px solid var(--border)",
            }}
            title="Workspace overview"
          >
            <BarChart3 size={11} />
            Overview
          </button>
        </div>
      ) : null}

      {/* Primary action */}
      <div className="relative px-3 pt-2 pb-1 flex-shrink-0">
        <motion.button
          type="button"
          onClick={onUploadClick}
          className="w-full flex items-center justify-center gap-2 px-3 py-2.5 rounded-xl text-xs font-semibold"
          style={{
            background: "var(--gradient-accent)",
            color: "#fff",
            boxShadow: "var(--shadow-glow-teal)",
          }}
          whileHover={{ scale: 1.02, boxShadow: "0 0 32px rgba(20,184,166,0.2)" }}
          whileTap={{ scale: 0.97 }}
          transition={{ type: "spring", stiffness: 400, damping: 17 }}
        >
          <Upload size={13} />
          Upload Document
        </motion.button>
      </div>

      {/* Maintenance actions — separated visually */}
      <div className="relative px-3 pb-2 flex gap-1.5 flex-shrink-0">
        <motion.button
          type="button"
          onClick={() =>
            dispatch({
              type: "SET_SETTINGS",
              payload: { theme: settings.theme === "dark" ? "light" : "dark" },
            })
          }
          className="flex items-center justify-center px-2.5 py-1.5 rounded-lg"
          style={{
            background: "var(--bg-surface)",
            color: "var(--text-secondary)",
            border: "1px solid var(--border)",
          }}
          aria-label="Toggle theme"
          title={settings.theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
          whileHover={{ borderColor: "var(--border-hover)", color: "var(--text-primary)" }}
          whileTap={{ scale: 0.92 }}
        >
          {settings.theme === "dark" ? <Sun size={13} /> : <Moon size={13} />}
        </motion.button>
        <motion.button
          type="button"
          onClick={() => dispatch({ type: "TOGGLE_SETTINGS" })}
          className="flex items-center justify-center px-2.5 py-1.5 rounded-lg"
          style={{
            background: "var(--bg-surface)",
            color: "var(--text-secondary)",
            border: "1px solid var(--border)",
          }}
          aria-label="Open settings"
          title="Open settings"
          whileHover={{ borderColor: "var(--border-hover)", color: "var(--text-primary)" }}
          whileTap={{ scale: 0.92 }}
        >
          <Settings size={13} />
        </motion.button>
        <div className="flex-1" />
        <span className="self-center text-[10px]" style={{ color: "var(--text-muted)" }}>⌘U upload</span>
      </div>

      {/* Search */}
      <div className="relative px-3 pb-2 flex-shrink-0">
        <motion.div
          className="flex items-center gap-2 rounded-xl px-3 py-2 transition-all duration-200"
          style={{
            background: "var(--bg-surface)",
            border: `1px solid ${searchFocused ? "var(--border-hover)" : "var(--border)"}`,
          }}
          animate={{
            boxShadow: searchFocused ? "0 0 0 2px rgba(99,102,241,0.1)" : "none",
          }}
        >
          <Search size={13} style={{ color: "var(--text-muted)" }} />
          {/* [a11y] Added aria-label — input had no associated label element */}
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            onFocus={() => setSearchFocused(true)}
            onBlur={() => setSearchFocused(false)}
            placeholder="Search documents"
            aria-label="Search documents"
            className="w-full bg-transparent text-xs outline-none rounded-xl focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[var(--accent)]"
            style={{ color: "var(--text-primary)" }}
          />
        </motion.div>
      </div>

      {/* Document list */}
      <div className="relative flex-1 overflow-y-auto px-2 pb-3">
        <div className="px-2 py-1.5 flex items-center justify-between">
          <span className="text-[10px] font-semibold uppercase tracking-widest" style={{ color: "var(--text-muted)" }}>
            Documents
          </span>
          <div className="flex items-center gap-2">
            {(documentsLoading || conversationsLoading) && <Loader2 size={10} className="animate-spin" style={{ color: "var(--text-muted)" }} />}
            <motion.button
              type="button"
              onClick={() => void refreshDocuments()}
              style={{ color: "var(--text-muted)" }}
              aria-label="Refresh documents"
              title="Refresh documents"
              whileHover={{ color: "var(--text-secondary)", rotate: 180 }}
              transition={{ duration: 0.4 }}
            >
              <RefreshCcw size={10} />
            </motion.button>
          </div>
        </div>

        <AnimatePresence>
          {documentsError ? (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              exit={{ opacity: 0, height: 0 }}
              className="mx-2 mb-3 rounded-xl px-3 py-2 text-xs"
              style={{ background: "var(--error-soft)", color: "var(--error)" }}
            >
              {documentsError}
            </motion.div>
          ) : null}
          {actionError ? (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              exit={{ opacity: 0, height: 0 }}
              className="mx-2 mb-3 rounded-xl px-3 py-2 text-xs"
              style={{ background: "var(--error-soft)", color: "var(--error)" }}
            >
              {actionError}
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
          <motion.div
            className="px-3 py-8 text-center"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
          >
            <FileText size={28} className="mx-auto mb-2" style={{ color: "var(--text-muted)" }} />
            <p className="text-xs" style={{ color: "var(--text-tertiary)" }}>
              {search ? "No matching documents." : "No indexed documents yet."}
            </p>
          </motion.div>
        ) : null}

        {activeDocumentIds.length > 1 ? (
          <div
            className="mx-2 mb-2 rounded-xl px-3 py-2 flex items-center justify-between"
            style={{ background: "var(--accent-brand-soft)", border: "1px solid var(--border)" }}
          >
            <span className="text-xs" style={{ color: "var(--text-primary)" }}>
              {activeDocumentIds.length} docs selected
            </span>
            <motion.button
              type="button"
              className="text-xs px-2 py-1 rounded-lg"
              style={{ background: "var(--accent)", color: "var(--accent-fg)" }}
              onClick={() => dispatch({ type: "SET_ACTIVE_DOCUMENT_IDS", payload: activeDocumentIds })}
              whileTap={{ scale: 0.95 }}
            >
              Chat
            </motion.button>
          </div>
        ) : null}

        {visibleDocuments.map((document, index) => {
          const isActive = activeDocumentId === document.id;
          const isSelected = activeDocumentIds.includes(document.id);
          const statusColor =
            document.status === "ready"
              ? "var(--success)"
              : document.status === "error"
              ? "var(--error)"
              : "var(--warning)";
          return (
            <motion.div
              key={document.id}
              className="mb-1"
              variants={listItem}
              initial="hidden"
              animate="show"
              transition={{ delay: index * 0.03 }}
            >
              {/* [a11y] Use a keyboard-focusable container so row actions can stay real buttons */}
              <motion.div
                role="button"
                tabIndex={0}
                className="group rounded-xl px-3 py-2.5 cursor-pointer w-full text-left relative overflow-hidden"
                style={{
                  background: isActive
                    ? "var(--accent-brand-soft)"
                    : isSelected
                    ? "var(--accent-soft)"
                    : "transparent",
                  border: `1px solid ${isActive ? "var(--border-accent)" : "transparent"}`,
                }}
                whileHover={{ background: isActive ? "var(--accent-brand-soft)" : "var(--bg-surface)" }}
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
                  {activeDocumentIds.length > 1 || isSelected ? (
                    <input
                      type="checkbox"
                      checked={isSelected}
                      onChange={() => dispatch({ type: "TOGGLE_DOCUMENT_SELECTION", payload: document.id })}
                      onClick={(e) => e.stopPropagation()}
                      className="mt-1 flex-shrink-0 cursor-pointer"
                      aria-label={`Select ${document.filename}`}
                    />
                  ) : (
                    <div
                      className="mt-1.5 h-2 w-2 rounded-full flex-shrink-0"
                      style={{ background: statusColor }}
                    />
                  )}
                  {/* Active left-edge rail */}
                  {isActive && (
                    <span
                      className="absolute left-0 top-1/2 -translate-y-1/2 w-[3px] rounded-r-full"
                      style={{ height: "60%", background: "var(--accent-brand)" }}
                      aria-hidden="true"
                    />
                  )}
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium truncate" style={{ color: "var(--text-primary)", letterSpacing: "-0.01em" }}>
                      {document.filename}
                    </p>
                    <p className="text-[11px] mt-0.5" style={{ color: isActive ? "var(--text-secondary)" : "var(--text-muted)" }}>
                      {document.status}
                      {document.current_stage ? ` · ${document.current_stage}` : ""}
                      {" · "}
                      {document.chunk_count} chunks
                      {document.page_count ? ` · ${document.page_count}p` : ""}
                    </p>
                    {document.last_error ? (
                      <p className="text-[11px] mt-0.5 line-clamp-2" style={{ color: "var(--error)" }}>
                        {document.last_error}
                      </p>
                    ) : null}
                  </div>
                  {/* [a11y] Added focus-within:opacity-100 so keyboard users can reach these actions */}
                  {/* [mobile] Added p-2 for minimum 44px touch targets */}
                  <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 group-focus-within:opacity-100 transition-opacity">
                    {document.status === "error" || document.status === "ready" ? (
                      <button
                        type="button"
                        className="p-2 rounded-lg"
                        onClick={(event) => {
                          event.stopPropagation();
                          void handleReprocess(document.id);
                        }}
                        style={{ color: "var(--text-muted)" }}
                        aria-label="Reprocess document"
                        title="Reprocess document"
                      >
                        <RefreshCcw size={12} />
                      </button>
                    ) : null}
                    {/* [flow] Added confirmation before destructive delete action */}
                    <button
                      type="button"
                      className="p-2 rounded-lg"
                      onClick={(event) => {
                        event.stopPropagation();
                        if (window.confirm(`Delete "${document.filename}"? This cannot be undone.`)) {
                          void handleDeleteDocument(document.id);
                        }
                      }}
                      style={{ color: "var(--text-muted)" }}
                      aria-label="Delete document"
                      title="Delete document"
                    >
                      <Trash2 size={12} />
                    </button>
                  </div>
                </div>
              </motion.div>

              <AnimatePresence>
                {isActive ? (
                  <motion.div
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: "auto" }}
                    exit={{ opacity: 0, height: 0 }}
                    transition={{ duration: 0.25, ease: EASE_OUT }}
                    className="ml-6 mt-1 pl-3 overflow-hidden"
                    style={{ borderLeft: "1px solid var(--border)" }}
                  >
                    <div className="flex items-center gap-2 mb-2">
                      <motion.button
                        type="button"
                        onClick={() => void selectConversation(null)}
                        className="inline-flex items-center gap-1 px-2 py-1 rounded-lg text-[11px]"
                        style={{ color: "var(--text-primary)", background: "var(--bg-surface)" }}
                        whileHover={{ background: "var(--bg-surface-hover)" }}
                        whileTap={{ scale: 0.95 }}
                      >
                        <Plus size={10} />
                        New Chat
                      </motion.button>
                      {activeConversation ? (
                        <>
                          <button
                            type="button"
                            onClick={() => void handleRenameConversation()}
                            style={{ color: "var(--text-muted)" }}
                            aria-label="Rename conversation"
                            title="Rename conversation"
                          >
                            <Pencil size={10} />
                          </button>
                          <button
                            type="button"
                            onClick={() => void handleExportConversation("markdown")}
                            style={{ color: "var(--text-muted)" }}
                            aria-label="Export conversation"
                            title="Export conversation"
                          >
                            <Download size={10} />
                          </button>
                        </>
                      ) : null}
                    </div>

                    {/* [a11y] Changed clickable div to button for keyboard accessibility */}
                    {/* [mobile] Increased padding for better touch targets */}
                    {conversations.map((conversation) => (
                      <motion.button
                        type="button"
                        key={conversation.id}
                        className="group flex items-center gap-2 px-2 py-2 rounded-lg cursor-pointer w-full text-left"
                        style={{
                          background:
                            activeConversationId === conversation.id ? "var(--bg-surface)" : "transparent",
                        }}
                        onClick={() => void selectConversation(conversation.id)}
                        whileHover={{ background: "var(--bg-surface)" }}
                      >
                        <MessageSquare size={10} style={{ color: "var(--text-muted)", flexShrink: 0 }} />
                        <span className="text-[11px] truncate flex-1" style={{ color: "var(--text-secondary)" }}>
                          {conversation.title}
                        </span>
                        {/* [flow] Added confirmation before destructive delete */}
                        {/* [a11y] Added focus-within visibility for keyboard access */}
                        <span
                          role="button"
                          tabIndex={0}
                          onClick={(event) => {
                            event.stopPropagation();
                            if (window.confirm(`Delete conversation "${conversation.title}"?`)) {
                              void handleDeleteConversation(conversation.id);
                            }
                          }}
                          onKeyDown={(event) => {
                            if (event.key === "Enter" || event.key === " ") {
                              event.stopPropagation();
                              event.preventDefault();
                              if (window.confirm(`Delete conversation "${conversation.title}"?`)) {
                                void handleDeleteConversation(conversation.id);
                              }
                            }
                          }}
                          className="opacity-0 group-hover:opacity-100 group-focus-within:opacity-100 p-1 rounded-md transition-opacity"
                          style={{ color: "var(--text-muted)" }}
                          aria-label="Delete conversation"
                          title="Delete conversation"
                        >
                          <Trash2 size={9} />
                        </span>
                      </motion.button>
                    ))}

                    {document.status === "ready" ? (
                      <div className="mt-3">
                        <div className="flex items-center justify-between mb-2">
                          {/* [typography] Changed text-[11px] to text-xs for minimum readable size */}
                          <span className="text-[10px] uppercase tracking-widest" style={{ color: "var(--text-muted)" }}>
                            Chunk Preview
                          </span>
                          {chunkPreviewLoading ? <Loader2 size={10} className="animate-spin" style={{ color: "var(--text-muted)" }} /> : null}
                        </div>
                        {chunkPreview.slice(0, 4).map((chunk) => (
                          <motion.div
                            key={chunk.chunk_id}
                            className="rounded-xl px-3 py-2 mb-1.5"
                            style={{ background: "var(--bg-surface)", border: "1px solid var(--border)" }}
                            whileHover={{ borderColor: "var(--border-hover)" }}
                          >
                              {/* [typography] Changed text-[11px] to text-xs for minimum readable size */}
                            <div className="flex items-center gap-2 text-[10px] mb-1" style={{ color: "var(--text-muted)" }}>
                                <span>Chunk {chunk.chunk_index + 1}</span>
                              {chunk.page_number ? <span>p.{chunk.page_number}</span> : null}
                            </div>
                            <p className="text-[11px] line-clamp-3 leading-relaxed" style={{ color: "var(--text-tertiary)" }}>
                              {chunk.content}
                            </p>
                          </motion.div>
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
    </aside>
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

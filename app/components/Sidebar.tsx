"use client";

import React, { useMemo, useState } from "react";
import {
  BarChart3,
  Cpu,
  Download,
  FileText,
  Loader2,
  MessageSquare,
  Pencil,
  Plus,
  RefreshCcw,
  Search,
  Settings,
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
import { useServerState } from "../lib/server-state";
import { useStore } from "../lib/store";

interface SidebarProps {
  onUploadClick: () => void;
}

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
  const { settings, activeConversationId, activeDocumentId, activeView, sidebarOpen } = state;
  const [search, setSearch] = useState("");
  const [actionError, setActionError] = useState<string | null>(null);
  const auth = {
    clientSessionId: settings.clientSessionId,
    providerApiKey: settings.providerApiKey,
  };

  const visibleDocuments = useMemo(() => {
    const term = search.trim().toLowerCase();
    if (!term) return documents;
    return documents.filter((document) => document.filename.toLowerCase().includes(term));
  }, [documents, search]);

  const activeConversation = conversations.find(
    (conversation) => conversation.id === activeConversationId
  ) ?? null;

  const handleDeleteDocument = async (documentId: string) => {
    try {
      await deleteDocument(auth, documentId);
      if (activeDocumentId === documentId) {
        await selectDocument(null);
        setMessages([]);
      }
      await refreshDocuments();
      setActionError(null);
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "Unable to delete document.");
    }
  };

  const handleReprocess = async (documentId: string) => {
    if (!settings.providerApiKey.trim()) {
      setActionError("Add your provider API key in Settings before reprocessing.");
      return;
    }
    try {
      await reprocessDocument(auth, documentId, settings.embeddingModel);
      await refreshDocuments();
      if (activeDocumentId === documentId) {
        await refreshChunkPreview(documentId);
      }
      setActionError(null);
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "Unable to reprocess document.");
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



  return (
    <aside
      style={{ width: "var(--sidebar-width)" }}
      className={`absolute md:relative z-40 bg-[var(--bg-primary)] flex flex-col h-full border-r transition-transform duration-300 flex-shrink-0 ${
        sidebarOpen ? "translate-x-0" : "-translate-x-full md:hidden"
      }`}
      aria-label="Document navigation"
    >
      <div
        className="flex items-center justify-between px-4 flex-shrink-0"
        style={{
          height: "var(--header-height)",
          borderBottom: "1px solid var(--border)",
          background: "var(--bg-secondary)",
        }}
      >
        <div className="flex items-center gap-2">
          <div
            className="flex items-center justify-center rounded-lg"
            style={{ width: 32, height: 32, background: "var(--accent-soft)" }}
          >
            <FileText size={16} style={{ color: "var(--text-primary)" }} />
          </div>
          <span className="font-semibold text-sm" style={{ color: "var(--text-primary)" }}>
            Document RAG
          </span>
        </div>
        <button
          type="button"
          onClick={() => dispatch({ type: "TOGGLE_SIDEBAR" })}
          className="p-1.5 rounded-md"
          style={{ color: "var(--text-tertiary)" }}
          aria-label="Toggle sidebar"
          title="Toggle sidebar"
        >
          <PanelLeftClose size={18} />
        </button>
      </div>

      {/* [layout] Removed duplicate dashboard icon button — kept full-width one below */}
      <div className="px-3 py-3 flex gap-2 flex-shrink-0">
        <button
          type="button"
          onClick={onUploadClick}
          className="flex-1 flex items-center justify-center gap-2 px-3 py-2 rounded-lg text-sm font-medium"
          style={{ background: "var(--accent)", color: "var(--accent-fg)" }}
        >
          <Upload size={15} />
          Upload
        </button>
        <button
          type="button"
          onClick={() => dispatch({ type: "TOGGLE_SETTINGS" })}
          className="flex items-center justify-center px-3 py-2 rounded-lg"
          style={{
            background: "var(--bg-surface)",
            color: "var(--text-secondary)",
            border: "1px solid var(--border)",
          }}
          aria-label="Open settings"
          title="Open settings"
        >
          <Settings size={16} />
        </button>
      </div>

      <div className="px-3 pb-2 flex-shrink-0">
        {/* Navigation buttons */}
        <div className="flex flex-col gap-1 mb-2">
          {([
            { view: "insights" as const, label: "Insights", icon: <BarChart3 size={14} />, badge: "Shared" },
            { view: "users" as const, label: "Users", icon: <Users size={14} />, badge: "" },
            { view: "models" as const, label: "Models", icon: <Cpu size={14} />, badge: "" },
          ] as const).map((nav) => (
            <button
              key={nav.view}
              type="button"
              onClick={() => dispatch({ type: "SET_ACTIVE_VIEW", payload: nav.view })}
              className="flex w-full items-center justify-between rounded-lg px-3 py-2 text-sm"
              style={{
                background: activeView === nav.view ? "var(--accent-soft)" : "var(--bg-surface)",
                border: `1px solid ${activeView === nav.view ? "var(--border-accent)" : "var(--border)"}`,
                color: activeView === nav.view ? "var(--text-primary)" : "var(--text-secondary)",
              }}
            >
              <span className="inline-flex items-center gap-2">
                {nav.icon}
                {nav.label}
              </span>
              {nav.badge ? (
                <span className="text-[11px]" style={{ color: "var(--text-tertiary)" }}>
                  {nav.badge}
                </span>
              ) : null}
            </button>
          ))}
        </div>
        <div
          className="flex items-center gap-2 rounded-lg px-3 py-2"
          style={{ background: "var(--bg-surface)", border: "1px solid var(--border)" }}
        >
          <Search size={14} style={{ color: "var(--text-muted)" }} />
          {/* [a11y] Added aria-label — input had no associated label element */}
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search documents"
            aria-label="Search documents"
            className="w-full bg-transparent text-sm outline-none"
            style={{ color: "var(--text-primary)" }}
          />
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-2 pb-3">
        <div className="px-2 py-1.5 flex items-center justify-between">
          <span className="text-xs font-semibold uppercase tracking-wider" style={{ color: "var(--text-tertiary)" }}>
            Documents
          </span>
          <div className="flex items-center gap-2">
            {(documentsLoading || conversationsLoading) && <Loader2 size={12} className="animate-spin" style={{ color: "var(--text-tertiary)" }} />}
            <button
              type="button"
              onClick={() => void refreshDocuments()}
              style={{ color: "var(--text-tertiary)" }}
              aria-label="Refresh documents"
              title="Refresh documents"
            >
              <RefreshCcw size={12} />
            </button>
          </div>
        </div>

        {documentsError ? (
          <div className="mx-2 mb-3 rounded-lg px-3 py-2 text-xs" style={{ background: "var(--error-soft)", color: "var(--error)" }}>
            {documentsError}
          </div>
        ) : null}
        {actionError ? (
          <div className="mx-2 mb-3 rounded-lg px-3 py-2 text-xs" style={{ background: "var(--error-soft)", color: "var(--error)" }}>
            {actionError}
          </div>
        ) : null}

        {visibleDocuments.length === 0 ? (
          <div className="px-3 py-6 text-center">
            <FileText size={32} className="mx-auto mb-2" style={{ color: "var(--text-muted)" }} />
            <p className="text-xs" style={{ color: "var(--text-tertiary)" }}>
              {search ? "No matching documents." : "No indexed documents yet."}
            </p>
          </div>
        ) : null}

        {visibleDocuments.map((document) => {
          const isActive = activeDocumentId === document.id;
          const statusColor =
            document.status === "ready"
              ? "var(--success)"
              : document.status === "error"
              ? "var(--error)"
              : "var(--warning)";
          return (
            <div key={document.id} className="mb-2">
              {/* [a11y] Use a keyboard-focusable container so row actions can stay real buttons */}
              <div
                role="button"
                tabIndex={0}
                className="group rounded-xl px-3 py-3 cursor-pointer w-full text-left"
                style={{
                  background: isActive ? "var(--accent-soft)" : "transparent",
                  border: `1px solid ${isActive ? "var(--border-accent)" : "transparent"}`,
                }}
                onClick={() => void selectDocument(document.id)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    void selectDocument(document.id);
                  }
                }}
              >
                <div className="flex items-start gap-2.5">
                  <div
                    className="mt-1 h-2.5 w-2.5 rounded-full flex-shrink-0"
                    style={{ background: statusColor }}
                  />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium truncate" style={{ color: "var(--text-primary)" }}>
                      {document.filename}
                    </p>
                    <p className="text-xs mt-1" style={{ color: "var(--text-tertiary)" }}>
                      {document.status}
                      {document.current_stage ? ` (${document.current_stage})` : ""}
                      {" · "}
                      {document.chunk_count} chunks
                      {document.page_count ? ` · ${document.page_count} pages` : ""}
                    </p>
                    {document.last_error ? (
                      <p className="text-xs mt-1 line-clamp-2" style={{ color: "var(--error)" }}>
                        {document.last_error}
                      </p>
                    ) : null}
                  </div>
                  {/* [a11y] Added focus-within:opacity-100 so keyboard users can reach these actions */}
                  {/* [mobile] Added p-2 for minimum 44px touch targets */}
                  <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 group-focus-within:opacity-100 transition-opacity">
                    {document.status === "error" || document.status === "ready" ? (
                      <button
                        type="button"
                        className="p-2 rounded-md"
                        onClick={(event) => {
                          event.stopPropagation();
                          void handleReprocess(document.id);
                        }}
                        style={{ color: "var(--text-tertiary)" }}
                        aria-label="Reprocess document"
                        title="Reprocess document"
                      >
                        <RefreshCcw size={14} />
                      </button>
                    ) : null}
                    {/* [flow] Added confirmation before destructive delete action */}
                    <button
                      type="button"
                      className="p-2 rounded-md"
                      onClick={(event) => {
                        event.stopPropagation();
                        if (window.confirm(`Delete "${document.filename}"? This cannot be undone.`)) {
                          void handleDeleteDocument(document.id);
                        }
                      }}
                      style={{ color: "var(--text-tertiary)" }}
                      aria-label="Delete document"
                      title="Delete document"
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                </div>
              </div>

              {isActive ? (
                <div className="ml-6 mt-2 pl-3" style={{ borderLeft: "2px solid var(--border)" }}>
                  <div className="flex items-center gap-2 mb-2">
                    <button
                      type="button"
                      onClick={() => void selectConversation(null)}
                      className="inline-flex items-center gap-1 px-2 py-1 rounded-md text-xs"
                      style={{ color: "var(--text-primary)", background: "var(--bg-surface)" }}
                    >
                      <Plus size={12} />
                      New Chat
                    </button>
                    {activeConversation ? (
                      <>
                        <button
                          type="button"
                          onClick={() => void handleRenameConversation()}
                          style={{ color: "var(--text-tertiary)" }}
                          aria-label="Rename conversation"
                          title="Rename conversation"
                        >
                          <Pencil size={12} />
                        </button>
                        <button
                          type="button"
                          onClick={() => void handleExportConversation("markdown")}
                          style={{ color: "var(--text-tertiary)" }}
                          aria-label="Export conversation"
                          title="Export conversation"
                        >
                          <Download size={12} />
                        </button>
                      </>
                    ) : null}
                  </div>

                  {/* [a11y] Changed clickable div to button for keyboard accessibility */}
                  {/* [mobile] Increased padding for better touch targets */}
                  {conversations.map((conversation) => (
                    <button
                      type="button"
                      key={conversation.id}
                      className="group flex items-center gap-2 px-2 py-2.5 rounded-md cursor-pointer w-full text-left"
                      style={{
                        background:
                          activeConversationId === conversation.id ? "var(--bg-surface)" : "transparent",
                      }}
                      onClick={() => void selectConversation(conversation.id)}
                    >
                      <MessageSquare size={12} style={{ color: "var(--text-tertiary)", flexShrink: 0 }} />
                      <span className="text-xs truncate flex-1" style={{ color: "var(--text-secondary)" }}>
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
                        className="opacity-0 group-hover:opacity-100 group-focus-within:opacity-100 p-1.5 rounded-md transition-opacity"
                        style={{ color: "var(--text-tertiary)" }}
                        aria-label="Delete conversation"
                        title="Delete conversation"
                      >
                        <Trash2 size={11} />
                      </span>
                    </button>
                  ))}

                  {document.status === "ready" ? (
                    <div className="mt-3">
                      <div className="flex items-center justify-between mb-2">
                        {/* [typography] Changed text-[11px] to text-xs for minimum readable size */}
                        <span className="text-xs uppercase tracking-wider" style={{ color: "var(--text-tertiary)" }}>
                          Chunk Preview
                        </span>
                        {chunkPreviewLoading ? <Loader2 size={12} className="animate-spin" style={{ color: "var(--text-tertiary)" }} /> : null}
                      </div>
                      {chunkPreview.slice(0, 4).map((chunk) => (
                        <div
                          key={chunk.chunk_id}
                          className="rounded-lg px-3 py-2 mb-2"
                          style={{ background: "var(--bg-surface)", border: "1px solid var(--border)" }}
                        >
                              {/* [typography] Changed text-[11px] to text-xs for minimum readable size */}
                          <div className="flex items-center gap-2 text-xs mb-1" style={{ color: "var(--text-tertiary)" }}>
                                <span>Chunk {chunk.chunk_index + 1}</span>
                            {chunk.page_number ? <span>Page {chunk.page_number}</span> : null}
                          </div>
                          <p className="text-xs line-clamp-4" style={{ color: "var(--text-secondary)" }}>
                            {chunk.content}
                          </p>
                        </div>
                      ))}
                    </div>
                  ) : null}
                </div>
              ) : null}
            </div>
          );
        })}
      </div>
    </aside>
  );
}

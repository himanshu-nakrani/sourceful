"use client";

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  FileText,
  Loader2,
  MessageSquarePlus,
  PanelLeftOpen,
  RefreshCcw,
  Settings,
  Sparkles,
  StopCircle,
  ArrowUp,
  Bug,
  ChevronDown,
  ChevronRight,
} from "lucide-react";
import MessageBubble from "./MessageBubble";
import SourceCard from "./SourceCard";
import {
  reprocessDocument,
  rerunMessage,
  sendChatStream,
  type Citation,
  type GroundingSummary,
  type Message,
  type RetrievalStages,
} from "../lib/api";
import { useServerState } from "../lib/server-state";
import { useStore } from "../lib/store";
import { EASE_OUT } from "../lib/motion";

interface ChatAreaProps {
  onUploadClick: () => void;
}

/**
 * Renders the document-aware chat interface, including message display, submission, streaming control,
 * reruns, source citations, conversation management, and contextual empty/error states.
 *
 * This component drives user interactions for asking questions about one or more indexed documents,
 * handles streaming assistant responses, and coordinates conversation lifecycle actions.
 *
 * @param onUploadClick - Callback invoked when the user chooses to upload a document from the empty state
 * @returns The chat area React element
 */
export default function ChatArea({ onUploadClick }: ChatAreaProps) {
  const { state, dispatch } = useStore();
  const {
    documents,
    messages,
    messagesLoading,
    addMessage,
    appendToLastAssistant,
    refreshConversations,
    selectConversation,
    updateLastAssistantSources,
    setMessages,
  } = useServerState();
  const { settings, activeConversationId, activeDocumentId, activeDocumentIds, sidebarOpen } = state;
  const activeDocument = useMemo(
    () => documents.find((document) => document.id === activeDocumentId) ?? null,
    [documents, activeDocumentId]
  );
  const activeDocuments = useMemo(
    () => documents.filter((d) => activeDocumentIds.includes(d.id)),
    [documents, activeDocumentIds]
  );
  const isMultiDoc = activeDocumentIds.length > 1;
  const [question, setQuestion] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [currentSources, setCurrentSources] = useState<Citation[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [rerunningMessageId, setRerunningMessageId] = useState<string | null>(null);
  const [debugOpen, setDebugOpen] = useState(false);
  const [lastStages, setLastStages] = useState<RetrievalStages | null>(null);
  const [lastLatencyMs, setLastLatencyMs] = useState<number | null>(null);
  const [lastGrounding, setLastGrounding] = useState<GroundingSummary | null>(null);
  const [streamEvents, setStreamEvents] = useState<Array<{ at: number; label: string; detail?: string }>>([]);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  const auth = useMemo(
    () => ({
      clientSessionId: settings.clientSessionId,
      providerApiKey: settings.providerApiKey,
    }),
    [settings.clientSessionId, settings.providerApiKey]
  );

  const suggestions = [
    "Summarize the main themes",
    "List the most important findings",
    "What evidence supports the core conclusion?",
    "What should I pay attention to first?",
  ];

  const canAsk = Boolean(
    activeDocumentId &&
      (isMultiDoc ? activeDocuments.every((d) => d.status === "ready") : activeDocument?.status === "ready") &&
      settings.providerApiKey.trim() &&
      settings.chatModel.trim() &&
      question.trim() &&
      !streaming
  );

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, currentSources]);

  useEffect(() => {
    const element = textareaRef.current;
    if (!element) return;
    element.style.height = "auto";
    element.style.height = `${Math.min(element.scrollHeight, 160)}px`;
  }, [question]);

  const handleSubmit = useCallback(
    async (event?: React.FormEvent) => {
      event?.preventDefault();
      if (!canAsk || !activeDocumentId) return;

      const prompt = question.trim();
      setQuestion("");
      setError(null);
      setCurrentSources([]);
      setStreaming(true);

      const userMessage: Message = {
        id: `temp-user-${Date.now()}`,
        role: "user",
        content: prompt,
        created_at: new Date().toISOString(),
      };
      const assistantMessage: Message = {
        id: `temp-assistant-${Date.now()}`,
        role: "assistant",
        content: "",
        created_at: new Date().toISOString(),
        sources: [],
      };
      addMessage(userMessage);
      addMessage(assistantMessage);

      const controller = new AbortController();
      abortRef.current = controller;
      const startedAt = performance.now();
      setLastGrounding(null);
      setStreamEvents([{ at: 0, label: "request_sent" }]);

      const appendEvent = (label: string, detail?: string) => {
        setStreamEvents((current) => [
          ...current,
          { at: performance.now() - startedAt, label, detail },
        ]);
      };

      let activeConversation = activeConversationId;
      let streamError: Error | null = null;
      let sawServerError = false;

      try {
        await sendChatStream(
          auth,
          settings.provider,
          settings.chatModel,
          activeDocumentId,
          prompt,
          activeConversationId,
          {
            onSources: (payload) => {
              appendEvent("sources", `${payload.sources?.length ?? 0} chunks`);
              setCurrentSources(payload.sources);
              setLastStages(payload.stages ?? null);
              updateLastAssistantSources(payload.sources);
              activeConversation = payload.conversation_id;
              dispatch({ type: "SET_ACTIVE_CONVERSATION", payload: payload.conversation_id });
            },
            onToken: (delta) => {
              appendToLastAssistant(delta);
            },
            onGrounding: (grounding) => {
              appendEvent(
                "grounding",
                grounding.score !== null ? `score=${grounding.score.toFixed(2)}` : "unverified",
              );
              setLastGrounding(grounding);
            },
            onMessageSaved: () => {
              appendEvent("message_saved");
            },
            onDone: () => {
              appendEvent("done");
              setLastLatencyMs(performance.now() - startedAt);
            },
            onError: (payload) => {
              sawServerError = true;
              appendEvent("server_error", payload.code);
              streamError = new Error(payload.error || "Chat failed");
            },
          },
          controller.signal,
          settings.topK,
          settings.similarityThreshold,
          activeDocumentIds,
        );
        if (streamError) throw streamError;
        if (activeConversation) {
          await refreshConversations(activeDocumentId);
        }
      } catch (err) {
        if (!sawServerError) {
          setMessages((current) => current.slice(0, -1));
        }
        if (
          !(err instanceof DOMException) ||
          err.name !== "AbortError"
        ) {
          setError(err instanceof Error ? err.message : "Request failed.");
        }
      } finally {
        setStreaming(false);
        abortRef.current = null;
      }
    },
    [
      activeConversationId,
      activeDocumentId,
      activeDocumentIds,
      addMessage,
      appendToLastAssistant,
      auth,
      canAsk,
      dispatch,
      question,
      refreshConversations,
      setMessages,
      settings.chatModel,
      settings.provider,
      settings.topK,
      settings.similarityThreshold,
      updateLastAssistantSources,
    ]
  );

  const handleRerun = useCallback(
    async (message: Message) => {
      if (
        streaming ||
        !activeDocumentId ||
        !activeConversationId ||
        !settings.providerApiKey.trim() ||
        !settings.chatModel.trim()
      ) {
        return;
      }
      setError(null);
      setCurrentSources([]);
      setStreaming(true);
      setRerunningMessageId(message.id);
      try {
        const response = await rerunMessage(
          auth,
          settings.provider,
          settings.chatModel,
          activeDocumentId,
          activeConversationId,
          message.id,
          settings.topK,
          settings.similarityThreshold
        );
        dispatch({ type: "SET_ACTIVE_CONVERSATION", payload: response.conversation_id });
        await refreshConversations(activeDocumentId);
        await selectConversation(response.conversation_id);
      } catch (rerunError) {
        setError(rerunError instanceof Error ? rerunError.message : "Unable to rerun message.");
      } finally {
        setStreaming(false);
        setRerunningMessageId(null);
      }
    },
    [
      activeConversationId,
      activeDocumentId,
      auth,
      dispatch,
      refreshConversations,
      selectConversation,
      settings.chatModel,
      settings.provider,
      settings.providerApiKey,
      settings.topK,
      settings.similarityThreshold,
      streaming,
    ]
  );

  const handleRetryDocument = async () => {
    if (!activeDocumentId || !settings.providerApiKey.trim()) return;
    try {
      setError(null);
      await reprocessDocument(auth, activeDocumentId, settings.embeddingModel);
    } catch (retryError) {
      setError(retryError instanceof Error ? retryError.message : "Unable to retry indexing.");
    }
  };

  const stopStreaming = () => {
    abortRef.current?.abort();
    setStreaming(false);
  };

  const renderEmptyState = () => {
    if (!settings.providerApiKey.trim()) {
      return (
        <StateCard
          title="API Key Required"
          description="Add your OpenAI or Google AI API key in Settings to start chatting with your documents."
          primaryLabel="Open Settings"
          onPrimary={() => dispatch({ type: "SET_SETTINGS_OPEN", payload: true })}
        />
      );
    }

    if (!activeDocument) {
      return (
        <StateCard
          title="Welcome to Document RAG"
          description="Upload a document, inspect the extracted chunks, and ask grounded questions with source citations."
          primaryLabel="Upload Document"
          onPrimary={onUploadClick}
          secondaryLabel="Open Settings"
          onSecondary={() => dispatch({ type: "SET_SETTINGS_OPEN", payload: true })}
        />
      );
    }

    if (activeDocument.status !== "ready") {
      return (
        <StateCard
          title={activeDocument.status === "error" ? "Indexing Failed" : "Indexing In Progress"}
          description={
            activeDocument.status === "error"
              ? activeDocument.last_error || "The document could not be indexed."
              : "The worker is preparing chunks and embeddings for this document."
          }
          primaryLabel={activeDocument.status === "error" ? "Retry Indexing" : undefined}
          onPrimary={activeDocument.status === "error" ? handleRetryDocument : undefined}
        />
      );
    }

    return (
      <motion.div
        className="flex flex-col items-center justify-center py-20"
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, ease: EASE_OUT }}
      >
        <motion.div
          className="flex items-center justify-center rounded-2xl mb-5"
          style={{
            width: 56,
            height: 56,
            background: "var(--accent-brand-soft)",
            border: "1px solid var(--border)",
          }}
          animate={{ y: [0, -4, 0] }}
          transition={{ duration: 3, repeat: Infinity, ease: "easeInOut" }}
        >
          <Sparkles size={24} style={{ color: "var(--accent-brand)" }} />
        </motion.div>
        <h3
          className="text-lg font-semibold mb-1"
          style={{ color: "var(--text-primary)", letterSpacing: "-0.02em" }}
        >
          Ask about {activeDocument.filename}
        </h3>
        <p className="text-sm mb-8 text-center max-w-md" style={{ color: "var(--text-tertiary)" }}>
          Retrieved chunks will appear with similarity scores and page references.
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 w-full max-w-xl">
          {suggestions.map((suggestion, i) => (
            <motion.button
              key={suggestion}
              type="button"
              onClick={() => {
                setQuestion(suggestion);
                textareaRef.current?.focus();
              }}
              className="text-left px-4 py-3 rounded-xl text-sm group"
              style={{
                background: "var(--bg-surface)",
                border: "1px solid var(--border)",
                color: "var(--text-secondary)",
              }}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.1 + i * 0.05, duration: 0.4, ease: EASE_OUT }}
              whileHover={{
                borderColor: "var(--border-hover)",
                background: "var(--bg-surface-hover)",
              }}
            >
              <span className="inline-block mr-1.5" style={{ color: "var(--accent-brand)" }}>→</span>
              {suggestion}
            </motion.button>
          ))}
        </div>
      </motion.div>
    );
  };

  return (
    <div className="flex-1 flex flex-col h-full w-full min-w-0">
      {/* Header bar */}
      <div
        className="flex items-center gap-3 px-4 flex-shrink-0 relative"
        style={{
          height: "var(--header-height)",
          borderBottom: "1px solid var(--border)",
          background: "var(--bg-primary)",
        }}
      >
        <motion.button
          type="button"
          onClick={() => dispatch({ type: "TOGGLE_SIDEBAR" })}
          className={`p-1.5 rounded-lg ${sidebarOpen ? 'md:hidden' : ''}`}
          style={{ color: "var(--text-muted)" }}
          aria-label="Toggle sidebar"
          title="Toggle sidebar"
          whileHover={{ color: "var(--text-secondary)" }}
          whileTap={{ scale: 0.92 }}
        >
          <PanelLeftOpen size={16} />
        </motion.button>
        {isMultiDoc ? (
          <div className="flex items-center gap-2 min-w-0">
            <FileText size={14} style={{ color: "var(--accent-brand)", flexShrink: 0 }} />
            <span className="text-sm font-medium truncate" style={{ color: "var(--text-primary)", letterSpacing: "-0.01em" }}>
              {activeDocumentIds.length} documents
            </span>
            <span
              className="text-[10px] px-2 py-0.5 rounded-full flex-shrink-0"
              style={{ background: "var(--accent-brand-soft)", color: "var(--accent-brand)" }}
            >
              {activeDocuments.reduce((sum, d) => sum + d.chunk_count, 0)} chunks
            </span>
          </div>
        ) : activeDocument ? (
          <div className="flex items-center gap-2 min-w-0">
            <FileText size={14} style={{ color: "var(--accent-brand)", flexShrink: 0 }} />
            <span className="text-sm font-medium truncate" style={{ color: "var(--text-primary)", letterSpacing: "-0.01em" }}>
              {activeDocument.filename}
            </span>
            <span
              className="text-[10px] px-2 py-0.5 rounded-full flex-shrink-0"
              style={{ background: "var(--accent-brand-soft)", color: "var(--accent-brand)" }}
            >
              {activeDocument.chunk_count} chunks
            </span>
          </div>
        ) : (
          <span className="text-sm" style={{ color: "var(--text-muted)" }}>
            Select a document to start
          </span>
        )}
        <div className="flex-1" />
        <motion.button
          type="button"
          onClick={() => setDebugOpen((v) => !v)}
          className="p-1.5 rounded-lg flex items-center gap-1.5"
          style={{
            color: debugOpen ? "var(--accent-brand)" : "var(--text-muted)",
            background: debugOpen ? "var(--accent-brand-soft)" : "transparent",
          }}
          aria-label="Toggle retrieval debug panel"
          title="Retrieval debug panel"
          whileHover={{ color: "var(--text-secondary)" }}
          whileTap={{ scale: 0.92 }}
        >
          <Bug size={14} />
          <span className="text-[11px] font-medium hidden sm:inline">Debug</span>
        </motion.button>
        {activeDocument && activeDocument.status !== "ready" ? (
          <motion.button
            type="button"
            onClick={handleRetryDocument}
            style={{ color: "var(--text-muted)" }}
            aria-label="Retry processing document"
            title="Retry processing document"
            whileHover={{ rotate: 180, color: "var(--text-secondary)" }}
            transition={{ duration: 0.4 }}
          >
            <RefreshCcw size={14} />
          </motion.button>
        ) : null}
      </div>

      <RetrievalDebugPanel
        open={debugOpen}
        stages={lastStages}
        latencyMs={lastLatencyMs}
        sources={currentSources}
        topK={settings.topK}
        grounding={lastGrounding}
        streamEvents={streamEvents}
      />

      {/* Messages area */}
      <div className="flex-1 overflow-y-auto px-4 py-6" style={{ background: "var(--bg-primary)" }}>
        <div className="max-w-3xl mx-auto flex flex-col gap-4">
          {messages.length === 0 ? (
            renderEmptyState()
          ) : (
            <>
              {messages.map((message, idx) => (
                <React.Fragment key={message.id}>
                  <motion.div
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.3, delay: idx * 0.02, ease: EASE_OUT }}
                  >
                    <MessageBubble
                      message={message}
                      onRerun={
                        message.role === "user" && activeConversationId ? handleRerun : undefined
                      }
                      rerunDisabled={streaming || rerunningMessageId === message.id}
                      isStreaming={
                        streaming &&
                        message.role === "assistant" &&
                        idx === messages.length - 1
                      }
                    />
                  </motion.div>
                  {message.role === "assistant" && message.sources?.length ? (
                    <SourceCard sources={message.sources} />
                  ) : null}
                </React.Fragment>
              ))}
              {streaming && currentSources.length ? <SourceCard sources={currentSources} /> : null}
              {messagesLoading ? (
                <div className="flex items-center gap-2 pl-11" style={{ color: "var(--text-muted)" }}>
                  <Loader2 size={12} className="animate-spin" />
                  <span className="text-xs">Loading conversation…</span>
                </div>
              ) : null}
            </>
          )}
          <div ref={endRef} />
        </div>
      </div>

      {/* Error bar */}
      <AnimatePresence>
        {error ? (
          <motion.div
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 4 }}
            className="mx-4 mb-2 px-3 py-2 rounded-xl text-sm"
            style={{ background: "var(--error-soft)", color: "var(--error)" }}
          >
            {error}
          </motion.div>
        ) : null}
      </AnimatePresence>

      {/* Input area */}
      {activeDocument?.status === "ready" ? (
        <div className="flex-shrink-0 px-4 pb-4 pt-2" style={{ background: "var(--bg-primary)" }}>
          <form onSubmit={handleSubmit} className="max-w-3xl mx-auto relative">
            <motion.div
              className="flex items-end rounded-2xl overflow-hidden border border-[var(--border)] bg-[var(--bg-secondary)] transition-[border-color,box-shadow] duration-200 focus-within:border-[var(--border-hover)] focus-within:shadow-[0_0_0_3px_rgba(99,102,241,0.06)]"
            >
              <textarea
                ref={textareaRef}
                value={question}
                onChange={(event) => setQuestion(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" && !event.shiftKey) {
                    event.preventDefault();
                    void handleSubmit();
                  }
                }}
                placeholder={
                  settings.providerApiKey.trim()
                    ? "Ask a question about your document…"
                    : "Add your provider API key in Settings first"
                }
                disabled={!settings.providerApiKey.trim() || streaming}
                rows={1}
                aria-label="Ask a question about your document"
                className="flex-1 resize-none bg-transparent px-4 py-3.5 text-sm outline-none"
                style={{ color: "var(--text-primary)", maxHeight: 160, minHeight: 44 }}
              />
              <div className="flex items-center gap-1 p-1.5">
                {streaming ? (
                  <motion.button
                    type="button"
                    onClick={stopStreaming}
                    className="flex items-center justify-center p-2 rounded-xl"
                    style={{ color: "var(--warning)" }}
                    aria-label="Stop generating response"
                    title="Stop generating response"
                    whileTap={{ scale: 0.9 }}
                  >
                    <StopCircle size={18} />
                  </motion.button>
                ) : null}
                <motion.button
                  type="submit"
                  disabled={!canAsk}
                  className="flex items-center justify-center p-2 rounded-xl"
                  style={{
                    background: canAsk ? "var(--accent)" : "transparent",
                    color: canAsk ? "var(--accent-fg)" : "var(--text-muted)",
                  }}
                  aria-label="Send message"
                  title="Send message"
                  whileHover={canAsk ? { scale: 1.05 } : {}}
                  whileTap={canAsk ? { scale: 0.92 } : {}}
                  transition={{ type: "spring", stiffness: 400, damping: 17 }}
                >
                  {streaming ? <Loader2 size={16} className="animate-spin" /> : <ArrowUp size={16} />}
                </motion.button>
              </div>
            </motion.div>
            <p className="text-center mt-2 text-[10px]" style={{ color: "var(--text-muted)" }}>
              Sources include chunk IDs, scores, and page references.
            </p>
          </form>
        </div>
      ) : null}
    </div>
  );
}

function RetrievalDebugPanel({
  open,
  stages,
  latencyMs,
  sources,
  topK,
  grounding,
  streamEvents,
}: {
  open: boolean;
  stages: RetrievalStages | null;
  latencyMs: number | null;
  sources: Citation[];
  topK: number;
  grounding: GroundingSummary | null;
  streamEvents: Array<{ at: number; label: string; detail?: string }>;
}) {
  const [sourcesExpanded, setSourcesExpanded] = useState(true);
  const [eventsExpanded, setEventsExpanded] = useState(false);
  return (
    <AnimatePresence initial={false}>
      {open ? (
        <motion.div
          initial={{ height: 0, opacity: 0 }}
          animate={{ height: "auto", opacity: 1 }}
          exit={{ height: 0, opacity: 0 }}
          transition={{ duration: 0.2, ease: EASE_OUT }}
          style={{
            borderBottom: "1px solid var(--border)",
            background: "var(--bg-secondary)",
            overflow: "hidden",
          }}
          aria-label="Retrieval debug panel"
        >
          <div className="px-4 py-3 max-w-3xl mx-auto flex flex-col gap-3">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-[11px] font-semibold uppercase tracking-wide" style={{ color: "var(--text-tertiary)" }}>
                Retrieval
              </span>
              <StageChip label="top_k" value={stages?.requested_top_k ?? topK} />
              <StageChip
                label="hybrid"
                value={stages?.hybrid_enabled === undefined ? "—" : stages.hybrid_enabled ? "on" : "off"}
                accent={stages?.hybrid_enabled}
              />
              <StageChip
                label="reranker"
                value={
                  stages?.reranker_enabled === undefined ? "—" : stages.reranker_enabled ? "on" : "off"
                }
                accent={stages?.reranker_enabled}
              />
              {stages?.dense_k !== undefined ? <StageChip label="dense_k" value={stages.dense_k} /> : null}
              {stages?.dense_hits !== undefined ? <StageChip label="dense" value={stages.dense_hits} /> : null}
              {stages?.fts_hits !== undefined ? <StageChip label="fts" value={stages.fts_hits} /> : null}
              {stages?.fused_hits !== undefined ? <StageChip label="fused" value={stages.fused_hits} /> : null}
              {stages?.rerank_reordered !== undefined ? (
                <StageChip label="reordered" value={stages.rerank_reordered} />
              ) : null}
              {stages?.final_hits !== undefined ? <StageChip label="final" value={stages.final_hits} /> : null}
              {stages?.mmr_enabled ? (
                <StageChip label="mmr" value="on" accent />
              ) : null}
              {Array.isArray(stages?.query_transforms) && (stages?.query_transforms as string[]).length ? (
                <StageChip
                  label="transforms"
                  value={(stages?.query_transforms as string[]).join("+")}
                  accent
                />
              ) : null}
              {grounding?.enabled ? (
                <StageChip
                  label="grounded"
                  value={
                    grounding.score !== null && grounding.score !== undefined
                      ? grounding.score.toFixed(2)
                      : grounding.verified === null
                      ? "—"
                      : grounding.verified
                      ? "yes"
                      : "no"
                  }
                  accent={grounding.verified === true}
                />
              ) : null}
              {latencyMs !== null ? (
                <StageChip label="total" value={`${latencyMs.toFixed(0)} ms`} accent />
              ) : null}
            </div>

            {streamEvents.length > 0 ? (
              <div>
                <button
                  type="button"
                  onClick={() => setEventsExpanded((v) => !v)}
                  className="flex items-center gap-1 text-[11px] font-medium"
                  style={{ color: "var(--text-tertiary)" }}
                >
                  {eventsExpanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
                  Stream timeline ({streamEvents.length} events)
                </button>
                {eventsExpanded ? (
                  <div className="mt-2 flex flex-col gap-1">
                    {streamEvents.map((ev, i) => (
                      <div
                        key={`${ev.label}-${i}`}
                        className="flex items-center gap-2 text-[11px]"
                        style={{ fontFamily: "var(--font-mono, monospace)" }}
                      >
                        <span style={{ color: "var(--text-muted)", minWidth: 60 }}>
                          {ev.at.toFixed(0)} ms
                        </span>
                        <span style={{ color: "var(--accent-brand)", minWidth: 120 }}>
                          {ev.label}
                        </span>
                        {ev.detail ? (
                          <span style={{ color: "var(--text-secondary)" }}>{ev.detail}</span>
                        ) : null}
                      </div>
                    ))}
                  </div>
                ) : null}
              </div>
            ) : null}

            {sources.length ? (
              <div>
                <button
                  type="button"
                  onClick={() => setSourcesExpanded((v) => !v)}
                  className="flex items-center gap-1 text-[11px] font-medium"
                  style={{ color: "var(--text-tertiary)" }}
                >
                  {sourcesExpanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
                  Top {sources.length} chunks
                </button>
                {sourcesExpanded ? (
                  <div className="mt-2 flex flex-col gap-1.5">
                    {sources.map((source, index) => (
                      <div
                        key={source.chunk_id}
                        className="px-2.5 py-1.5 rounded-lg text-[11px] flex gap-2"
                        style={{
                          background: "var(--bg-surface)",
                          border: "1px solid var(--border)",
                        }}
                      >
                        <span style={{ color: "var(--text-muted)", fontFamily: "var(--font-mono, monospace)" }}>
                          [{index + 1}]
                        </span>
                        <span
                          style={{
                            color: "var(--accent-brand)",
                            fontFamily: "var(--font-mono, monospace)",
                            minWidth: 54,
                          }}
                        >
                          {source.score.toFixed(4)}
                        </span>
                        {source.page_number !== null && source.page_number !== undefined ? (
                          <span style={{ color: "var(--text-muted)" }}>p{source.page_number}</span>
                        ) : null}
                        <span
                          className="truncate flex-1"
                          style={{ color: "var(--text-secondary)" }}
                          title={source.excerpt}
                        >
                          {source.excerpt}
                        </span>
                      </div>
                    ))}
                  </div>
                ) : null}
              </div>
            ) : (
              <p className="text-[11px]" style={{ color: "var(--text-muted)" }}>
                Send a question to see retrieval stages and top chunks.
              </p>
            )}
          </div>
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}

function StageChip({
  label,
  value,
  accent,
}: {
  label: string;
  value: string | number | boolean;
  accent?: boolean;
}) {
  return (
    <span
      className="px-2 py-0.5 rounded-md text-[10px] flex items-center gap-1"
      style={{
        background: accent ? "var(--accent-brand-soft)" : "var(--bg-surface)",
        color: accent ? "var(--accent-brand)" : "var(--text-secondary)",
        border: "1px solid var(--border)",
        fontFamily: "var(--font-mono, monospace)",
      }}
    >
      <span style={{ color: "var(--text-muted)" }}>{label}</span>
      <span>{String(value)}</span>
    </span>
  );
}

function StateCard({
  title,
  description,
  primaryLabel,
  onPrimary,
  secondaryLabel,
  onSecondary,
}: {
  title: string;
  description: string;
  primaryLabel?: string;
  onPrimary?: () => void;
  secondaryLabel?: string;
  onSecondary?: () => void;
}) {
  return (
    <motion.div
      className="flex flex-col items-center justify-center py-20"
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.6, ease: EASE_OUT }}
    >
      <motion.div
        className="flex items-center justify-center rounded-2xl mb-5"
        style={{
          width: 56,
          height: 56,
          background: "var(--accent-brand-soft)",
          border: "1px solid var(--border)",
        }}
        animate={{ y: [0, -4, 0] }}
        transition={{ duration: 3, repeat: Infinity, ease: "easeInOut" }}
      >
        <MessageSquarePlus size={24} style={{ color: "var(--accent-brand)" }} />
      </motion.div>
      <h3
        className="text-lg font-semibold mb-2"
        style={{ color: "var(--text-primary)", letterSpacing: "-0.02em" }}
      >
        {title}
      </h3>
      <p className="text-sm text-center max-w-md mb-6" style={{ color: "var(--text-tertiary)" }}>
        {description}
      </p>
      <div className="flex gap-3">
        {primaryLabel && onPrimary ? (
          <motion.button
            type="button"
            onClick={onPrimary}
            className="flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-medium"
            style={{ background: "var(--accent)", color: "var(--accent-fg)" }}
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.97 }}
            transition={{ type: "spring", stiffness: 400, damping: 17 }}
          >
            {primaryLabel}
          </motion.button>
        ) : null}
        {secondaryLabel && onSecondary ? (
          <motion.button
            type="button"
            onClick={onSecondary}
            className="flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-medium"
            style={{
              background: "var(--bg-surface)",
              color: "var(--text-secondary)",
              border: "1px solid var(--border)",
            }}
            whileHover={{ borderColor: "var(--border-hover)" }}
            whileTap={{ scale: 0.97 }}
          >
            <Settings size={14} />
            {secondaryLabel}
          </motion.button>
        ) : null}
      </div>
    </motion.div>
  );
}

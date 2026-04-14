"use client";

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  FileText,
  Loader2,
  MessageSquarePlus,
  PanelLeftOpen,
  RefreshCcw,
  Send,
  Settings,
  Sparkles,
  StopCircle,
} from "lucide-react";
import MessageBubble from "./MessageBubble";
import SourceCard from "./SourceCard";
import { reprocessDocument, rerunMessage, sendChat, type Citation, type Message } from "../lib/api";
import { useServerState } from "../lib/server-state";
import { useStore } from "../lib/store";

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
      try {
        const response = await sendChat(
          auth,
          settings.provider,
          settings.chatModel,
          activeDocumentId,
          prompt,
          activeConversationId,
          controller.signal,
          settings.topK,
          settings.similarityThreshold,
          activeDocumentIds
        );

        setCurrentSources(response.sources);
        updateLastAssistantSources(response.sources);
        appendToLastAssistant(response.content);
        dispatch({ type: "SET_ACTIVE_CONVERSATION", payload: response.conversation_id });
        await refreshConversations(activeDocumentId);
      } catch (streamError) {
        setMessages((current) => current.slice(0, -1));
        if (
          !(streamError instanceof DOMException) ||
          streamError.name !== "AbortError"
        ) {
          setError(
            streamError instanceof Error ? streamError.message : "Request failed."
          );
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
      <div className="flex flex-col items-center justify-center py-16 animate-fade-in">
        <div
          className="flex items-center justify-center rounded-2xl mb-4"
          style={{
            width: 64,
            height: 64,
            background: "linear-gradient(135deg, var(--bg-surface), var(--bg-tertiary))",
            border: "1px solid var(--border)",
            boxShadow: "var(--shadow-glow)",
          }}
        >
          <Sparkles size={28} style={{ color: "var(--text-primary)" }} />
        </div>
        <h3 className="text-lg font-semibold mb-1" style={{ color: "var(--text-primary)" }}>
          Ask about {activeDocument.filename}
        </h3>
        <p className="text-sm mb-6 text-center max-w-md" style={{ color: "var(--text-tertiary)" }}>
          Retrieved chunks will appear with similarity scores and page references so you can inspect the grounding before trusting the answer.
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 w-full max-w-xl">
          {suggestions.map((suggestion) => (
            <button
              key={suggestion}
              type="button"
              onClick={() => {
                setQuestion(suggestion);
                textareaRef.current?.focus();
              }}
              className="text-left px-3 py-2.5 rounded-lg text-sm"
              style={{
                background: "var(--bg-surface)",
                border: "1px solid var(--border)",
                color: "var(--text-secondary)",
              }}
            >
              {suggestion}
            </button>
          ))}
        </div>
      </div>
    );
  };

  return (
    <div className="flex-1 flex flex-col h-full w-full min-w-0">
      <div
        className="flex items-center gap-3 px-4 flex-shrink-0"
        style={{
          height: "var(--header-height)",
          borderBottom: "1px solid var(--border)",
          background: "var(--bg-secondary)",
        }}
      >
        <button
          type="button"
          onClick={() => dispatch({ type: "TOGGLE_SIDEBAR" })}
          className={`p-1.5 rounded-md ${sidebarOpen ? 'md:hidden' : ''}`}
          style={{ color: "var(--text-tertiary)" }}
          aria-label="Toggle sidebar"
          title="Toggle sidebar"
        >
          <PanelLeftOpen size={18} />
        </button>
        {isMultiDoc ? (
          <div className="flex items-center gap-2 min-w-0">
            <FileText size={16} style={{ color: "var(--accent)", flexShrink: 0 }} />
            <span className="text-sm font-medium truncate" style={{ color: "var(--text-primary)" }}>
              {activeDocumentIds.length} documents
            </span>
            <span
              className="text-xs px-2 py-0.5 rounded-full flex-shrink-0"
              style={{ background: "var(--accent-soft)", color: "var(--accent-hover)" }}
            >
              {activeDocuments.reduce((sum, d) => sum + d.chunk_count, 0)} chunks
            </span>
          </div>
        ) : activeDocument ? (
          <div className="flex items-center gap-2 min-w-0">
            <FileText size={16} style={{ color: "var(--accent)", flexShrink: 0 }} />
            <span className="text-sm font-medium truncate" style={{ color: "var(--text-primary)" }}>
              {activeDocument.filename}
            </span>
            <span
              className="text-xs px-2 py-0.5 rounded-full flex-shrink-0"
              style={{ background: "var(--accent-soft)", color: "var(--accent-hover)" }}
            >
              {activeDocument.chunk_count} chunks
            </span>
          </div>
        ) : (
          <span className="text-sm" style={{ color: "var(--text-tertiary)" }}>
            Select a document to start
          </span>
        )}
        <div className="flex-1" />
        {activeDocument && activeDocument.status !== "ready" ? (
          <button
            type="button"
            onClick={handleRetryDocument}
            style={{ color: "var(--text-tertiary)" }}
            aria-label="Retry processing document"
            title="Retry processing document"
          >
            <RefreshCcw size={16} />
          </button>
        ) : null}
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-6" style={{ background: "var(--bg-primary)" }}>
        <div className="max-w-3xl mx-auto flex flex-col gap-4">
          {messages.length === 0 ? (
            renderEmptyState()
          ) : (
            <>
              {messages.map((message) => (
                <React.Fragment key={message.id}>
                  <MessageBubble
                    message={message}
                    onRerun={
                      message.role === "user" && activeConversationId ? handleRerun : undefined
                    }
                    rerunDisabled={streaming || rerunningMessageId === message.id}
                  />
                  {message.role === "assistant" && message.sources?.length ? (
                    <SourceCard sources={message.sources} />
                  ) : null}
                </React.Fragment>
              ))}
              {streaming && currentSources.length ? <SourceCard sources={currentSources} /> : null}
              {messagesLoading ? (
                <div className="flex items-center gap-2 pl-11" style={{ color: "var(--text-tertiary)" }}>
                  <Loader2 size={14} className="animate-spin" />
                  <span className="text-xs">Loading conversation…</span>
                </div>
              ) : null}
            </>
          )}
          <div ref={endRef} />
        </div>
      </div>

      {error ? (
        <div className="mx-4 mb-2 px-3 py-2 rounded-lg text-sm" style={{ background: "var(--error-soft)", color: "var(--error)" }}>
          {error}
        </div>
      ) : null}

      {activeDocument?.status === "ready" ? (
        <div className="flex-shrink-0 px-4 pb-4 pt-2" style={{ background: "var(--bg-primary)" }}>
          <form onSubmit={handleSubmit} className="max-w-3xl mx-auto relative">
            <div
              className="flex items-end rounded-2xl"
              style={{
                background: "var(--glass-bg)",
                backdropFilter: "blur(var(--glass-blur))",
                WebkitBackdropFilter: "blur(var(--glass-blur))",
                border: "1px solid var(--glass-border)",
                boxShadow: "var(--shadow-lg)",
              }}
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
                className="flex-1 resize-none bg-transparent px-4 py-3 text-sm outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]"
                style={{ color: "var(--text-primary)", maxHeight: 160, minHeight: 44 }}
              />
              <button
                type="button"
                onClick={streaming ? stopStreaming : undefined}
                disabled={!streaming}
                className="flex items-center justify-center p-2 m-1.5 rounded-lg"
                style={{ color: streaming ? "var(--warning)" : "var(--text-muted)" }}
                aria-label="Stop generating response"
                title="Stop generating response"
              >
                <StopCircle size={18} />
              </button>
              <button
                type="submit"
                disabled={!canAsk}
                className="flex items-center justify-center p-2 m-1.5 rounded-lg"
                style={{
                  background: canAsk ? "var(--accent)" : "transparent",
                  color: canAsk ? "var(--accent-fg)" : "var(--text-muted)",
                }}
                aria-label="Send message"
                title="Send message"
              >
                {streaming ? <Loader2 size={18} className="animate-spin" /> : <Send size={18} />}
              </button>
            </div>
            <p className="text-center mt-2 text-xs" style={{ color: "var(--text-muted)" }}>
              Structured sources include chunk ids, scores, and page references when available.
            </p>
          </form>
        </div>
      ) : null}
    </div>
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
    <div className="flex flex-col items-center justify-center py-20 animate-fade-in">
      <div
        className="flex items-center justify-center rounded-2xl mb-4"
        style={{
          width: 72,
          height: 72,
          background: "linear-gradient(135deg, var(--bg-secondary), var(--bg-primary))",
          border: "1px solid var(--border)",
          boxShadow: "var(--shadow-glow)",
        }}
      >
        <MessageSquarePlus size={32} style={{ color: "var(--text-secondary)" }} />
      </div>
      <h3 className="text-lg font-semibold mb-2" style={{ color: "var(--text-primary)" }}>
        {title}
      </h3>
      <p className="text-sm text-center max-w-md mb-6" style={{ color: "var(--text-tertiary)" }}>
        {description}
      </p>
      <div className="flex gap-3">
        {primaryLabel && onPrimary ? (
          <button
            type="button"
            onClick={onPrimary}
            className="flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium"
            style={{ background: "var(--accent)", color: "var(--accent-fg)" }}
          >
            <MessageSquarePlus size={16} />
            {primaryLabel}
          </button>
        ) : null}
        {secondaryLabel && onSecondary ? (
          <button
            type="button"
            onClick={onSecondary}
            className="flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium"
            style={{
              background: "var(--bg-surface)",
              color: "var(--text-secondary)",
              border: "1px solid var(--border)",
            }}
          >
            <Settings size={16} />
            {secondaryLabel}
          </button>
        ) : null}
      </div>
    </div>
  );
}

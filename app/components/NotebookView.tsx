"use client";

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useOnChange } from "../lib/use-on-change";
import { AnimatePresence, motion } from "framer-motion";
import dynamic from "next/dynamic";
import {
  ChevronLeft,
  ChevronRight,
  FileText,
  Highlighter,
  Loader2,
  MessageSquare,
  Send,
  X,
} from "lucide-react";
import {
  getDocument,
  getDocumentContent,
  sendChat,
  type Citation,
  type DocumentInfo,
} from "../lib/api";
import { useStore } from "../lib/store";
import { transitionFast, transitionNormal } from "../lib/motion";
import { CitationPreview } from "./CitationPreview";
import { Button, ErrorBanner, StatusDot } from "./ui";

const NotebookPdf = dynamic(
  () => import("./NotebookPdf").then((module) => module.NotebookPdf),
  {
    ssr: false,
    loading: () => (
      <div className="flex h-full items-center justify-center">
        <Loader2
          className="h-7 w-7 animate-spin"
          style={{ color: "var(--accent-primary)" }}
        />
      </div>
    ),
  }
);

interface NotebookViewProps {
  documentId: string;
  initialPage?: number;
  onClose?: () => void;
}

interface NotebookMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
}

interface Highlight {
  page: number;
  text: string;
}

/**
 * Ghost icon button: quiet, tooltip-bearing control for header actions
 * (close, page nav, zoom). Disabled state dims via text tokens.
 */
function GhostIconButton({
  label,
  onClick,
  disabled = false,
  compact = false,
  children,
}: {
  label: string;
  onClick: () => void;
  disabled?: boolean;
  compact?: boolean;
  children: React.ReactNode;
}) {
  const [hover, setHover] = useState(false);
  const showHover = hover && !disabled;
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-label={label}
      title={label}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      className="inline-flex items-center justify-center rounded-md transition-colors focus-ring disabled:cursor-not-allowed"
      style={{
        padding: compact ? 4 : 6,
        color: disabled
          ? "var(--text-faint)"
          : showHover
            ? "var(--text-primary)"
            : "var(--text-secondary)",
        background: showHover ? "var(--bg-surface-hover)" : "transparent",
      }}
    >
      {children}
    </button>
  );
}

/** Mono [n] / p.N evidence chip in the accent color; jumps to the cited page. */
function CitationChip({
  citation,
  index,
  onClick,
}: {
  citation: Citation;
  index: number;
  onClick: (citation: Citation) => void;
}) {
  const [hover, setHover] = useState(false);
  return (
    <CitationPreview citation={citation}>
      <button
        type="button"
        onClick={() => onClick(citation)}
        onMouseEnter={() => setHover(true)}
        onMouseLeave={() => setHover(false)}
        className="data-num inline-flex items-center gap-1 px-1.5 py-0.5 text-[11px] transition-colors focus-ring"
        style={{
          borderRadius: "var(--radius-xs)",
          background: hover ? "var(--accent-primary-glow)" : "var(--accent-primary-soft)",
          color: "var(--accent-primary)",
          border: `1px solid ${hover ? "var(--accent-primary)" : "var(--accent-primary-soft)"}`,
        }}
        >
          <Highlighter className="h-3 w-3" style={{ color: "var(--accent-primary)" }} />
          {citation.page_number ? `p. ${citation.page_number}` : `[${index + 1}]`}
        </button>
    </CitationPreview>
  );
}

// ⚡ BOLT OPTIMIZATION:
// Wrapped NotebookMessageBubble in React.memo to prevent expensive React re-renders
// for older messages during rapid state updates, such as when typing in the input
// or when active highlights change.
const NotebookMessageBubble = React.memo(function NotebookMessageBubble({
  message,
  onCitationClick,
}: {
  message: NotebookMessage;
  onCitationClick: (citation: Citation) => void;
}) {
  const isUser = message.role === "user";
  return (
    <div className="flex" style={{ justifyContent: isUser ? "flex-end" : "flex-start" }}>
      <div
        className="max-w-[85%] p-3"
        style={{
          // User turns are hairline surface cards; assistant turns sit plain on
          // the pane with a 2px left border edge (matches the main chat).
          background: isUser ? "var(--bg-surface)" : "transparent",
          border: isUser ? "1px solid var(--border)" : undefined,
          borderLeft: isUser ? undefined : "2px solid var(--border-hover)",
          borderRadius: isUser ? "var(--radius-lg)" : "var(--radius-xs)",
          color: "var(--text-primary)",
        }}
      >
        <p className="whitespace-pre-wrap text-sm leading-relaxed">{message.content}</p>
        {message.citations && message.citations.length > 0 && (
          <div className="mt-2.5 pt-2.5" style={{ borderTop: "1px solid var(--border)" }}>
            <p
              className="mb-1.5 text-[10px] uppercase tracking-widest"
              style={{ color: "var(--text-tertiary)" }}
            >
              Sources
            </p>
            <div className="flex flex-wrap gap-1">
              {message.citations.map((citation, index) => (
                <CitationChip
                  key={citation.chunk_id}
                  citation={citation}
                  index={index}
                  onClick={onCitationClick}
                />
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
});

export function NotebookView({ documentId, initialPage = 1, onClose }: NotebookViewProps) {
  const { state } = useStore();
  const { settings } = state;
  const auth = useMemo(
    () => ({
      clientSessionId: settings.clientSessionId,
      providerApiKey: settings.providerApiKey,
    }),
    [settings.clientSessionId, settings.providerApiKey]
  );

  const [doc, setDoc] = useState<DocumentInfo | null>(null);
  const [documentError, setDocumentError] = useState<string | null>(null);
  const [pdfUrl, setPdfUrl] = useState<string | null>(null);
  const [pdfError, setPdfError] = useState<string | null>(null);
  const [numPages, setNumPages] = useState(0);
  const [pageNumber, setPageNumber] = useState(initialPage);
  const [scale, setScale] = useState(1.2);
  const [chatWidth, setChatWidth] = useState(400);
  const [isChatOpen, setIsChatOpen] = useState(true);
  const [activeHighlight, setActiveHighlight] = useState<Highlight | null>(null);
  const [messages, setMessages] = useState<NotebookMessage[]>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [chatError, setChatError] = useState<string | null>(null);
  // Below md the notebook stacks (PDF over chat) and the drag divider is hidden.
  const [isDesktop, setIsDesktop] = useState(true);

  const containerRef = useRef<HTMLDivElement>(null);
  const isDragging = useRef(false);

  useEffect(() => {
    const mediaQuery = window.matchMedia("(min-width: 768px)");
    const update = () => setIsDesktop(mediaQuery.matches);
    update();
    mediaQuery.addEventListener("change", update);
    return () => mediaQuery.removeEventListener("change", update);
  }, []);

  // When the document (or auth) changes, clear the previous load's error and
  // PDF URL during render; the effects below only fetch.
  const loadTarget = useMemo(
    () => (auth.clientSessionId && documentId ? { auth, documentId } : null),
    [auth, documentId],
  );
  useOnChange(loadTarget, (target) => {
    if (target) {
      setDocumentError(null);
      setPdfError(null);
      setPdfUrl(null);
    }
  });

  useEffect(() => {
    if (!auth.clientSessionId || !documentId) return;
    let cancelled = false;
    void getDocument(auth, documentId)
      .then((nextDoc) => {
        if (!cancelled) setDoc(nextDoc);
      })
      .catch((error) => {
        if (!cancelled) {
          setDocumentError(error instanceof Error ? error.message : "Unable to load document.");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [auth, documentId]);

  useEffect(() => {
    if (!auth.clientSessionId || !documentId) return;
    let objectUrl: string | null = null;
    let cancelled = false;
    void getDocumentContent(auth, documentId)
      .then((blob) => {
        if (cancelled) return;
        objectUrl = URL.createObjectURL(blob);
        setPdfUrl(objectUrl);
      })
      .catch((error) => {
        if (!cancelled) {
          setPdfError(error instanceof Error ? error.message : "Unable to load document content.");
        }
      });
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [auth, documentId]);

  const onDocumentLoadSuccess = useCallback(({ numPages: nextNumPages }: { numPages: number }) => {
    setNumPages(nextNumPages);
    setPageNumber((current) => Math.min(current, nextNumPages || 1));
  }, []);

  // Shared width math for mouse and touch drag: chat pane is anchored to the
  // right edge, so the new width is the container width minus the pointer's
  // offset from the container's left edge. Clamped to 300–600px.
  const updateChatWidthFromClientX = useCallback((clientX: number) => {
    if (!containerRef.current) return;
    const containerRect = containerRef.current.getBoundingClientRect();
    const newWidth = containerRect.width - clientX + containerRect.left;
    setChatWidth(Math.max(300, Math.min(600, newWidth)));
  }, []);

  useEffect(() => {
    const handleMouseMove = (event: MouseEvent) => {
      if (!isDragging.current) return;
      updateChatWidthFromClientX(event.clientX);
    };

    const handleMouseUp = () => {
      isDragging.current = false;
    };

    window.document.addEventListener("mousemove", handleMouseMove);
    window.document.addEventListener("mouseup", handleMouseUp);
    return () => {
      window.document.removeEventListener("mousemove", handleMouseMove);
      window.document.removeEventListener("mouseup", handleMouseUp);
    };
  }, [updateChatWidthFromClientX]);

  const handleDividerTouchStart = useCallback(() => {
    isDragging.current = true;
  }, []);

  const handleDividerTouchMove = useCallback(
    (event: React.TouchEvent<HTMLDivElement>) => {
      if (!isDragging.current) return;
      const touch = event.touches[0];
      if (touch) updateChatWidthFromClientX(touch.clientX);
    },
    [updateChatWidthFromClientX]
  );

  const handleDividerTouchEnd = useCallback(() => {
    isDragging.current = false;
  }, []);

  const closeNotebook = () => {
    if (onClose) {
      onClose();
      return;
    }
    window.history.back();
  };

  const changePage = (delta: number) => {
    setPageNumber((prev) => Math.max(1, Math.min(numPages || 1, prev + delta)));
  };

  // ⚡ BOLT OPTIMIZATION:
  // Wrapped goToPage and handleCitationClick in useCallback to ensure referential
  // equality for props passed into the memoized NotebookMessageBubble component.
  const goToPage = useCallback((page: number) => {
    setPageNumber(Math.max(1, Math.min(numPages || page, page)));
  }, [numPages]);

  const handleCitationClick = useCallback((citation: Citation) => {
    if (!citation.page_number) return;
    goToPage(citation.page_number);
    const nextHighlight = {
      page: citation.page_number,
      text: citation.excerpt || "",
    };
    setActiveHighlight(nextHighlight);
    window.setTimeout(() => setActiveHighlight(null), 3000);
  }, [goToPage]);

  const handleSendMessage = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!doc || isLoading) return;
    const content = input.trim();
    if (!content) return;
    if (!settings.providerApiKey.trim()) {
      setChatError("Add your provider API key in Settings before asking notebook questions.");
      return;
    }

    setInput("");
    setChatError(null);
    setIsLoading(true);
    setMessages((current) => [
      ...current,
      {
        id: `user-${Date.now()}`,
        role: "user",
        content,
      },
    ]);

    try {
      const response = await sendChat(
        auth,
        settings.provider,
        settings.chatModel,
        doc.id,
        content,
        conversationId,
        undefined,
        settings.topK,
        settings.similarityThreshold
      );
      setConversationId(response.conversation_id);
      setMessages((current) => [
        ...current,
        {
          id: response.message_id,
          role: "assistant",
          content: response.content,
          citations: response.sources,
        },
      ]);
    } catch (error) {
      setChatError(error instanceof Error ? error.message : "Notebook chat failed.");
      setMessages((current) => [
        ...current,
        {
          id: `assistant-error-${Date.now()}`,
          role: "assistant",
          content: "Sorry, I encountered an error processing your question.",
        },
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div
      ref={containerRef}
      className="fixed inset-0 z-50 flex flex-col md:flex-row"
      style={{ background: "var(--bg-primary)" }}
    >
      <div className="flex h-[60vh] min-h-0 flex-col md:h-auto md:min-w-0 md:flex-1">
        {/* Header: hairline bottom rule, ghost icon controls, data-num readouts. */}
        <div
          className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 px-3 py-2 md:px-4"
          style={{ borderBottom: "1px solid var(--border)", background: "var(--bg-secondary)" }}
        >
          <div className="flex min-w-0 items-center gap-2">
            <GhostIconButton label="Close notebook" onClick={closeNotebook}>
              <X className="h-5 w-5" />
            </GhostIconButton>
            <h2
              className="display max-w-md truncate text-sm font-semibold"
              style={{ color: "var(--text-primary)" }}
            >
              {doc?.filename ?? "Notebook"}
            </h2>
          </div>

          <div className="flex items-center gap-3 md:gap-4">
            <div className="flex items-center gap-1.5">
              <GhostIconButton
                label="Previous page"
                onClick={() => changePage(-1)}
                disabled={pageNumber <= 1}
                compact
              >
                <ChevronLeft className="h-5 w-5" />
              </GhostIconButton>
              <span
                className="text-[10px] uppercase tracking-widest"
                style={{ color: "var(--text-tertiary)" }}
                title={`Page ${pageNumber} of ${numPages || "-"}`}
              >
                page
              </span>
              <span
                className="data-num min-w-12 text-center text-xs"
                style={{ color: "var(--text-secondary)" }}
                title={`Page ${pageNumber} of ${numPages || "-"}`}
              >
                {pageNumber} / {numPages || "–"}
              </span>
              <GhostIconButton
                label="Next page"
                onClick={() => changePage(1)}
                disabled={!numPages || pageNumber >= numPages}
                compact
              >
                <ChevronRight className="h-5 w-5" />
              </GhostIconButton>
            </div>

            <div
              className="flex items-center gap-1 pl-3 md:pl-4"
              style={{ borderLeft: "1px solid var(--border)" }}
            >
              <GhostIconButton
                label="Zoom out"
                onClick={() => setScale((current) => Math.max(0.5, current - 0.1))}
                compact
              >
                <span className="text-sm leading-none">-</span>
              </GhostIconButton>
              <span
                className="data-num min-w-12 text-center text-xs"
                style={{ color: "var(--text-secondary)" }}
              >
                {Math.round(scale * 100)}%
              </span>
              <GhostIconButton
                label="Zoom in"
                onClick={() => setScale((current) => Math.min(2, current + 0.1))}
                compact
              >
                <span className="text-sm leading-none">+</span>
              </GhostIconButton>
            </div>

            <Button
              variant="secondary"
              size="sm"
              onClick={() => setIsChatOpen((current) => !current)}
              aria-expanded={isChatOpen}
            >
              <MessageSquare className="h-3.5 w-3.5" />
              {isChatOpen ? "Hide Chat" : "Show Chat"}
            </Button>
          </div>
        </div>

        {/* PDF canvas: tertiary well, page card carries the hairline chrome. */}
        <div
          className="flex flex-1 justify-center overflow-auto p-4 md:p-8"
          style={{ background: "var(--bg-tertiary)" }}
        >
          {documentError || pdfError ? (
            <div className="flex h-full flex-col items-center justify-center gap-4 text-center">
              <span
                className="inline-flex rounded-lg p-3"
                style={{
                  background: "var(--bg-surface)",
                  border: "1px solid var(--border)",
                  color: "var(--text-muted)",
                }}
              >
                <FileText className="h-8 w-8" />
              </span>
              <ErrorBanner message={documentError || pdfError || "Unable to load document."} />
            </div>
          ) : !pdfUrl ? (
            <div className="flex h-full items-center justify-center">
              <StatusDot tone="processing" label="Loading document" pulse />
            </div>
          ) : (
            <NotebookPdf
              file={pdfUrl}
              onLoadSuccess={onDocumentLoadSuccess}
              onNavigateToPage={goToPage}
              pageNumber={pageNumber}
              scale={scale}
            />
          )}
        </div>
      </div>

      {/* Drag divider: 4px hit area, hairline, brightens on hover; touch supported. */}
      {isChatOpen && (
        <motion.div
          role="separator"
          aria-orientation="vertical"
          aria-label="Resize chat pane"
          onMouseDown={() => {
            isDragging.current = true;
          }}
          onTouchStart={handleDividerTouchStart}
          onTouchMove={handleDividerTouchMove}
          onTouchEnd={handleDividerTouchEnd}
          whileHover={{ backgroundColor: "var(--border-accent)" }}
          transition={transitionFast}
          className="hidden w-1 cursor-col-resize touch-none md:block"
          style={{ background: "var(--border)" }}
        />
      )}

      <AnimatePresence>
        {isChatOpen && (
          <motion.div
            initial={{ width: 0, opacity: 0 }}
            animate={{ width: isDesktop ? chatWidth : "100%", opacity: 1 }}
            exit={{ width: 0, opacity: 0 }}
            transition={transitionNormal}
            className="flex min-h-0 flex-1 flex-col overflow-hidden md:flex-none"
            style={{
              width: isDesktop ? chatWidth : "100%",
              background: "var(--bg-secondary)",
              borderLeft: isDesktop ? "1px solid var(--border)" : undefined,
              borderTop: isDesktop ? undefined : "1px solid var(--border)",
            }}
          >
            <div className="flex h-full min-h-0 flex-col">
              <div
                className="flex items-center justify-between px-4 py-3"
                style={{ borderBottom: "1px solid var(--border)" }}
              >
                <h3
                  className="display flex items-center gap-2 text-sm font-semibold"
                  style={{ color: "var(--text-primary)" }}
                >
                  <MessageSquare
                    className="h-4 w-4"
                    style={{ color: "var(--accent-primary)" }}
                  />
                  Chat with Document
                </h3>
                <GhostIconButton label="Hide chat" onClick={() => setIsChatOpen(false)} compact>
                  <X className="h-4 w-4" />
                </GhostIconButton>
              </div>

              <div className="flex-1 space-y-4 overflow-y-auto p-4">
                {messages.length === 0 ? (
                  <div className="mt-8 text-center" style={{ color: "var(--text-tertiary)" }}>
                    <MessageSquare
                      className="mx-auto mb-3 h-10 w-10"
                      style={{ color: "var(--text-muted)" }}
                    />
                    <p className="text-sm">Ask questions about this document</p>
                    <p className="mt-2 text-xs" style={{ color: "var(--text-muted)" }}>
                      Click citations to jump to the relevant page
                    </p>
                  </div>
                ) : (
                  messages.map((message) => (
                    <NotebookMessageBubble
                      key={message.id}
                      message={message}
                      onCitationClick={handleCitationClick}
                    />
                  ))
                )}
                <AnimatePresence>
                  {activeHighlight && (
                    <motion.div
                      key="citation-highlight"
                      initial={{ opacity: 0, y: 4 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0, y: 4 }}
                      transition={transitionFast}
                      className="flex items-start gap-2 rounded-md p-3 text-xs leading-relaxed"
                      style={{
                        background: "var(--accent-primary-soft)",
                        border: "1px solid var(--border)",
                        color: "var(--text-secondary)",
                      }}
                    >
                      <Highlighter
                        className="mt-0.5 h-3.5 w-3.5 shrink-0"
                        style={{ color: "var(--accent-primary)" }}
                      />
                      <span className="min-w-0 break-words">
                        Page{" "}
                        <span className="data-num" style={{ color: "var(--accent-primary)" }}>
                          {activeHighlight.page}
                        </span>
                        : {activeHighlight.text}
                      </span>
                    </motion.div>
                  )}
                </AnimatePresence>
                {chatError && <ErrorBanner message={chatError} />}
                {isLoading && (
                  <div className="flex justify-start">
                    <div
                      className="rounded-md p-3"
                      style={{
                        background: "var(--bg-surface)",
                        border: "1px solid var(--border)",
                        borderLeft: "2px solid var(--border-hover)",
                      }}
                    >
                      <StatusDot tone="processing" label="Thinking" pulse />
                    </div>
                  </div>
                )}
              </div>

              {/* Input row: hairline rule, lime send action. */}
              <div className="p-3 md:p-4" style={{ borderTop: "1px solid var(--border)" }}>
                <form onSubmit={handleSendMessage} className="flex gap-2">
                  <input
                    value={input}
                    onChange={(event) => setInput(event.target.value)}
                    type="text"
                    placeholder="Ask a question..."
                    aria-label="Ask a question"
                    className="min-w-0 flex-1 px-3 py-2 text-sm outline-none focus-ring"
                    style={{
                      background: "var(--bg-surface)",
                      border: "1px solid var(--border)",
                      borderRadius: "var(--radius-md)",
                      color: "var(--text-primary)",
                    }}
                    disabled={isLoading}
                  />
                  <Button
                    type="submit"
                    variant="primary"
                    aria-label="Send message"
                    title="Send message"
                    disabled={isLoading || !input.trim()}
                  >
                    <Send className="h-4 w-4" />
                  </Button>
                </form>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

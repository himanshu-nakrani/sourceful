"use client";

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
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

const NotebookPdf = dynamic(
  () => import("./NotebookPdf").then((module) => module.NotebookPdf),
  {
    ssr: false,
    loading: () => (
      <div className="flex h-full items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-blue-600" />
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
  return (
    <div className={`flex ${message.role === "user" ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[85%] rounded-lg p-3 ${
          message.role === "user"
            ? "bg-blue-600 text-white"
            : "bg-gray-100 text-gray-900 dark:bg-gray-800 dark:text-white"
        }`}
      >
        <p className="whitespace-pre-wrap text-sm">{message.content}</p>
        {message.citations && message.citations.length > 0 && (
          <div className="mt-2 border-t border-gray-200 pt-2 dark:border-gray-700">
            <p className="mb-1 text-xs text-gray-500 dark:text-gray-400">Sources:</p>
            <div className="flex flex-wrap gap-1">
              {message.citations.map((citation, index) => (
                <button
                  key={citation.chunk_id}
                  type="button"
                  onClick={() => onCitationClick(citation)}
                  className="inline-flex items-center gap-1 rounded-full bg-white px-2 py-0.5 text-xs transition-colors hover:bg-yellow-100 dark:bg-gray-700 dark:hover:bg-yellow-900 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
                  title={citation.excerpt}
                >
                  <Highlighter className="h-3 w-3 text-yellow-600" />
                  {citation.page_number ? `p. ${citation.page_number}` : `[${index + 1}]`}
                </button>
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

  const containerRef = useRef<HTMLDivElement>(null);
  const isDragging = useRef(false);

  useEffect(() => {
    if (!auth.clientSessionId || !documentId) return;
    let cancelled = false;
    setDocumentError(null);
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
    setPdfError(null);
    setPdfUrl(null);
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

  useEffect(() => {
    const handleMouseMove = (event: MouseEvent) => {
      if (!isDragging.current || !containerRef.current) return;
      const containerRect = containerRef.current.getBoundingClientRect();
      const newWidth = containerRect.width - event.clientX + containerRect.left;
      setChatWidth(Math.max(300, Math.min(600, newWidth)));
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
    <div ref={containerRef} className="fixed inset-0 z-50 flex bg-white dark:bg-gray-900">
      <div className="flex min-w-0 flex-1 flex-col">
        <div className="flex items-center justify-between border-b border-gray-200 bg-gray-50 px-4 py-2 dark:border-gray-700 dark:bg-gray-800">
          <div className="flex min-w-0 items-center gap-3">
            <button
              type="button"
              onClick={closeNotebook}
              className="rounded-lg p-2 transition-colors hover:bg-gray-200 dark:hover:bg-gray-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
              aria-label="Close notebook"
              title="Close notebook"
            >
              <X className="h-5 w-5" />
            </button>
            <h2 className="max-w-md truncate font-semibold text-gray-900 dark:text-white">
              {doc?.filename ?? "Notebook"}
            </h2>
          </div>

          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => changePage(-1)}
                disabled={pageNumber <= 1}
                className="rounded p-1.5 hover:bg-gray-200 disabled:opacity-50 dark:hover:bg-gray-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
                aria-label="Previous page"
                title="Previous page"
              >
                <ChevronLeft className="h-5 w-5" />
              </button>
              <span className="text-sm text-gray-600 dark:text-gray-400">
                Page {pageNumber} of {numPages || "-"}
              </span>
              <button
                type="button"
                onClick={() => changePage(1)}
                disabled={!numPages || pageNumber >= numPages}
                className="rounded p-1.5 hover:bg-gray-200 disabled:opacity-50 dark:hover:bg-gray-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
                aria-label="Next page"
                title="Next page"
              >
                <ChevronRight className="h-5 w-5" />
              </button>
            </div>

            <div className="flex items-center gap-1 border-l border-gray-300 pl-4 dark:border-gray-600">
              <button
                type="button"
                onClick={() => setScale((current) => Math.max(0.5, current - 0.1))}
                className="rounded p-1.5 text-sm hover:bg-gray-200 dark:hover:bg-gray-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
                aria-label="Zoom out"
                title="Zoom out"
              >
                -
              </button>
              <span className="min-w-12 text-center text-sm text-gray-600 dark:text-gray-400">
                {Math.round(scale * 100)}%
              </span>
              <button
                type="button"
                onClick={() => setScale((current) => Math.min(2, current + 0.1))}
                className="rounded p-1.5 text-sm hover:bg-gray-200 dark:hover:bg-gray-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
                aria-label="Zoom in"
                title="Zoom in"
              >
                +
              </button>
            </div>

            <button
              type="button"
              onClick={() => setIsChatOpen((current) => !current)}
              aria-expanded={isChatOpen}
              className="flex items-center gap-2 rounded-lg bg-blue-600 px-3 py-1.5 text-white transition-colors hover:bg-blue-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2 dark:focus-visible:ring-offset-gray-800"
            >
              <MessageSquare className="h-4 w-4" />
              <span className="text-sm">{isChatOpen ? "Hide Chat" : "Show Chat"}</span>
            </button>
          </div>
        </div>

        <div className="flex flex-1 justify-center overflow-auto bg-gray-100 p-8 dark:bg-gray-950">
          {documentError || pdfError ? (
            <div className="flex h-full flex-col items-center justify-center text-center text-gray-500">
              <FileText className="mb-4 h-16 w-16" />
              <p>{documentError || pdfError}</p>
            </div>
          ) : !pdfUrl ? (
            <div className="flex h-full items-center justify-center gap-2 text-gray-500">
              <Loader2 className="h-5 w-5 animate-spin" />
              <span>Loading document</span>
            </div>
          ) : (
            <NotebookPdf
              file={pdfUrl}
              onLoadSuccess={onDocumentLoadSuccess}
              pageNumber={pageNumber}
              scale={scale}
            />
          )}
        </div>
      </div>

      {isChatOpen && (
        <div
          onMouseDown={() => {
            isDragging.current = true;
          }}
          className="w-1 cursor-col-resize bg-gray-300 transition-colors hover:bg-blue-500 dark:bg-gray-700"
        />
      )}

      <AnimatePresence>
        {isChatOpen && (
          <motion.div
            initial={{ width: 0, opacity: 0 }}
            animate={{ width: chatWidth, opacity: 1 }}
            exit={{ width: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="flex flex-col border-l border-gray-200 bg-white dark:border-gray-700 dark:bg-gray-900"
            style={{ width: chatWidth }}
          >
            <div className="flex items-center justify-between border-b border-gray-200 px-4 py-3 dark:border-gray-700">
              <h3 className="flex items-center gap-2 font-semibold text-gray-900 dark:text-white">
                <MessageSquare className="h-5 w-5 text-blue-600" />
                Chat with Document
              </h3>
              <button
                type="button"
                onClick={() => setIsChatOpen(false)}
                className="rounded p-1.5 hover:bg-gray-100 dark:hover:bg-gray-800 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
                aria-label="Hide chat"
                title="Hide chat"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <div className="flex-1 space-y-4 overflow-y-auto p-4">
              {messages.length === 0 ? (
                <div className="mt-8 text-center text-gray-500">
                  <MessageSquare className="mx-auto mb-3 h-12 w-12 opacity-50" />
                  <p>Ask questions about this document</p>
                  <p className="mt-2 text-sm">Click citations to jump to the relevant page</p>
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
              {activeHighlight && (
                <div className="rounded-lg border border-yellow-300 bg-yellow-50 p-3 text-xs text-yellow-900">
                  Page {activeHighlight.page}: {activeHighlight.text}
                </div>
              )}
              {chatError && <p className="text-sm text-red-500">{chatError}</p>}
              {isLoading && (
                <div className="flex justify-start">
                  <div className="rounded-lg bg-gray-100 p-3 dark:bg-gray-800">
                    <Loader2 className="h-4 w-4 animate-spin text-blue-600" />
                  </div>
                </div>
              )}
            </div>

            <div className="border-t border-gray-200 p-4 dark:border-gray-700">
              <form onSubmit={handleSendMessage} className="flex gap-2">
                <input
                  value={input}
                  onChange={(event) => setInput(event.target.value)}
                  type="text"
                  placeholder="Ask a question..."
                  aria-label="Ask a question"
                  className="min-w-0 flex-1 rounded-lg border border-gray-300 bg-white px-3 py-2 text-gray-900 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:border-gray-600 dark:bg-gray-800 dark:text-white"
                  disabled={isLoading}
                />
                <button
                  type="submit"
                  disabled={isLoading || !input.trim()}
                  className="inline-flex items-center justify-center rounded-lg bg-blue-600 px-3 py-2 text-white transition-colors hover:bg-blue-700 disabled:opacity-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2 dark:focus-visible:ring-offset-gray-900"
                  aria-label="Send message"
                  title="Send message"
                >
                  <Send className="h-4 w-4" />
                </button>
              </form>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

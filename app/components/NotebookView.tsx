"use client";

import React, { useState, useRef, useCallback, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Document, Page, pdfjs } from "react-pdf";
import "react-pdf/dist/esm/Page/AnnotationLayer.css";
import "react-pdf/dist/esm/Page/TextLayer.css";
import { FileText, MessageSquare, X, ChevronLeft, ChevronRight, Maximize2, Minimize2, Highlighter } from "lucide-react";

// Set PDF.js worker
if (typeof window !== "undefined") {
  pdfjs.GlobalWorkerOptions.workerSrc = `//cdnjs.cloudflare.com/ajax/libs/pdf.js/${pdfjs.version}/pdf.worker.min.js`;
}

import { ChatArea } from "./ChatArea";
import { MessageBubble } from "./MessageBubble";
import type { Document as DocumentType, Citation } from "../lib/api";

interface NotebookViewProps {
  document: DocumentType;
  initialPage?: number;
  onClose?: () => void;
}

interface Highlight {
  page: number;
  text: string;
  color: string;
}

export function NotebookView({ document, initialPage = 1, onClose }: NotebookViewProps) {
  const [numPages, setNumPages] = useState<number>(0);
  const [pageNumber, setPageNumber] = useState<number>(initialPage);
  const [scale, setScale] = useState<number>(1.2);
  const [chatWidth, setChatWidth] = useState<number>(400);
  const [isChatOpen, setIsChatOpen] = useState<boolean>(true);
  const [highlights, setHighlights] = useState<Highlight[]>([]);
  const [activeHighlight, setActiveHighlight] = useState<Highlight | null>(null);
  const [messages, setMessages] = useState<Array<{ role: "user" | "assistant"; content: string; citations?: Citation[] }>>([]);
  const [isLoading, setIsLoading] = useState(false);

  const containerRef = useRef<HTMLDivElement>(null);
  const resizeRef = useRef<HTMLDivElement>(null);
  const isDragging = useRef(false);

  const onDocumentLoadSuccess = useCallback(({ numPages }: { numPages: number }) => {
    setNumPages(numPages);
  }, []);

  // Handle resize drag
  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (!isDragging.current || !containerRef.current) return;
      const containerRect = containerRef.current.getBoundingClientRect();
      const newWidth = containerRect.width - e.clientX + containerRect.left;
      setChatWidth(Math.max(300, Math.min(600, newWidth)));
    };

    const handleMouseUp = () => {
      isDragging.current = false;
    };

    document.addEventListener("mousemove", handleMouseMove);
    document.addEventListener("mouseup", handleMouseUp);
    return () => {
      document.removeEventListener("mousemove", handleMouseMove);
      document.removeEventListener("mouseup", handleMouseUp);
    };
  }, []);

  const handleResizeStart = () => {
    isDragging.current = true;
  };

  const changePage = (delta: number) => {
    setPageNumber((prev) => Math.max(1, Math.min(numPages, prev + delta)));
  };

  const goToPage = (page: number) => {
    setPageNumber(Math.max(1, Math.min(numPages, page)));
  };

  const handleCitationClick = (citation: Citation) => {
    if (citation.page_number) {
      goToPage(citation.page_number);
      // Add temporary highlight
      const newHighlight: Highlight = {
        page: citation.page_number,
        text: citation.excerpt || "",
        color: "#fbbf24",
      };
      setActiveHighlight(newHighlight);
      setTimeout(() => setActiveHighlight(null), 3000);
    }
  };

  const handleSendMessage = async (content: string) => {
    const userMessage = { role: "user" as const, content };
    setMessages((prev) => [...prev, userMessage]);
    setIsLoading(true);

    try {
      const response = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          document_id: document.id,
          question: content,
          provider: "openai",
          model: "gpt-4o-mini",
        }),
      });

      if (!response.ok) throw new Error("Failed to get response");

      const data = await response.json();
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: data.answer,
          citations: data.sources || [],
        },
      ]);
    } catch (error) {
      setMessages((prev) => [
        ...prev,
        {
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
      className="fixed inset-0 z-50 flex bg-white dark:bg-gray-900"
    >
      {/* PDF Viewer Pane */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Toolbar */}
        <div className="flex items-center justify-between px-4 py-2 border-b border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800">
          <div className="flex items-center gap-3">
            <button
              onClick={onClose}
              className="p-2 hover:bg-gray-200 dark:hover:bg-gray-700 rounded-lg transition-colors"
            >
              <X className="w-5 h-5" />
            </button>
            <h2 className="font-semibold text-gray-900 dark:text-white truncate max-w-md">
              {document.filename}
            </h2>
          </div>

          <div className="flex items-center gap-4">
            {/* Page navigation */}
            <div className="flex items-center gap-2">
              <button
                onClick={() => changePage(-1)}
                disabled={pageNumber <= 1}
                className="p-1.5 hover:bg-gray-200 dark:hover:bg-gray-700 rounded disabled:opacity-50"
              >
                <ChevronLeft className="w-5 h-5" />
              </button>
              <span className="text-sm text-gray-600 dark:text-gray-400">
                Page {pageNumber} of {numPages}
              </span>
              <button
                onClick={() => changePage(1)}
                disabled={pageNumber >= numPages}
                className="p-1.5 hover:bg-gray-200 dark:hover:bg-gray-700 rounded disabled:opacity-50"
              >
                <ChevronRight className="w-5 h-5" />
              </button>
            </div>

            {/* Zoom controls */}
            <div className="flex items-center gap-1 border-l border-gray-300 dark:border-gray-600 pl-4">
              <button
                onClick={() => setScale((s) => Math.max(0.5, s - 0.1))}
                className="p-1.5 hover:bg-gray-200 dark:hover:bg-gray-700 rounded text-sm"
              >
                -
              </button>
              <span className="text-sm text-gray-600 dark:text-gray-400 min-w-[3rem] text-center">
                {Math.round(scale * 100)}%
              </span>
              <button
                onClick={() => setScale((s) => Math.min(2, s + 0.1))}
                className="p-1.5 hover:bg-gray-200 dark:hover:bg-gray-700 rounded text-sm"
              >
                +
              </button>
            </div>

            {/* Toggle chat */}
            <button
              onClick={() => setIsChatOpen(!isChatOpen)}
              className="flex items-center gap-2 px-3 py-1.5 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
            >
              <MessageSquare className="w-4 h-4" />
              <span className="text-sm">{isChatOpen ? "Hide Chat" : "Show Chat"}</span>
            </button>
          </div>
        </div>

        {/* PDF Content */}
        <div className="flex-1 overflow-auto bg-gray-100 dark:bg-gray-950 flex justify-center p-8">
          <Document
            file={`/api/documents/${document.id}/content`}
            onLoadSuccess={onDocumentLoadSuccess}
            loading={
              <div className="flex items-center justify-center h-full">
                <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600" />
              </div>
            }
            error={
              <div className="flex flex-col items-center justify-center h-full text-gray-500">
                <FileText className="w-16 h-16 mb-4" />
                <p>Failed to load PDF</p>
              </div>
            }
          >
            <Page
              pageNumber={pageNumber}
              scale={scale}
              renderTextLayer
              renderAnnotationLayer
              className="shadow-xl"
            />
          </Document>
        </div>
      </div>

      {/* Resize Handle */}
      {isChatOpen && (
        <div
          ref={resizeRef}
          onMouseDown={handleResizeStart}
          className="w-1 cursor-col-resize bg-gray-300 dark:bg-gray-700 hover:bg-blue-500 transition-colors"
        />
      )}

      {/* Chat Pane */}
      <AnimatePresence>
        {isChatOpen && (
          <motion.div
            initial={{ width: 0, opacity: 0 }}
            animate={{ width: chatWidth, opacity: 1 }}
            exit={{ width: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="flex flex-col bg-white dark:bg-gray-900 border-l border-gray-200 dark:border-gray-700"
            style={{ width: chatWidth }}
          >
            {/* Chat Header */}
            <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200 dark:border-gray-700">
              <h3 className="font-semibold text-gray-900 dark:text-white flex items-center gap-2">
                <MessageSquare className="w-5 h-5 text-blue-600" />
                Chat with Document
              </h3>
              <button
                onClick={() => setIsChatOpen(false)}
                className="p-1.5 hover:bg-gray-100 dark:hover:bg-gray-800 rounded"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Messages */}
            <div className="flex-1 overflow-y-auto p-4 space-y-4">
              {messages.length === 0 ? (
                <div className="text-center text-gray-500 mt-8">
                  <MessageSquare className="w-12 h-12 mx-auto mb-3 opacity-50" />
                  <p>Ask questions about this document</p>
                  <p className="text-sm mt-2">
                    Click on citations to jump to the relevant page
                  </p>
                </div>
              ) : (
                messages.map((msg, idx) => (
                  <div
                    key={idx}
                    className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
                  >
                    <div
                      className={`max-w-[85%] rounded-lg p-3 ${
                        msg.role === "user"
                          ? "bg-blue-600 text-white"
                          : "bg-gray-100 dark:bg-gray-800 text-gray-900 dark:text-white"
                      }`}
                    >
                      <p className="text-sm whitespace-pre-wrap">{msg.content}</p>
                      {msg.citations && msg.citations.length > 0 && (
                        <div className="mt-2 pt-2 border-t border-gray-200 dark:border-gray-700">
                          <p className="text-xs text-gray-500 dark:text-gray-400 mb-1">
                            Sources:
                          </p>
                          <div className="flex flex-wrap gap-1">
                            {msg.citations.map((citation, cidx) => (
                              <button
                                key={cidx}
                                onClick={() => handleCitationClick(citation)}
                                className="inline-flex items-center gap-1 px-2 py-0.5 text-xs bg-white dark:bg-gray-700 rounded-full hover:bg-yellow-100 dark:hover:bg-yellow-900 transition-colors"
                              >
                                <Highlighter className="w-3 h-3 text-yellow-600" />
                                {citation.page_number ? `p. ${citation.page_number}` : `[${cidx + 1}]`}
                              </button>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                ))
              )}
              {isLoading && (
                <div className="flex justify-start">
                  <div className="bg-gray-100 dark:bg-gray-800 rounded-lg p-3">
                    <div className="flex items-center gap-2">
                      <div className="w-2 h-2 bg-blue-600 rounded-full animate-bounce" />
                      <div className="w-2 h-2 bg-blue-600 rounded-full animate-bounce delay-100" />
                      <div className="w-2 h-2 bg-blue-600 rounded-full animate-bounce delay-200" />
                    </div>
                  </div>
                </div>
              )}
            </div>

            {/* Input */}
            <div className="p-4 border-t border-gray-200 dark:border-gray-700">
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  const input = e.currentTarget.elements.namedItem("message") as HTMLInputElement;
                  if (input.value.trim()) {
                    handleSendMessage(input.value);
                    input.value = "";
                  }
                }}
                className="flex gap-2"
              >
                <input
                  name="message"
                  type="text"
                  placeholder="Ask a question..."
                  className="flex-1 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
                <button
                  type="submit"
                  className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
                >
                  Send
                </button>
              </form>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

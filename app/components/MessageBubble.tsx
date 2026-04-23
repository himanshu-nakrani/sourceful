"use client";

import React from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneDark } from "react-syntax-highlighter/dist/esm/styles/prism";
import { motion } from "framer-motion";
import { Bot, Check, Copy, RefreshCcw, ThumbsDown, ThumbsUp, User } from "lucide-react";
import type { Citation, Message } from "../lib/api";

export type MessageFeedbackState = "idle" | "up" | "down" | "pending" | "error";

function getConfidenceRailClass(sources: Citation[] | undefined): string {
  if (!sources || sources.length === 0) return "";
  const avg = sources.reduce((s, c) => s + c.score, 0) / sources.length;
  if (avg >= 0.75) return "confidence-high-rail";
  if (avg >= 0.45) return "confidence-med-rail";
  return "confidence-low-rail";
}

interface MessageBubbleProps {
  message: Message;
  onRerun?: (message: Message) => void;
  rerunDisabled?: boolean;
  /** When false but the assistant message is empty, show a placeholder instead of infinite typing dots. */
  isStreaming?: boolean;
  /** Called when the user clicks thumbs-up / thumbs-down. Omitting disables the UI. */
  onFeedback?: (message: Message, rating: "up" | "down") => void;
  feedbackState?: MessageFeedbackState;
}

// Match inline citation markers like [1], [ 2 ], or ranges like [1,3,5].
// We replace them with hoverable pill badges that reveal the underlying
// excerpt and page reference.
const CITATION_RE = /\[(\d+(?:\s*,\s*\d+)*)\]/g;

function renderWithInlineCitations(text: string, sources: Citation[]): React.ReactNode[] {
  if (!sources?.length || !text) return [text];
  const nodes: React.ReactNode[] = [];
  let lastIndex = 0;
  let match: RegExpExecArray | null;
  CITATION_RE.lastIndex = 0;
  while ((match = CITATION_RE.exec(text))) {
    const start = match.index;
    if (start > lastIndex) nodes.push(text.slice(lastIndex, start));
    const indices = match[1]
      .split(",")
      .map((part) => Number.parseInt(part.trim(), 10))
      .filter((n) => Number.isFinite(n));
    nodes.push(
      <CitationPills key={`cite-${start}`} indices={indices} sources={sources} />
    );
    lastIndex = start + match[0].length;
  }
  if (lastIndex < text.length) nodes.push(text.slice(lastIndex));
  return nodes;
}

function rewriteCitations(children: React.ReactNode, sources: Citation[]): React.ReactNode {
  if (!sources?.length) return children;
  return React.Children.map(children, (child) => {
    if (typeof child === "string") {
      return renderWithInlineCitations(child, sources);
    }
    return child;
  });
}

function CitationPills({
  indices,
  sources,
}: {
  indices: number[];
  sources: Citation[];
}) {
  return (
    <>
      {indices.map((raw, idx) => {
        // Accept both 1-indexed ([1] == sources[0]) and 0-indexed callers.
        const oneIdx = raw - 1;
        const source = sources[oneIdx] ?? sources[raw] ?? null;
        const label = raw;
        const title = source
          ? `[${label}] ${source.page_number ? `p${source.page_number} · ` : ""}${source.excerpt}`
          : `[${label}] (source not found)`;
        return (
          <span
            key={`${label}-${idx}`}
            title={title}
            className="inline-flex items-center align-baseline text-[11px] font-semibold mx-0.5 px-2 py-0.5 rounded-full cursor-help transition-colors"
            style={{
              background: source ? "var(--accent-brand-soft)" : "var(--bg-surface)",
              color: source ? "var(--accent-brand)" : "var(--text-muted)",
              border: `1px solid ${source ? "var(--accent-brand)" : "var(--border)"}`,
              cursor: source ? "help" : "default",
              verticalAlign: "baseline",
              lineHeight: 1.4,
            }}
          >
            {label}
          </span>
        );
      })}
    </>
  );
}

// ⚡ BOLT OPTIMIZATION:
// Wrapped MessageBubble in React.memo to prevent expensive ReactMarkdown and
// SyntaxHighlighter re-renders for all previous messages in the chat history
// during rapid state updates from token streaming.
const MessageBubble = React.memo(function MessageBubble({
  message,
  onRerun,
  rerunDisabled = false,
  isStreaming = false,
  onFeedback,
  feedbackState = "idle",
}: MessageBubbleProps) {
  const isUser = message.role === "user";
  const canShowFeedback =
    !isUser && !isStreaming && Boolean(onFeedback) && Boolean(message.content);
  const feedbackPending = feedbackState === "pending";
  const feedbackRecorded = feedbackState === "up" || feedbackState === "down";

  return (
    <div
      className="flex gap-3"
      style={{ justifyContent: isUser ? "flex-end" : "flex-start", maxWidth: "100%" }}
    >
      {!isUser ? (
        <div className="flex-shrink-0 flex items-start pt-1">
          <div
            className="flex items-center justify-center rounded-xl"
            style={{
              width: 30,
              height: 30,
              background: "var(--accent-brand-soft)",
              border: "1px solid var(--border)",
            }}
          >
            <Bot size={14} style={{ color: "var(--accent-brand)" }} />
          </div>
        </div>
      ) : null}

      <div
        className={`rounded-2xl px-4 py-3${
          !isUser && message.sources?.length && !isStreaming
            ? " " + getConfidenceRailClass(message.sources)
            : ""
        }`}
        style={{
          maxWidth: isUser ? "75%" : "85%",
          background: isUser ? "var(--accent)" : "var(--bg-surface)",
          border: isUser ? "none" : "1px solid var(--border)",
          color: isUser ? "var(--accent-fg)" : "var(--text-primary)",
          borderTopRightRadius: isUser ? 6 : undefined,
          borderTopLeftRadius: !isUser ? 6 : undefined,
        }}
      >
        {isUser ? (
          <div className="flex flex-col gap-2">
            <p className="text-sm leading-relaxed whitespace-pre-wrap">{message.content}</p>
            {onRerun ? (
              <div className="flex justify-end">
                <motion.button
                  type="button"
                  onClick={() => onRerun(message)}
                  disabled={rerunDisabled}
                  aria-label="Rerun this message"
                  className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-xs"
                  style={{
                    background: "rgba(9, 9, 11, 0.16)",
                    color: "var(--accent-fg)",
                    opacity: rerunDisabled ? 0.55 : 1,
                  }}
                  whileTap={{ scale: 0.92 }}
                >
                  <RefreshCcw size={10} />
                  Rerun
                </motion.button>
              </div>
            ) : null}
          </div>
        ) : (
          <div className="markdown-body">
            {!message.content ? (
              isStreaming ? (
                <TypingIndicator />
              ) : (
                <p className="text-sm leading-relaxed" style={{ color: "var(--text-muted)" }}>
                  No response received.
                </p>
              )
            ) : (
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={{
                  code({ className, children, ...props }) {
                    const match = /language-(\w+)/.exec(className || "");
                    const code = String(children).replace(/\n$/, "");
                    if (match) {
                      return <CodeBlock language={match[1]} code={code} />;
                    }
                    return (
                      <code className={className} {...props}>
                        {children}
                      </code>
                    );
                  },
                  // Rewrite plain text nodes so `[n]` markers become
                  // hoverable citation pills that link to the retrieved
                  // source. Preserves markdown formatting around them.
                  p({ children, ...props }) {
                    return (
                      <p {...props}>
                        {rewriteCitations(children, message.sources ?? [])}
                      </p>
                    );
                  },
                  li({ children, ...props }) {
                    return (
                      <li {...props}>
                        {rewriteCitations(children, message.sources ?? [])}
                      </li>
                    );
                  },
                }}
              >
                {message.content}
              </ReactMarkdown>
            )}
            {canShowFeedback ? (
              <FeedbackControls
                message={message}
                state={feedbackState}
                pending={feedbackPending}
                recorded={feedbackRecorded}
                onFeedback={onFeedback!}
              />
            ) : null}
          </div>
        )}
      </div>

      {isUser ? (
        <div className="flex-shrink-0 flex items-start pt-1">
          <div
            className="flex items-center justify-center rounded-xl"
            style={{
              width: 30,
              height: 30,
              background: "var(--bg-surface)",
              border: "1px solid var(--border)",
            }}
          >
            <User size={14} style={{ color: "var(--text-tertiary)" }} />
          </div>
        </div>
      ) : null}
    </div>
  );
});
export default MessageBubble;

function CodeBlock({ language, code }: { language: string; code: string }) {
  const [copied, setCopied] = React.useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  };

  return (
    <div className="relative group" style={{ margin: "0.75rem 0" }}>
      <div
        className="flex items-center justify-between px-3 py-1.5 rounded-t-xl"
        style={{
          background: "var(--bg-elevated)",
          borderBottom: "1px solid var(--border)",
          fontSize: "0.65rem",
          color: "var(--text-muted)",
          fontFamily: "var(--font-mono)",
          letterSpacing: "0.04em",
          textTransform: "uppercase",
        }}
      >
        <span>{language}</span>
        {/* [a11y] Added aria-label — icon-only button needs accessible name */}
        <motion.button
          type="button"
          onClick={handleCopy}
          className="flex items-center gap-1 transition-colors"
          style={{ color: copied ? "var(--success)" : "var(--text-muted)" }}
          aria-label={copied ? "Code copied" : "Copy code to clipboard"}
          whileTap={{ scale: 0.9 }}
        >
          {copied ? <Check size={11} /> : <Copy size={11} />}
          {copied ? "Copied" : "Copy"}
        </motion.button>
      </div>
      <SyntaxHighlighter
        language={language}
        style={oneDark}
        customStyle={{
          margin: 0,
          borderRadius: "0 0 var(--radius-md) var(--radius-md)",
          background: "var(--bg-primary)",
          fontSize: "0.8125rem",
          border: "1px solid var(--border)",
          borderTop: "none",
        }}
      >
        {code}
      </SyntaxHighlighter>
    </div>
  );
}
function FeedbackControls({
  message,
  state,
  pending,
  recorded,
  onFeedback,
}: {
  message: Message;
  state: MessageFeedbackState;
  pending: boolean;
  recorded: boolean;
  onFeedback: (message: Message, rating: "up" | "down") => void;
}) {
  const up = state === "up";
  const down = state === "down";
  const label = pending
    ? "Saving feedback…"
    : up
    ? "Thanks — recorded."
    : down
    ? "Thanks — recorded."
    : state === "error"
    ? "Couldn't save feedback."
    : null;
  return (
    <div
      className="flex items-center gap-2 pt-3 mt-3"
      style={{
        borderTop: "1px dashed var(--border)",
        color: "var(--text-muted)",
      }}
    >
      <span className="text-[11px]">Was this helpful?</span>
      <motion.button
        type="button"
        aria-label="Thumbs up"
        disabled={pending || recorded}
        onClick={() => onFeedback(message, "up")}
        whileTap={{ scale: 0.9 }}
        className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-[11px]"
        style={{
          background: up ? "var(--accent-brand-soft)" : "transparent",
          color: up ? "var(--accent-brand)" : "var(--text-muted)",
          border: "1px solid var(--border)",
          cursor: pending || recorded ? "default" : "pointer",
          opacity: pending ? 0.6 : 1,
        }}
      >
        <ThumbsUp size={11} />
      </motion.button>
      <motion.button
        type="button"
        aria-label="Thumbs down"
        disabled={pending || recorded}
        onClick={() => onFeedback(message, "down")}
        whileTap={{ scale: 0.9 }}
        className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-[11px]"
        style={{
          background: down ? "var(--error-soft)" : "transparent",
          color: down ? "var(--error)" : "var(--text-muted)",
          border: "1px solid var(--border)",
          cursor: pending || recorded ? "default" : "pointer",
          opacity: pending ? 0.6 : 1,
        }}
      >
        <ThumbsDown size={11} />
      </motion.button>
      {label ? <span className="text-[11px]">{label}</span> : null}
    </div>
  );
}

function TypingIndicator() {
  return (
    <div className="flex gap-1.5 items-center py-1">
      {[0, 0.15, 0.3].map((delay, i) => (
        <motion.div
          key={i}
          className="w-1.5 h-1.5 rounded-full"
          style={{ background: "var(--accent-brand)" }}
          animate={{ opacity: [0.3, 1, 0.3], scale: [0.8, 1.1, 0.8] }}
          transition={{ duration: 1, repeat: Infinity, delay, ease: "easeInOut" }}
        />
      ))}
    </div>
  );
}

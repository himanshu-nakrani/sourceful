"use client";

import React from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneDark } from "react-syntax-highlighter/dist/esm/styles/prism";
import { motion } from "framer-motion";
import { Check, Copy, RefreshCcw, ThumbsDown, ThumbsUp, Scale, FileText, ListTree } from "lucide-react";
import type { Citation, Message } from "../lib/api";
import { CitationPreview } from "./CitationPreview";

export type MessageFeedbackState = "idle" | "up" | "down" | "pending" | "error";

interface MessageBubbleProps {
  message: Message;
  onCitationSelect?: (citation: Citation, sources: Citation[]) => void;
  onRerun?: (message: Message) => void;
  rerunDisabled?: boolean;
  /** When false but the assistant message is empty, show a placeholder instead of infinite typing dots. */
  isStreaming?: boolean;
  /** Called when the user clicks thumbs-up / thumbs-down. Omitting disables the UI. */
  onFeedback?: (message: Message, rating: "up" | "down") => void;
  feedbackState?: MessageFeedbackState;
}

// Match inline citation markers like [1], [ 2 ], or ranges like [1,3,5].
// We replace them with hoverable superscript chips that reveal the underlying
// excerpt and page reference.
const CITATION_RE = /\[(\d+(?:\s*,\s*\d+)*)\]/g;

function renderWithInlineCitations(text: string, sources: Citation[], onSelect?: (citation: Citation) => void): React.ReactNode[] {
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
      <CitationPills key={`cite-${start}`} indices={indices} sources={sources} onSelect={onSelect} />
    );
    lastIndex = start + match[0].length;
  }
  if (lastIndex < text.length) nodes.push(text.slice(lastIndex, text.length));
  return nodes;
}

function rewriteCitations(children: React.ReactNode, sources: Citation[], onSelect?: (citation: Citation) => void): React.ReactNode {
  if (!sources?.length) return children;
  return React.Children.map(children, (child) => {
    if (typeof child === "string") {
      return renderWithInlineCitations(child, sources, onSelect);
    }
    return child;
  });
}

function CitationPills({
  indices,
  sources,
  onSelect,
}: {
  indices: number[];
  sources: Citation[];
  onSelect?: (citation: Citation) => void;
}) {
  return (
    <>
      {indices.map((raw, idx) => {
        // Accept both 1-indexed ([1] == sources[0]) and 0-indexed callers.
        const oneIdx = raw - 1;
        const source = sources[oneIdx] ?? sources[raw] ?? null;
        const label = raw;
        if (!source) {
          return (
            <span
              key={`${label}-${idx}`}
              className="data-num inline-flex items-center mx-[2px] px-1 text-xs leading-none"
              style={{
                borderRadius: "var(--radius-xs)",
                color: "var(--text-muted)",
                border: "1px solid var(--border)",
                verticalAlign: "super",
                lineHeight: 1.4,
              }}
            >
              [{label}]
            </span>
          );
        }
        const sourceLabel = `Source ${label}${source.page_number ? `, page ${source.page_number}` : ""}`;
        const chipClass = "data-num mx-0.5 inline-flex cursor-pointer items-center rounded-sm border border-transparent bg-[var(--accent-primary-soft)] px-1.5 py-0.5 align-baseline text-[10px] leading-none text-[var(--accent-primary)] focus-ring hover:border-[var(--accent-primary)]";
        return (
          <CitationPreview key={`${label}-${idx}`} citation={source}>
            {onSelect ? (
              <button type="button" className={chipClass} aria-label={`Inspect ${sourceLabel.toLowerCase()}`} onClick={() => onSelect(source)}>[{label}]</button>
            ) : (
              <span className={chipClass} tabIndex={0} aria-label={sourceLabel}>[{label}]</span>
            )}
          </CitationPreview>
        );
      })}
    </>
  );
}

/** Keep the grounding cue close to the answer without surfacing retrieval scores. */
function ProvenanceSummary({ sources }: { sources: Citation[] }) {
  if (!sources.length) return null;
  const avg = sources.reduce((sum, source) => sum + source.score, 0) / sources.length;
  return (
    <div
      className="mt-3 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs"
      role="note"
    >
      <FileText size={13} aria-hidden="true" style={{ color: "var(--accent-primary)" }} />
      <span style={{ color: "var(--text-tertiary)" }}>
        Based on {sources.length} source {sources.length === 1 ? "passage" : "passages"}.
      </span>
      {avg < 0.45 ? (
        <span style={{ color: "var(--warning)" }}>Some matches may be less relevant.</span>
      ) : null}
    </div>
  );
}

// Streaming optimization:
// Wrapped MessageBubble in React.memo to prevent expensive ReactMarkdown and
// SyntaxHighlighter re-renders for all previous messages in the chat history
// during rapid state updates from token streaming.
const MessageBubble = React.memo(function MessageBubble({
  message,
  onCitationSelect,
  onRerun,
  rerunDisabled = false,
  isStreaming = false,
  onFeedback,
  feedbackState = "idle",
}: MessageBubbleProps) {
  const isUser = message.role === "user";
  const [copyState, setCopyState] = React.useState<"idle" | "copied" | "error">("idle");
  React.useEffect(() => {
    if (copyState !== "copied") return;
    const timer = window.setTimeout(() => setCopyState("idle"), 2000);
    return () => window.clearTimeout(timer);
  }, [copyState]);
  const copyAnswer = async () => {
    try {
      await navigator.clipboard.writeText(message.content);
      setCopyState("copied");
    } catch {
      setCopyState("error");
    }
  };
  const canShowFeedback =
    !isUser && !isStreaming && Boolean(onFeedback) && Boolean(message.content);
  const feedbackPending = feedbackState === "pending";
  const feedbackRecorded = feedbackState === "up" || feedbackState === "down";

  const mode = message.mode;
  const modeLabel = mode ? mode.charAt(0).toUpperCase() + mode.slice(1) : "";
  const modeBadge = !isUser && mode && mode !== "ask" ? (
    <span
      className="inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-xs font-medium mb-3"
      style={{
        background:
          mode === "compare"
            ? "var(--warning-soft)"
            : mode === "extract"
              ? "var(--success-soft)"
              : "var(--accent-secondary-soft)",
        color:
          mode === "compare"
            ? "var(--warning)"
            : mode === "extract"
              ? "var(--success)"
              : "var(--accent-secondary)",
        border: "1px solid var(--border)",
      }}
    >
      {mode === "compare" && <Scale size={12} aria-hidden="true" />}
      {mode === "extract" && <FileText size={12} aria-hidden="true" />}
      {mode === "brief" && <ListTree size={12} aria-hidden="true" />}
      {modeLabel}
    </span>
  ) : null;

  return (
    <article className={`group/message w-full min-w-0 ${isUser ? "pt-1" : ""}`}>
      <div className="mb-4 flex items-center gap-3">
        <span className="index-label" style={{ color: isUser ? "var(--text-muted)" : "var(--accent-primary)" }}>{isUser ? "Question" : "Answer"}</span>
        <span className="h-px flex-1" aria-hidden="true" style={{ background: "var(--border)" }} />
        {isUser && onRerun ? (
          <button type="button" onClick={() => onRerun(message)} disabled={rerunDisabled} aria-label="Rerun this message" title="Ask this question again" className="focus-ring inline-flex items-center gap-1.5 rounded-sm px-1 py-1 text-[11px] transition-opacity disabled:opacity-40 md:opacity-0 md:group-hover/message:opacity-100 md:group-focus-within/message:opacity-100" style={{ color: "var(--text-tertiary)" }}><RefreshCcw size={12} />Ask again</button>
        ) : null}
      </div>
      <div style={{ color: "var(--text-primary)" }}>
        {isUser ? (
          <div className="flex flex-col gap-2">
            <p className="editorial-heading whitespace-pre-wrap text-[28px] leading-[1.25] sm:text-[32px]">{message.content}</p>

          </div>
        ) : (
          <div className="markdown-body">
            {modeBadge}
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
                        {rewriteCitations(children, message.sources ?? [], onCitationSelect ? (citation) => onCitationSelect(citation, message.sources ?? []) : undefined)}
                      </p>
                    );
                  },
                  li({ children, ...props }) {
                    return (
                      <li {...props}>
                        {rewriteCitations(children, message.sources ?? [], onCitationSelect ? (citation) => onCitationSelect(citation, message.sources ?? []) : undefined)}
                      </li>
                    );
                  },
                }}
              >
                {message.content}
              </ReactMarkdown>
            )}
            {message.sources?.length ? <ProvenanceSummary sources={message.sources} /> : null}
            {!isStreaming && message.content ? (
              <div className="mt-3 flex flex-wrap items-center gap-3">
                <button type="button" onClick={copyAnswer} className="focus-ring inline-flex items-center gap-1.5 rounded-sm px-1 py-1 text-[11px]" style={{ color: "var(--text-tertiary)" }} aria-label="Copy answer">
                  {copyState === "copied" ? <Check size={13} /> : <Copy size={13} />}
                  {copyState === "copied" ? "Copied" : "Copy answer"}
                </button>
                <span role="status" className="sr-only">{copyState === "copied" ? "Answer copied to clipboard." : ""}</span>
                {copyState === "error" ? <span className="text-xs" role="alert" style={{ color: "var(--error)" }}>Couldn’t copy. Select the text to copy it.</span> : null}
                {canShowFeedback ? (
                  <FeedbackControls message={message} pending={feedbackPending} recorded={feedbackRecorded} state={feedbackState} onFeedback={onFeedback!} />
                ) : null}
              </div>
            ) : null}
          </div>
        )}
      </div>

    </article>
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
        className="flex items-center justify-between px-3 py-1.5"
        style={{
          background: "var(--bg-secondary)",
          borderBottom: "1px solid var(--border)",
          borderTopLeftRadius: "var(--radius-md)",
          borderTopRightRadius: "var(--radius-md)",
        }}
      >
        <span className="data-num text-xs font-medium" style={{ color: "var(--text-tertiary)" }}>
          {language}
        </span>
        {/* [a11y] Added aria-label — icon-only button needs accessible name */}
        <motion.button
          type="button"
          onClick={handleCopy}
          className="flex items-center gap-1.5 rounded-md px-2 py-1 text-xs font-medium transition-colors focus-ring"
          style={{
            color: copied ? "var(--success)" : "var(--text-muted)",
            background: "transparent",
            border: "1px solid var(--border)",
          }}
          aria-label={copied ? "Code copied" : "Copy code to clipboard"}
          title={copied ? "Code copied" : "Copy code to clipboard"}
          whileTap={{ scale: 0.9 }}
        >
          {copied ? <Check size={12} aria-hidden="true" /> : <Copy size={12} aria-hidden="true" />}
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
      className="flex items-center gap-1.5"
      style={{ color: "var(--text-muted)" }}
    >
      <span className="hidden text-[11px] sm:inline" style={{ color: "var(--text-tertiary)" }}>
        Was this helpful?
      </span>
      <motion.button
        type="button"
        aria-label="Thumbs up"
        title="Thumbs up"
        aria-pressed={up}
        disabled={pending || recorded}
        onClick={() => onFeedback(message, "up")}
        whileHover={{ background: up ? "var(--success-soft)" : "var(--bg-tertiary)" }}
        whileTap={{ scale: 0.9 }}
        className="inline-flex h-8 w-8 items-center justify-center rounded-full transition-colors focus-ring"
        style={{
          background: up ? "var(--success-soft)" : "transparent",
          color: up ? "var(--success)" : "var(--text-muted)",
          border: "1px solid transparent",
          cursor: pending || recorded ? "default" : "pointer",
          opacity: pending ? 0.6 : 1,
        }}
      >
        <ThumbsUp size={14} aria-hidden="true" />
      </motion.button>
      <motion.button
        type="button"
        aria-label="Thumbs down"
        title="Thumbs down"
        aria-pressed={down}
        disabled={pending || recorded}
        onClick={() => onFeedback(message, "down")}
        whileHover={{ background: down ? "var(--error-soft)" : "var(--bg-tertiary)" }}
        whileTap={{ scale: 0.9 }}
        className="inline-flex h-8 w-8 items-center justify-center rounded-full transition-colors focus-ring"
        style={{
          background: down ? "var(--error-soft)" : "transparent",
          color: down ? "var(--error)" : "var(--text-muted)",
          border: "1px solid transparent",
          cursor: pending || recorded ? "default" : "pointer",
          opacity: pending ? 0.6 : 1,
        }}
      >
        <ThumbsDown size={14} aria-hidden="true" />
      </motion.button>
      {label ? (
        <span
          className="text-xs"
          style={{ color: state === "error" ? "var(--error)" : "var(--text-tertiary)" }}
          role={state === "error" ? "alert" : "status"}
          aria-live={state === "error" ? "assertive" : "polite"}
          aria-atomic="true"
        >
          {label}
        </span>
      ) : null}
    </div>
  );
}

function TypingIndicator() {
  return (
    <div className="flex gap-1.5 items-center py-1" role="status" aria-label="Assistant is responding">
      {[0, 0.15, 0.3].map((delay, i) => (
        <motion.div
          key={i}
          className="w-1.5 h-1.5 rounded-full"
          style={{ background: "var(--accent-secondary)" }}
          aria-hidden="true"
          animate={{ opacity: [0.3, 1, 0.3], scale: [0.8, 1.1, 0.8] }}
          transition={{ duration: 1, repeat: Infinity, delay, ease: "easeInOut" }}
        />
      ))}
    </div>
  );
}

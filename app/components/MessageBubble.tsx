"use client";

import React from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneDark } from "react-syntax-highlighter/dist/esm/styles/prism";
import { Bot, Check, Copy, User } from "lucide-react";
import type { Message } from "../lib/api";

interface MessageBubbleProps {
  message: Message;
}

export default function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === "user";

  return (
    <div
      className="flex gap-3 animate-fade-in"
      style={{ justifyContent: isUser ? "flex-end" : "flex-start", maxWidth: "100%" }}
    >
      {!isUser ? (
        <div className="flex-shrink-0 flex items-start pt-1">
          <div
            className="flex items-center justify-center rounded-lg"
            style={{
              width: 32,
              height: 32,
              background: "var(--accent-soft)",
              border: "1px solid var(--border-accent)",
            }}
          >
            <Bot size={16} style={{ color: "var(--accent)" }} />
          </div>
        </div>
      ) : null}

      <div
        className="rounded-2xl px-4 py-3"
        style={{
          maxWidth: isUser ? "75%" : "85%",
          background: isUser ? "var(--accent)" : "var(--bg-surface)",
          border: isUser ? "none" : "1px solid var(--border)",
          color: isUser ? "var(--accent-fg)" : "var(--text-primary)",
          borderTopRightRadius: isUser ? 4 : undefined,
          borderTopLeftRadius: !isUser ? 4 : undefined,
        }}
      >
        {isUser ? (
          <p className="text-sm leading-relaxed whitespace-pre-wrap">{message.content}</p>
        ) : (
          <div className="markdown-body">
            {!message.content ? (
              <TypingIndicator />
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
                }}
              >
                {message.content}
              </ReactMarkdown>
            )}
          </div>
        )}
      </div>

      {isUser ? (
        <div className="flex-shrink-0 flex items-start pt-1">
          <div
            className="flex items-center justify-center rounded-lg"
            style={{
              width: 32,
              height: 32,
              background: "var(--bg-surface)",
              border: "1px solid var(--border)",
            }}
          >
            <User size={16} style={{ color: "var(--text-secondary)" }} />
          </div>
        </div>
      ) : null}
    </div>
  );
}

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
        className="flex items-center justify-between px-3 py-1.5 rounded-t-lg"
        style={{
          background: "var(--bg-elevated)",
          borderBottom: "1px solid var(--border)",
          fontSize: "0.7rem",
          color: "var(--text-tertiary)",
          fontFamily: "var(--font-mono)",
        }}
      >
        <span>{language}</span>
        <button
          type="button"
          onClick={handleCopy}
          className="flex items-center gap-1 transition-colors"
          style={{ color: copied ? "var(--success)" : "var(--text-tertiary)" }}
        >
          {copied ? <Check size={12} /> : <Copy size={12} />}
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <SyntaxHighlighter
        language={language}
        style={oneDark}
        customStyle={{
          margin: 0,
          borderRadius: "0 0 var(--radius-sm) var(--radius-sm)",
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
function TypingIndicator() {
  return (
    <div className="flex gap-1.5 items-center py-1">
      <div 
        className="w-1.5 h-1.5 rounded-full" 
        style={{ 
          background: "var(--text-tertiary)",
          animation: 'pulse-dot 1s infinite' 
        }} 
      />
      <div 
        className="w-1.5 h-1.5 rounded-full" 
        style={{ 
          background: "var(--text-tertiary)",
          animation: 'pulse-dot 1s infinite 0.2s' 
        }} 
      />
      <div 
        className="w-1.5 h-1.5 rounded-full" 
        style={{ 
          background: "var(--text-tertiary)",
          animation: 'pulse-dot 1s infinite 0.4s' 
        }} 
      />
    </div>
  );
}

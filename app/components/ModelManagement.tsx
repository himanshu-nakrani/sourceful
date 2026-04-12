"use client";

import React from "react";
import { Box, CheckCircle2, Cpu, KeyRound, RotateCcw, Sparkles, Zap } from "lucide-react";

import { type Provider } from "../lib/api";
import { DEFAULT_CHAT, DEFAULT_EMBEDDING, useStore } from "../lib/store";

const CHAT_MODEL_OPTIONS: Record<Provider, string[]> = {
  openai: ["gpt-4o-mini", "gpt-4.1-mini", "gpt-4.1", "gpt-4o"],
  gemini: ["gemini-2.0-flash", "gemini-2.5-flash", "gemini-2.5-pro"],
  vertex_search: ["gemini-2.0-flash", "gemini-2.5-flash", "gemini-2.5-pro"],
};

const EMBEDDING_MODEL_OPTIONS: Record<Provider, string[]> = {
  openai: ["text-embedding-3-small", "text-embedding-3-large"],
  gemini: ["models/gemini-embedding-001"],
  vertex_search: ["vertex_search_managed"],
};

const PROVIDER_INFO: Record<Provider, { label: string; icon: string; color: string; description: string }> = {
  openai: {
    label: "OpenAI",
    icon: "O",
    color: "#10a37f",
    description: "GPT-4o and text-embedding-3 models via OpenAI API.",
  },
  gemini: {
    label: "Google Gemini",
    icon: "G",
    color: "#4285f4",
    description: "Gemini flash and pro models via Google AI Studio.",
  },
  vertex_search: {
    label: "Vertex AI Search",
    icon: "V",
    color: "#ea4335",
    description: "Google Cloud Vertex AI Search with managed embeddings.",
  },
};

export default function ModelManagement() {
  const { state, dispatch } = useStore();
  const { settings } = state;

  const providers: Provider[] = ["openai", "gemini", "vertex_search"];

  return (
    <div className="flex-1 overflow-y-auto px-4 py-6" style={{ background: "var(--bg-primary)" }}>
      <div className="mx-auto flex max-w-4xl flex-col gap-6 animate-fade-in">
        {/* Header */}
        <div
          className="rounded-[28px] border px-5 sm:px-6 py-6"
          style={{
            borderColor: "var(--border)",
            background:
              "radial-gradient(circle at top left, rgba(16,163,127,0.15), transparent 32%), linear-gradient(180deg, var(--bg-secondary), var(--bg-primary))",
          }}
        >
          <p className="text-xs font-semibold uppercase tracking-wider" style={{ color: "var(--text-tertiary)" }}>
            Configuration
          </p>
          <h2 className="mt-2 text-xl sm:text-2xl font-semibold" style={{ color: "var(--text-primary)" }}>
            Model Management
          </h2>
          <p className="mt-2 max-w-2xl text-sm" style={{ color: "var(--text-secondary)" }}>
            Select your AI provider, configure chat and embedding models, and manage API credentials.
          </p>
        </div>

        {/* Provider Selection */}
        <div
          className="rounded-2xl border px-5 py-5"
          style={{ borderColor: "var(--border)", background: "var(--bg-surface)" }}
        >
          <div className="flex items-center gap-2 mb-4">
            <Cpu size={16} style={{ color: "var(--accent-brand)" }} />
            <h3 className="text-sm font-semibold" style={{ color: "var(--text-primary)" }}>
              Active Provider
            </h3>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            {providers.map((p) => {
              const info = PROVIDER_INFO[p];
              const isActive = settings.provider === p;
              return (
                <button
                  key={p}
                  type="button"
                  onClick={() => dispatch({ type: "SET_PROVIDER", payload: p })}
                  className="relative rounded-xl px-4 py-4 text-left transition-all"
                  style={{
                    background: isActive ? "var(--accent-soft)" : "var(--bg-secondary)",
                    border: `1.5px solid ${isActive ? info.color : "var(--border)"}`,
                  }}
                >
                  {isActive ? (
                    <CheckCircle2
                      size={16}
                      className="absolute top-3 right-3"
                      style={{ color: info.color }}
                    />
                  ) : null}
                  <div
                    className="flex items-center justify-center rounded-lg text-sm font-bold mb-3"
                    style={{
                      width: 36,
                      height: 36,
                      background: `${info.color}20`,
                      color: info.color,
                    }}
                  >
                    {info.icon}
                  </div>
                  <p className="text-sm font-semibold" style={{ color: "var(--text-primary)" }}>
                    {info.label}
                  </p>
                  <p className="text-xs mt-1 leading-relaxed" style={{ color: "var(--text-tertiary)" }}>
                    {info.description}
                  </p>
                </button>
              );
            })}
          </div>
        </div>

        {/* Model configuration grid */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {/* Chat Model */}
          <div
            className="rounded-2xl border px-5 py-5"
            style={{ borderColor: "var(--border)", background: "var(--bg-surface)" }}
          >
            <div className="flex items-center gap-2 mb-4">
              <Sparkles size={16} style={{ color: "var(--accent-brand)" }} />
              <h3 className="text-sm font-semibold" style={{ color: "var(--text-primary)" }}>
                Chat Model
              </h3>
            </div>
            <p className="text-xs mb-3" style={{ color: "var(--text-tertiary)" }}>
              Used for generating AI responses in the document Q&A chat.
            </p>
            <div className="flex flex-col gap-2">
              {CHAT_MODEL_OPTIONS[settings.provider].map((model) => (
                <button
                  key={model}
                  type="button"
                  onClick={() => dispatch({ type: "SET_SETTINGS", payload: { chatModel: model } })}
                  className="flex items-center justify-between rounded-lg px-3 py-2.5 text-sm transition-all"
                  style={{
                    background: settings.chatModel === model ? "var(--accent-soft)" : "var(--bg-secondary)",
                    border: `1px solid ${settings.chatModel === model ? "var(--border-accent)" : "var(--border)"}`,
                    color: settings.chatModel === model ? "var(--text-primary)" : "var(--text-secondary)",
                  }}
                >
                  <span className="inline-flex items-center gap-2">
                    <Box size={14} />
                    {model}
                  </span>
                  {settings.chatModel === model ? (
                    <CheckCircle2 size={14} style={{ color: "var(--success)" }} />
                  ) : null}
                </button>
              ))}
            </div>
            <input
              value={settings.chatModel}
              onChange={(e) => dispatch({ type: "SET_SETTINGS", payload: { chatModel: e.target.value } })}
              placeholder="Or type a custom model name"
              className="mt-3 w-full rounded-lg px-3 py-2.5 text-sm outline-none"
              style={{
                background: "var(--bg-secondary)",
                border: "1px solid var(--border)",
                color: "var(--text-primary)",
              }}
            />
          </div>

          {/* Embedding Model */}
          <div
            className="rounded-2xl border px-5 py-5"
            style={{ borderColor: "var(--border)", background: "var(--bg-surface)" }}
          >
            <div className="flex items-center gap-2 mb-4">
              <Zap size={16} style={{ color: "var(--accent-brand)" }} />
              <h3 className="text-sm font-semibold" style={{ color: "var(--text-primary)" }}>
                Embedding Model
              </h3>
            </div>
            <p className="text-xs mb-3" style={{ color: "var(--text-tertiary)" }}>
              Used for indexing documents and generating vector embeddings.
            </p>
            <div className="flex flex-col gap-2">
              {EMBEDDING_MODEL_OPTIONS[settings.provider].map((model) => (
                <button
                  key={model}
                  type="button"
                  onClick={() => dispatch({ type: "SET_SETTINGS", payload: { embeddingModel: model } })}
                  className="flex items-center justify-between rounded-lg px-3 py-2.5 text-sm transition-all"
                  style={{
                    background: settings.embeddingModel === model ? "var(--accent-soft)" : "var(--bg-secondary)",
                    border: `1px solid ${settings.embeddingModel === model ? "var(--border-accent)" : "var(--border)"}`,
                    color: settings.embeddingModel === model ? "var(--text-primary)" : "var(--text-secondary)",
                  }}
                >
                  <span className="inline-flex items-center gap-2">
                    <Box size={14} />
                    {model}
                  </span>
                  {settings.embeddingModel === model ? (
                    <CheckCircle2 size={14} style={{ color: "var(--success)" }} />
                  ) : null}
                </button>
              ))}
            </div>
            <input
              value={settings.embeddingModel}
              onChange={(e) => dispatch({ type: "SET_SETTINGS", payload: { embeddingModel: e.target.value } })}
              placeholder="Or type a custom model name"
              className="mt-3 w-full rounded-lg px-3 py-2.5 text-sm outline-none"
              style={{
                background: "var(--bg-secondary)",
                border: "1px solid var(--border)",
                color: "var(--text-primary)",
              }}
            />
          </div>
        </div>

        {/* API Key */}
        <div
          className="rounded-2xl border px-5 py-5"
          style={{ borderColor: "var(--border)", background: "var(--bg-surface)" }}
        >
          <div className="flex items-center gap-2 mb-4">
            <KeyRound size={16} style={{ color: "var(--accent-brand)" }} />
            <h3 className="text-sm font-semibold" style={{ color: "var(--text-primary)" }}>
              Provider API Key
            </h3>
          </div>
          <p className="text-xs mb-3" style={{ color: "var(--text-tertiary)" }}>
            Your API key is stored in browser session storage only. It is never sent to our servers.
          </p>
          <div className="relative">
            <div className="absolute left-3 top-1/2 -translate-y-1/2" style={{ color: "var(--text-muted)" }}>
              <KeyRound size={14} />
            </div>
            <input
              type="password"
              autoComplete="off"
              value={settings.providerApiKey}
              onChange={(e) => dispatch({ type: "SET_SETTINGS", payload: { providerApiKey: e.target.value } })}
              placeholder={
                settings.provider === "openai"
                  ? "sk-..."
                  : "Google AI API key"
              }
              className="w-full rounded-lg px-3 py-2.5 pl-9 text-sm outline-none"
              style={{
                background: "var(--bg-secondary)",
                border: "1px solid var(--border)",
                color: "var(--text-primary)",
              }}
            />
          </div>
          {settings.providerApiKey.trim() ? (
            <div className="mt-3 flex items-center gap-2 text-xs" style={{ color: "var(--success)" }}>
              <CheckCircle2 size={12} />
              API key configured
            </div>
          ) : (
            <div className="mt-3 flex items-center gap-2 text-xs" style={{ color: "var(--warning)" }}>
              <KeyRound size={12} />
              No API key set — uploads and chat will not work
            </div>
          )}
        </div>

        {/* Reset defaults */}
        <div className="flex items-center justify-between">
          <div className="text-xs" style={{ color: "var(--text-tertiary)" }}>
            Session: {settings.clientSessionId}
          </div>
          <button
            type="button"
            onClick={() =>
              dispatch({
                type: "SET_SETTINGS",
                payload: {
                  chatModel: DEFAULT_CHAT[settings.provider],
                  embeddingModel: DEFAULT_EMBEDDING[settings.provider],
                },
              })
            }
            className="inline-flex items-center gap-2 px-3 py-2 rounded-lg text-sm"
            style={{ background: "var(--bg-surface)", color: "var(--text-secondary)", border: "1px solid var(--border)" }}
          >
            <RotateCcw size={14} />
            Reset to Defaults
          </button>
        </div>
      </div>
    </div>
  );
}

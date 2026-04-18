"use client";

import React from "react";
import { motion } from "framer-motion";
import { Box, CheckCircle2, Cpu, KeyRound, RotateCcw, Sparkles, Zap } from "lucide-react";

import { type Provider } from "../lib/api";
import { EASE_OUT } from "../lib/motion";
import { DEFAULT_CHAT, DEFAULT_EMBEDDING, useStore } from "../lib/store";

const CHAT_MODEL_OPTIONS: Record<Provider, string[]> = {
  openai: ["gpt-4o-mini", "gpt-4o", "gpt-4-turbo", "gpt-4.1-mini", "gpt-4.1"],
  gemini: ["gemini-1.5-flash", "gemini-1.5-pro", "gemini-2.0-flash", "gemini-2.5-flash", "gemini-2.5-pro"],
  // vertex_search: ["gemini-1.5-flash", "gemini-1.5-pro", "gemini-2.0-flash", "gemini-2.5-flash", "gemini-2.5-pro"],
};

const EMBEDDING_MODEL_OPTIONS: Record<Provider, string[]> = {
  openai: ["text-embedding-3-small", "text-embedding-3-large"],
  gemini: ["models/gemini-embedding-001"],
  // vertex_search: ["vertex_search_managed"],
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
  /* vertex_search: {
    label: "Vertex AI Search",
    icon: "V",
    color: "#ea4335",
    description: "Google Cloud Vertex AI Search with managed embeddings.",
  }, */
};

const container = {
  hidden: { opacity: 0 },
  show: { opacity: 1, transition: { staggerChildren: 0.06, delayChildren: 0.1 } },
};

const fadeUp = {
  hidden: { opacity: 0, y: 12 },
  show: { opacity: 1, y: 0, transition: { duration: 0.4, ease: EASE_OUT } },
};

export default function ModelManagement() {
  const { state, dispatch } = useStore();
  const { settings } = state;

  const providers: Provider[] = ["openai", "gemini"];

  return (
    <div className="flex-1 overflow-y-auto px-4 py-6" style={{ background: "var(--bg-primary)" }}>
      <motion.div
        className="mx-auto flex max-w-4xl flex-col gap-5"
        variants={container}
        initial="hidden"
        animate="show"
      >
        {/* Header */}
        <motion.div
          className="rounded-2xl px-5 sm:px-6 py-6"
          style={{
            background: "var(--bg-secondary)",
            border: "1px solid var(--border)",
          }}
          variants={fadeUp}
        >
          <p className="text-[10px] font-semibold uppercase tracking-widest" style={{ color: "var(--text-muted)" }}>
            Configuration
          </p>
          <h2 className="mt-2 text-xl font-semibold" style={{ color: "var(--text-primary)", letterSpacing: "-0.02em" }}>
            Model Management
          </h2>
          <p className="mt-2 max-w-2xl text-sm" style={{ color: "var(--text-tertiary)" }}>
            Select your AI provider, configure chat and embedding models, and manage API credentials.
          </p>
        </motion.div>

        {/* Provider Selection */}
        <motion.div
          className="rounded-2xl px-5 py-5"
          style={{ background: "var(--bg-surface)", border: "1px solid var(--border)" }}
          variants={fadeUp}
        >
          <div className="flex items-center gap-2 mb-4">
            <Cpu size={14} style={{ color: "var(--accent-brand)" }} />
            <h3 className="text-sm font-semibold" style={{ color: "var(--text-primary)", letterSpacing: "-0.01em" }}>
              Active Provider
            </h3>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {providers.map((p) => {
              const info = PROVIDER_INFO[p];
              const isActive = settings.provider === p;
              return (
                <motion.button
                  key={p}
                  type="button"
                  onClick={() => dispatch({ type: "SET_PROVIDER", payload: p })}
                  className="relative rounded-xl px-4 py-4 text-left"
                  style={{
                    background: isActive ? "var(--accent-brand-soft)" : "var(--bg-secondary)",
                    border: `1.5px solid ${isActive ? info.color : "var(--border)"}`,
                  }}
                  whileHover={{ borderColor: info.color, y: -1 }}
                  whileTap={{ scale: 0.98 }}
                  transition={{ duration: 0.15 }}
                >
                  {isActive ? (
                    <CheckCircle2
                      size={14}
                      className="absolute top-3 right-3"
                      style={{ color: info.color }}
                    />
                  ) : null}
                  <div
                    className="flex items-center justify-center rounded-lg text-xs font-bold mb-3"
                    style={{
                      width: 32,
                      height: 32,
                      background: `${info.color}15`,
                      color: info.color,
                    }}
                  >
                    {info.icon}
                  </div>
                  <p className="text-sm font-semibold" style={{ color: "var(--text-primary)" }}>
                    {info.label}
                  </p>
                  <p className="text-[11px] mt-1 leading-relaxed" style={{ color: "var(--text-muted)" }}>
                    {info.description}
                  </p>
                </motion.button>
              );
            })}
          </div>
        </motion.div>

        {/* Model configuration grid */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {/* Chat Model */}
          <motion.div
            className="rounded-2xl px-5 py-5"
            style={{ background: "var(--bg-surface)", border: "1px solid var(--border)" }}
            variants={fadeUp}
          >
            <div className="flex items-center gap-2 mb-4">
              <Sparkles size={14} style={{ color: "var(--accent-brand)" }} />
              <h3 className="text-sm font-semibold" style={{ color: "var(--text-primary)", letterSpacing: "-0.01em" }}>
                Chat Model
              </h3>
            </div>
            <p className="text-[11px] mb-3" style={{ color: "var(--text-muted)" }}>
              Used for generating AI responses in document Q&A chat.
            </p>
            <div className="flex flex-col gap-1.5">
              {CHAT_MODEL_OPTIONS[settings.provider].map((model, i) => (
                <motion.button
                  key={model}
                  type="button"
                  onClick={() => dispatch({ type: "SET_SETTINGS", payload: { chatModel: model } })}
                  className="flex items-center justify-between rounded-xl px-3 py-2.5 text-sm"
                  style={{
                    background: settings.chatModel === model ? "var(--accent-brand-soft)" : "var(--bg-secondary)",
                    border: `1px solid ${settings.chatModel === model ? "var(--accent-brand)" : "var(--border)"}`,
                    color: settings.chatModel === model ? "var(--text-primary)" : "var(--text-secondary)",
                  }}
                  whileHover={{ borderColor: "var(--border-hover)" }}
                  whileTap={{ scale: 0.98 }}
                  initial={{ opacity: 0, x: -6 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: i * 0.03, duration: 0.25 }}
                >
                  <span className="inline-flex items-center gap-2">
                    <Box size={12} />
                    {model}
                  </span>
                  {settings.chatModel === model ? (
                    <CheckCircle2 size={12} style={{ color: "var(--success)" }} />
                  ) : null}
                </motion.button>
              ))}
            </div>
            <input
              value={settings.chatModel}
              onChange={(e) => dispatch({ type: "SET_SETTINGS", payload: { chatModel: e.target.value } })}
              placeholder="Or type a custom model name"
              className="mt-3 w-full rounded-xl px-3 py-2.5 text-sm outline-none transition-all duration-200"
              style={{
                background: "var(--bg-secondary)",
                border: "1px solid var(--border)",
                color: "var(--text-primary)",
              }}
            />
          </motion.div>

          {/* Embedding Model */}
          <motion.div
            className="rounded-2xl px-5 py-5"
            style={{ background: "var(--bg-surface)", border: "1px solid var(--border)" }}
            variants={fadeUp}
          >
            <div className="flex items-center gap-2 mb-4">
              <Zap size={14} style={{ color: "var(--accent-brand)" }} />
              <h3 className="text-sm font-semibold" style={{ color: "var(--text-primary)", letterSpacing: "-0.01em" }}>
                Embedding Model
              </h3>
            </div>
            <p className="text-[11px] mb-3" style={{ color: "var(--text-muted)" }}>
              Used for indexing documents and generating vector embeddings.
            </p>
            <div className="flex flex-col gap-1.5">
              {EMBEDDING_MODEL_OPTIONS[settings.provider].map((model, i) => (
                <motion.button
                  key={model}
                  type="button"
                  onClick={() => dispatch({ type: "SET_SETTINGS", payload: { embeddingModel: model } })}
                  className="flex items-center justify-between rounded-xl px-3 py-2.5 text-sm"
                  style={{
                    background: settings.embeddingModel === model ? "var(--accent-brand-soft)" : "var(--bg-secondary)",
                    border: `1px solid ${settings.embeddingModel === model ? "var(--accent-brand)" : "var(--border)"}`,
                    color: settings.embeddingModel === model ? "var(--text-primary)" : "var(--text-secondary)",
                  }}
                  whileHover={{ borderColor: "var(--border-hover)" }}
                  whileTap={{ scale: 0.98 }}
                  initial={{ opacity: 0, x: -6 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: i * 0.03, duration: 0.25 }}
                >
                  <span className="inline-flex items-center gap-2">
                    <Box size={12} />
                    {model}
                  </span>
                  {settings.embeddingModel === model ? (
                    <CheckCircle2 size={12} style={{ color: "var(--success)" }} />
                  ) : null}
                </motion.button>
              ))}
            </div>
            <input
              value={settings.embeddingModel}
              onChange={(e) => dispatch({ type: "SET_SETTINGS", payload: { embeddingModel: e.target.value } })}
              placeholder="Or type a custom model name"
              className="mt-3 w-full rounded-xl px-3 py-2.5 text-sm outline-none transition-all duration-200"
              style={{
                background: "var(--bg-secondary)",
                border: "1px solid var(--border)",
                color: "var(--text-primary)",
              }}
            />
          </motion.div>
        </div>

        {/* API Key */}
        <motion.div
          className="rounded-2xl px-5 py-5"
          style={{ background: "var(--bg-surface)", border: "1px solid var(--border)" }}
          variants={fadeUp}
        >
          <div className="flex items-center gap-2 mb-4">
            <KeyRound size={14} style={{ color: "var(--accent-brand)" }} />
            <h3 className="text-sm font-semibold" style={{ color: "var(--text-primary)", letterSpacing: "-0.01em" }}>
              Provider API Key
            </h3>
          </div>
          <p className="text-[11px] mb-3" style={{ color: "var(--text-muted)" }}>
            Stored in browser session storage only. Never sent to our servers.
          </p>
          <div className="relative">
            <div className="absolute left-3 top-1/2 -translate-y-1/2" style={{ color: "var(--text-muted)" }}>
              <KeyRound size={13} />
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
              className="w-full rounded-xl px-3 py-2.5 pl-9 text-sm outline-none transition-all duration-200"
              style={{
                background: "var(--bg-secondary)",
                border: "1px solid var(--border)",
                color: "var(--text-primary)",
              }}
            />
          </div>
          {settings.providerApiKey.trim() ? (
            <motion.div
              className="mt-3 flex items-center gap-2 text-[11px]"
              style={{ color: "var(--success)" }}
              initial={{ opacity: 0, x: -4 }}
              animate={{ opacity: 1, x: 0 }}
            >
              <CheckCircle2 size={11} />
              API key configured
            </motion.div>
          ) : (
            <div className="mt-3 flex items-center gap-2 text-[11px]" style={{ color: "var(--warning)" }}>
              <KeyRound size={11} />
              No API key — uploads and chat won&apos;t work
            </div>
          )}
        </motion.div>

        {/* Reset defaults */}
        <motion.div className="flex items-center justify-between" variants={fadeUp}>
          <div className="text-[11px]" style={{ color: "var(--text-muted)" }}>
            Session: {settings.clientSessionId}
          </div>
          <motion.button
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
            className="inline-flex items-center gap-2 px-3 py-2 rounded-xl text-xs"
            style={{ background: "var(--bg-surface)", color: "var(--text-tertiary)", border: "1px solid var(--border)" }}
            whileHover={{ borderColor: "var(--border-hover)", color: "var(--text-secondary)" }}
            whileTap={{ scale: 0.95 }}
          >
            <RotateCcw size={12} />
            Reset to Defaults
          </motion.button>
        </motion.div>
      </motion.div>
    </div>
  );
}

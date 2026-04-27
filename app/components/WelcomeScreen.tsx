"use client";

import React, { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  FileText,
  KeyRound,
  LockKeyhole,
  Shield,
  UserCircle,
} from "lucide-react";
import { type Provider } from "../lib/api";
import { EASE_OUT } from "../lib/motion";
import { DEFAULT_CHAT, DEFAULT_EMBEDDING, useStore } from "../lib/store";

interface WelcomeScreenProps {
  onComplete: () => void;
}

/**
 * Render the initial setup UI to choose an LLM provider, enter an API key, optionally sign in, and complete app setup.
 *
 * @param onComplete - Callback invoked after settings are saved and setup is marked complete
 * @returns The welcome/setup screen as a JSX element
 */
const container = {
  hidden: { opacity: 0 },
  show: {
    opacity: 1,
    transition: { staggerChildren: 0.06, delayChildren: 0.08 },
  },
};

const item = {
  hidden: { opacity: 0, y: 16, filter: "blur(4px)" },
  show: { opacity: 1, y: 0, filter: "blur(0px)", transition: { duration: 0.5, ease: EASE_OUT } },
};

const setupNotes = [
  "Provider key is stored in this browser session.",
  "Documents stay scoped to your client session or signed-in workspace.",
  "Answers are designed around citations and source review.",
];

export default function WelcomeScreen({ onComplete }: WelcomeScreenProps) {
  const { dispatch } = useStore();
  const [provider, setProvider] = useState<Provider>("openai");
  const [apiKey, setApiKey] = useState("");
  const [showLogin, setShowLogin] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [focused, setFocused] = useState(false);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!apiKey.trim()) {
      setError("Please enter your API key");
      return;
    }

    if (provider === "openai" && !apiKey.startsWith("sk-")) {
      setError("OpenAI keys should start with 'sk-'");
      return;
    }

    dispatch({
      type: "SET_SETTINGS",
      payload: {
        provider,
        providerApiKey: apiKey.trim(),
        chatModel: DEFAULT_CHAT[provider],
        embeddingModel: DEFAULT_EMBEDDING[provider],
      },
    });

    dispatch({ type: "SET_SETUP_COMPLETE", payload: true });
    onComplete();
  };

  if (showLogin) {
    return <LoginPrompt onBack={() => setShowLogin(false)} />;
  }

  return (
    <div
      className="relative flex min-h-screen items-center justify-center overflow-hidden px-4 py-10"
      style={{ background: "var(--bg-primary)" }}
    >
      <div
        className="pointer-events-none absolute inset-x-0 top-0 h-px"
        style={{ background: "linear-gradient(90deg, transparent, var(--border-strong), transparent)" }}
      />

      <motion.div
        className="relative z-10 grid w-full max-w-5xl gap-6 lg:grid-cols-[0.9fr_1.1fr] lg:items-center"
        variants={container}
        initial="hidden"
        animate="show"
      >
        <motion.div variants={item}>
          <div
            className="mb-6 inline-flex items-center gap-2 rounded-full px-3 py-1.5 text-xs font-medium"
            style={{
              background: "var(--bg-secondary)",
              border: "1px solid var(--border)",
              color: "var(--text-secondary)",
            }}
          >
            <LockKeyhole size={12} />
            Secure local setup
          </div>
          <h1
            className="text-4xl font-semibold leading-tight sm:text-5xl"
            style={{ color: "var(--text-primary)", letterSpacing: "-0.045em" }}
          >
            Prepare a workspace for traceable document answers.
          </h1>
          <p className="mt-5 max-w-md text-sm leading-7 sm:text-base" style={{ color: "var(--text-secondary)" }}>
            Connect a model provider, then upload documents and inspect every response through citations, source scores, and retrieval state.
          </p>

          <div className="mt-8 space-y-3">
            {setupNotes.map((note) => (
              <div key={note} className="flex items-start gap-3 text-sm" style={{ color: "var(--text-secondary)" }}>
                <CheckCircle2 size={15} className="mt-0.5 flex-shrink-0" style={{ color: "var(--confidence-high)" }} />
                <span>{note}</span>
              </div>
            ))}
          </div>
        </motion.div>

        <motion.div className="w-full" variants={item}>
          <div
            className="mb-3 rounded-xl px-4 py-3"
            style={{ background: "var(--bg-secondary)", border: "1px solid var(--border)" }}
          >
            <div className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-3">
                <div
                  className="flex h-9 w-9 items-center justify-center rounded-lg"
                  style={{
                    background: "var(--bg-surface)",
                    border: "1px solid var(--border)",
                    color: "var(--accent-primary)",
                  }}
                >
                  <FileText size={16} />
                </div>
                <div>
                  <p className="text-sm font-semibold" style={{ color: "var(--text-primary)" }}>
                    DocRAG
                  </p>
                  <p className="text-[11px]" style={{ color: "var(--text-muted)" }}>
                    Provider access required before indexing
                  </p>
                </div>
              </div>
              <span className="rounded-full px-2.5 py-1 text-[11px]" style={{ background: "var(--warning-soft)", color: "var(--warning)" }}>
                setup
              </span>
            </div>
          </div>

          <motion.div
            className="relative overflow-hidden rounded-xl p-6"
            style={{
              background: "var(--bg-secondary)",
              border: "1px solid var(--border-hover)",
              boxShadow: "var(--shadow-md)",
            }}
            variants={item}
          >
            <div className="mb-6 flex items-center gap-2">
              <div
                className="flex h-6 w-6 items-center justify-center rounded-md"
                style={{ background: "var(--bg-surface)", border: "1px solid var(--border)" }}
              >
                <KeyRound size={12} style={{ color: "var(--text-secondary)" }} />
              </div>
              <span className="text-xs font-semibold uppercase tracking-wide" style={{ color: "var(--text-tertiary)" }}>
                Provider credentials
              </span>
            </div>

            <div
              className="mb-6 flex gap-1 rounded-lg p-1"
              style={{
                background: "var(--bg-surface)",
                border: "1px solid var(--border)",
              }}
            >
              {(["openai", "gemini"] as const).map((p) => (
                <motion.button
                  key={p}
                  type="button"
                  onClick={() => setProvider(p)}
                  className="relative flex flex-1 items-center justify-center gap-2 rounded-md px-4 py-2.5 text-sm font-medium"
                  style={{
                    background: provider === p ? "var(--accent)" : "transparent",
                    color: provider === p ? "var(--accent-fg)" : "var(--text-secondary)",
                  }}
                  whileTap={{ scale: 0.97 }}
                  transition={{ duration: 0.15 }}
                >
                  {p === "openai" ? "OpenAI" : "Gemini"}
                </motion.button>
              ))}
            </div>

            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label
                  className="mb-2 block text-xs font-semibold uppercase tracking-wider"
                  style={{ color: "var(--text-tertiary)" }}
                >
                  {provider === "openai" ? "OpenAI API Key" : "Google AI API Key"}
                </label>
                <div className="relative">
                  <div
                    className="absolute left-3.5 top-1/2 -translate-y-1/2 transition-colors duration-200"
                    style={{ color: focused ? "var(--accent-primary)" : "var(--text-muted)" }}
                  >
                    <KeyRound size={15} />
                  </div>
                  <input
                    type="password"
                    value={apiKey}
                    onChange={(e) => {
                      setApiKey(e.target.value);
                      setError(null);
                    }}
                    onFocus={() => setFocused(true)}
                    onBlur={() => setFocused(false)}
                    placeholder={provider === "openai" ? "sk-..." : "Google AI API key"}
                    className="w-full rounded-lg px-3 py-3 pl-10 text-sm outline-none transition-all duration-200"
                    style={{
                      background: "var(--bg-surface)",
                      border: `1px solid ${focused ? "var(--border-hover)" : "var(--border)"}`,
                      color: "var(--text-primary)",
                      boxShadow: focused ? "0 0 0 3px var(--accent-primary-soft)" : "none",
                    }}
                    autoComplete="off"
                  />
                </div>
                <p className="mt-2 flex items-center gap-1.5 text-xs" style={{ color: "var(--text-muted)" }}>
                  <Shield size={10} />
                  Stored locally in this session.
                </p>
              </div>

              <AnimatePresence>
                {error && (
                  <motion.div
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: "auto" }}
                    exit={{ opacity: 0, height: 0 }}
                    className="overflow-hidden rounded-lg px-3 py-2 text-sm"
                    style={{ background: "var(--error-soft)", color: "var(--error)" }}
                  >
                    {error}
                  </motion.div>
                )}
              </AnimatePresence>

              <motion.button
                type="submit"
                className="flex w-full items-center justify-center gap-2 rounded-lg px-4 py-3.5 text-sm font-semibold"
                style={{
                  background: "var(--accent)",
                  color: "var(--accent-fg)",
                  boxShadow: "var(--shadow-sm)",
                }}
                whileHover={{ scale: 1.01 }}
                whileTap={{ scale: 0.98 }}
                transition={{ type: "spring", stiffness: 400, damping: 17 }}
              >
                Initialize workspace
                <ArrowRight size={15} />
              </motion.button>
            </form>
          </motion.div>

          <motion.div className="mt-6 text-center" variants={item}>
            <button
              type="button"
              onClick={() => setShowLogin(true)}
              className="inline-flex items-center gap-2 text-sm transition-colors"
              style={{ color: "var(--text-tertiary)" }}
            >
              <UserCircle size={15} />
              Sign in for cross-device sync
            </button>
          </motion.div>
        </motion.div>
      </motion.div>
    </div>
  );
}

/**
 * Renders a sign-in / sign-up prompt that authenticates a user and marks initial setup complete.
 *
 * The component provides email and password inputs, toggles between login and signup modes,
 * lazily imports and calls the appropriate auth function, dispatches the authenticated user
 * to the store, and sets the setup-complete flag. It also manages loading and error states.
 *
 * @param onBack - Callback invoked when the user chooses to return to the setup screen
 * @returns The JSX element for the login/signup prompt
 */
function LoginPrompt({ onBack }: { onBack: () => void }) {
  const { dispatch } = useStore();
  const [mode, setMode] = useState<"login" | "signup">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);

    try {
      const { login, signup } = await import("../lib/api");
      const user =
        mode === "login"
          ? await login(email.trim(), password)
          : await signup(email.trim(), password);
      dispatch({ type: "SET_CURRENT_USER", payload: user });
      dispatch({ type: "SET_SETUP_COMPLETE", payload: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Authentication failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      className="flex min-h-screen items-center justify-center px-4 py-10"
      style={{ background: "var(--bg-primary)" }}
    >
      <motion.div
        className="w-full max-w-md"
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, ease: EASE_OUT }}
      >
        <button
          type="button"
          onClick={onBack}
          className="mb-4 flex items-center gap-1 text-sm transition-colors"
          style={{ color: "var(--text-secondary)" }}
        >
          <ArrowLeft size={14} />
          Back to setup
        </button>

        <div
          className="rounded-xl p-6"
          style={{
            background: "var(--bg-secondary)",
            border: "1px solid var(--border)",
            boxShadow: "var(--shadow-md)",
          }}
        >
          <h2 className="mb-4 text-lg font-semibold" style={{ color: "var(--text-primary)" }}>
            {mode === "login" ? "Sign in" : "Create account"}
          </h2>

          <form onSubmit={handleSubmit} className="space-y-4">
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="Email"
              required
              className="w-full rounded-lg px-4 py-3 text-sm outline-none transition-all duration-200 focus:ring-2 focus:ring-[var(--accent-primary)]"
              style={{
                background: "var(--bg-surface)",
                border: "1px solid var(--border)",
                color: "var(--text-primary)",
              }}
            />
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Password"
              required
              minLength={mode === "signup" ? 8 : undefined}
              className="w-full rounded-lg px-4 py-3 text-sm outline-none transition-all duration-200 focus:ring-2 focus:ring-[var(--accent-primary)]"
              style={{
                background: "var(--bg-surface)",
                border: "1px solid var(--border)",
                color: "var(--text-primary)",
              }}
            />

            <AnimatePresence>
              {error && (
                <motion.div
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: "auto" }}
                  exit={{ opacity: 0, height: 0 }}
                  className="rounded-lg px-3 py-2 text-sm"
                  style={{ background: "var(--error-soft)", color: "var(--error)" }}
                >
                  {error}
                </motion.div>
              )}
            </AnimatePresence>

            <motion.button
              type="submit"
              disabled={loading}
              className="w-full rounded-lg px-4 py-3 text-sm font-semibold"
              style={{
                background: "var(--accent)",
                color: "var(--accent-fg)",
                opacity: loading ? 0.7 : 1,
              }}
              whileHover={{ scale: 1.01 }}
              whileTap={{ scale: 0.98 }}
            >
              {loading ? "Working..." : mode === "login" ? "Sign in" : "Create account"}
            </motion.button>
          </form>

          <div className="mt-4 text-center">
            <button
              type="button"
              onClick={() => setMode(mode === "login" ? "signup" : "login")}
              className="text-sm"
              style={{ color: "var(--text-secondary)" }}
            >
              {mode === "login" ? "Need an account? Sign up" : "Already have an account? Sign in"}
            </button>
          </div>
        </div>
      </motion.div>
    </div>
  );
}

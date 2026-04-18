"use client";

import React, { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ArrowRight, FileText, KeyRound, Sparkles, UserCircle, Zap, Shield, MessageSquare } from "lucide-react";
import { type Provider } from "../lib/api";
import { useStore, DEFAULT_CHAT, DEFAULT_EMBEDDING } from "../lib/store";

interface WelcomeScreenProps {
  onComplete: () => void;
}

/**
 * Render the initial Quick Setup UI to choose an LLM provider, enter an API key, optionally sign in, and complete initial app setup.
 *
 * @param onComplete - Callback invoked after settings are saved and setup is marked complete
 * @returns The welcome/setup screen as a JSX element
 */
const container = {
  hidden: { opacity: 0 },
  show: {
    opacity: 1,
    transition: { staggerChildren: 0.08, delayChildren: 0.1 },
  },
};

const item = {
  hidden: { opacity: 0, y: 16, filter: "blur(4px)" },
  show: { opacity: 1, y: 0, filter: "blur(0px)", transition: { duration: 0.5, ease: [0.22, 1, 0.36, 1] } },
};

const featureCards = [
  {
    icon: <Zap size={18} />,
    title: "Lightning Fast",
    desc: "Instant document indexing with intelligent chunking",
  },
  {
    icon: <Shield size={18} />,
    title: "Fully Private",
    desc: "API keys never leave your browser session",
  },
  {
    icon: <MessageSquare size={18} />,
    title: "Source Grounded",
    desc: "Every answer includes chunk-level citations",
  },
];

export default function WelcomeScreen({ onComplete }: WelcomeScreenProps) {
  const { dispatch } = useStore();
  const [provider, setProvider] = useState<Provider>("openai");
  const [apiKey, setApiKey] = useState("");
  const [showLogin, setShowLogin] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!apiKey.trim()) {
      setError("Please enter your API key");
      return;
    }

    // Validate key format
    if (provider === "openai" && !apiKey.startsWith("sk-")) {
      setError("OpenAI keys should start with 'sk-'");
      return;
    }

    // Save settings
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
      className="flex min-h-screen items-center justify-center px-4 py-10 relative overflow-hidden"
      style={{ background: "var(--bg-primary)" }}
    >
      {/* Ambient gradient orbs */}
      <motion.div
        className="absolute top-[-20%] left-[-10%] w-[500px] h-[500px] rounded-full opacity-30 pointer-events-none"
        style={{
          background: "radial-gradient(circle, rgba(99,102,241,0.15), transparent 70%)",
        }}
        animate={{ scale: [1, 1.1, 1], x: [0, 30, 0], y: [0, -20, 0] }}
        transition={{ duration: 8, repeat: Infinity, ease: "easeInOut" }}
      />
      <motion.div
        className="absolute bottom-[-15%] right-[-10%] w-[400px] h-[400px] rounded-full opacity-20 pointer-events-none"
        style={{
          background: "radial-gradient(circle, rgba(34,197,94,0.12), transparent 70%)",
        }}
        animate={{ scale: [1, 1.15, 1], x: [0, -25, 0], y: [0, 15, 0] }}
        transition={{ duration: 10, repeat: Infinity, ease: "easeInOut" }}
      />

      <motion.div
        className="w-full max-w-md relative z-10"
        variants={container}
        initial="hidden"
        animate="show"
      >
        {/* Header */}
        <motion.div className="text-center mb-8" variants={item}>
          <motion.div
            className="inline-flex items-center justify-center rounded-2xl mb-5"
            style={{
              width: 56,
              height: 56,
              background: "var(--accent-brand-soft)",
              border: "1px solid var(--border)",
            }}
            whileHover={{ scale: 1.05, rotate: 2 }}
            transition={{ type: "spring", stiffness: 300 }}
          >
            <FileText size={24} style={{ color: "var(--accent-brand)" }} />
          </motion.div>
          <h1
            className="text-2xl font-semibold mb-2"
            style={{ color: "var(--text-primary)", letterSpacing: "-0.03em" }}
          >
            Document RAG
          </h1>
          <p className="text-sm" style={{ color: "var(--text-secondary)" }}>
            Upload documents, ask questions, get grounded answers
          </p>
        </motion.div>

        {/* Feature chips */}
        <motion.div className="flex flex-wrap justify-center gap-2 mb-8" variants={item}>
          {featureCards.map((feat) => (
            <motion.div
              key={feat.title}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs"
              style={{
                background: "var(--bg-surface)",
                border: "1px solid var(--border)",
                color: "var(--text-secondary)",
              }}
              whileHover={{
                borderColor: "rgba(99,102,241,0.3)",
                background: "var(--accent-brand-soft)",
              }}
              transition={{ duration: 0.2 }}
            >
              <span style={{ color: "var(--accent-brand)" }}>{feat.icon}</span>
              {feat.title}
            </motion.div>
          ))}
        </motion.div>

        {/* Setup Card */}
        <motion.div
          className="rounded-2xl p-6 relative overflow-hidden"
          style={{
            background: "var(--bg-secondary)",
            border: "1px solid var(--border)",
          }}
          variants={item}
        >
          <div className="flex items-center gap-2 mb-6">
            <Sparkles size={14} style={{ color: "var(--accent-brand)" }} />
            <span className="text-xs font-medium tracking-wide uppercase" style={{ color: "var(--text-tertiary)" }}>
              Quick Setup
            </span>
          </div>

          {/* Provider Selector */}
          <div
            className="flex gap-1 mb-6 p-1 rounded-xl"
            style={{ background: "var(--bg-surface)" }}
          >
            {(["openai", "gemini"] as const).map((p) => (
              <motion.button
                key={p}
                type="button"
                onClick={() => setProvider(p)}
                className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium"
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
            {/* API Key Input */}
            <div>
              <label
                className="block text-xs font-medium uppercase tracking-wider mb-2"
                style={{ color: "var(--text-tertiary)" }}
              >
                {provider === "openai" ? "OpenAI API Key" : "Google AI API Key"}
              </label>
              <div className="relative">
                <div
                  className="absolute left-3 top-1/2 -translate-y-1/2"
                  style={{ color: "var(--text-muted)" }}
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
                  placeholder={
                    provider === "openai" ? "sk-..." : "Google AI API key"
                  }
                  className="w-full rounded-xl px-3 py-3 pl-10 text-sm outline-none transition-all duration-200"
                  style={{
                    background: "var(--bg-surface)",
                    border: "1px solid var(--border)",
                    color: "var(--text-primary)",
                  }}
                  autoComplete="off"
                />
              </div>
              <p className="mt-2 text-xs" style={{ color: "var(--text-muted)" }}>
                Stored locally — never sent to our servers.
              </p>
            </div>

            <AnimatePresence>
              {error && (
                <motion.div
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: "auto" }}
                  exit={{ opacity: 0, height: 0 }}
                  className="rounded-xl px-3 py-2 text-sm overflow-hidden"
                  style={{ background: "var(--error-soft)", color: "var(--error)" }}
                >
                  {error}
                </motion.div>
              )}
            </AnimatePresence>

            <motion.button
              type="submit"
              className="w-full flex items-center justify-center gap-2 rounded-xl px-4 py-3 text-sm font-medium"
              style={{
                background: "var(--accent)",
                color: "var(--accent-fg)",
              }}
              whileHover={{ scale: 1.01 }}
              whileTap={{ scale: 0.98 }}
              transition={{ type: "spring", stiffness: 400, damping: 17 }}
            >
              Get Started
              <ArrowRight size={15} />
            </motion.button>
          </form>
        </motion.div>

        {/* Optional Login */}
        <motion.div className="mt-6 text-center" variants={item}>
          <button
            type="button"
            onClick={() => setShowLogin(true)}
            className="inline-flex items-center gap-2 text-sm"
            style={{ color: "var(--text-tertiary)" }}
          >
            <UserCircle size={15} />
            Sign in for cross-device sync
          </button>
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

  // Lazy load login/signup functions to avoid circular deps
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
        transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
      >
        <button
          type="button"
          onClick={onBack}
          className="mb-4 text-sm flex items-center gap-1"
          style={{ color: "var(--text-secondary)" }}
        >
          ← Back to setup
        </button>

        <div
          className="rounded-2xl p-6"
          style={{
            background: "var(--bg-secondary)",
            border: "1px solid var(--border)",
          }}
        >
          <h2 className="text-lg font-semibold mb-4" style={{ color: "var(--text-primary)" }}>
            {mode === "login" ? "Sign In" : "Create Account"}
          </h2>

          <form onSubmit={handleSubmit} className="space-y-4">
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="Email"
              required
              className="w-full rounded-xl px-4 py-3 text-sm outline-none transition-all duration-200"
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
              className="w-full rounded-xl px-4 py-3 text-sm outline-none transition-all duration-200"
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
                  className="rounded-xl px-3 py-2 text-sm"
                  style={{ background: "var(--error-soft)", color: "var(--error)" }}
                >
                  {error}
                </motion.div>
              )}
            </AnimatePresence>

            <motion.button
              type="submit"
              disabled={loading}
              className="w-full rounded-xl px-4 py-3 text-sm font-medium"
              style={{
                background: "var(--accent)",
                color: "var(--accent-fg)",
                opacity: loading ? 0.7 : 1,
              }}
              whileHover={{ scale: 1.01 }}
              whileTap={{ scale: 0.98 }}
            >
              {loading ? "Working..." : mode === "login" ? "Sign In" : "Create Account"}
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

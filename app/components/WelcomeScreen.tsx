"use client";

import React, { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ArrowRight, FileText, KeyRound, Sparkles, UserCircle, Zap, Shield, MessageSquare } from "lucide-react";
import { type Provider } from "../lib/api";
import { EASE_OUT } from "../lib/motion";
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
    transition: { staggerChildren: 0.06, delayChildren: 0.08 },
  },
};

const item = {
  hidden: { opacity: 0, y: 16, filter: "blur(4px)" },
  show: { opacity: 1, y: 0, filter: "blur(0px)", transition: { duration: 0.5, ease: EASE_OUT } },
};

const featureCards = [
  {
    icon: <Zap size={16} />,
    title: "Lightning Fast",
    desc: "Instant document indexing with intelligent chunking",
    color: "var(--accent-primary)",
  },
  {
    icon: <Shield size={16} />,
    title: "Fully Private",
    desc: "API keys never leave your browser session",
    color: "#22c55e",
  },
  {
    icon: <MessageSquare size={16} />,
    title: "Source Grounded",
    desc: "Every answer includes chunk-level citations",
    color: "var(--accent-secondary)",
  },
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
        className="absolute top-[-25%] left-[-15%] w-[600px] h-[600px] rounded-full pointer-events-none"
        style={{
          background: "radial-gradient(circle, rgba(20,184,166,0.12), transparent 65%)",
          filter: "blur(40px)",
        }}
        animate={{ scale: [1, 1.08, 1], x: [0, 25, 0], y: [0, -15, 0] }}
        transition={{ duration: 10, repeat: Infinity, ease: "easeInOut" }}
      />
      <motion.div
        className="absolute bottom-[-20%] right-[-10%] w-[500px] h-[500px] rounded-full pointer-events-none"
        style={{
          background: "radial-gradient(circle, rgba(139,92,246,0.1), transparent 65%)",
          filter: "blur(40px)",
        }}
        animate={{ scale: [1, 1.12, 1], x: [0, -20, 0], y: [0, 12, 0] }}
        transition={{ duration: 12, repeat: Infinity, ease: "easeInOut" }}
      />

      {/* Subtle grid */}
      <div
        className="absolute inset-0 pointer-events-none"
        style={{
          backgroundImage: `linear-gradient(var(--border) 1px, transparent 1px), linear-gradient(90deg, var(--border) 1px, transparent 1px)`,
          backgroundSize: "48px 48px",
          maskImage: "radial-gradient(ellipse 50% 50% at 50% 50%, black, transparent)",
          WebkitMaskImage: "radial-gradient(ellipse 50% 50% at 50% 50%, black, transparent)",
          opacity: 0.5,
        }}
      />

      <motion.div
        className="w-full max-w-lg relative z-10"
        variants={container}
        initial="hidden"
        animate="show"
      >
        {/* Header */}
        <motion.div className="text-center mb-8" variants={item}>
          <motion.div
            className="inline-flex items-center justify-center rounded-2xl mb-6"
            style={{
              width: 64,
              height: 64,
              background: "var(--gradient-accent-soft)",
              border: "1px solid var(--border-hover)",
              boxShadow: "var(--shadow-glow-teal)",
            }}
            whileHover={{ scale: 1.05, rotate: 2 }}
            transition={{ type: "spring", stiffness: 300 }}
          >
            <FileText size={28} className="gradient-text" style={{ color: "var(--accent-primary)" }} />
          </motion.div>
          <h1
            className="text-3xl font-bold mb-2"
            style={{ color: "var(--text-primary)", letterSpacing: "-0.03em" }}
          >
            Welcome to <span className="gradient-text">DocRAG</span>
          </h1>
          <p className="text-sm" style={{ color: "var(--text-secondary)" }}>
            Upload documents, ask questions, get grounded answers
          </p>
        </motion.div>

        {/* Feature chips */}
        <motion.div className="grid grid-cols-3 gap-2 mb-8" variants={item}>
          {featureCards.map((feat) => (
            <motion.div
              key={feat.title}
              className="flex flex-col items-center gap-2 px-3 py-3 rounded-xl text-center"
              style={{
                background: "var(--bg-surface)",
                border: "1px solid var(--border)",
              }}
              whileHover={{
                borderColor: "var(--border-hover)",
                y: -2,
              }}
              transition={{ duration: 0.2 }}
            >
              <div
                className="flex items-center justify-center w-8 h-8 rounded-lg"
                style={{
                  background: `${feat.color}12`,
                }}
              >
                <span style={{ color: feat.color }}>{feat.icon}</span>
              </div>
              <span className="text-xs font-medium" style={{ color: "var(--text-primary)" }}>
                {feat.title}
              </span>
              <span className="text-[10px] leading-tight" style={{ color: "var(--text-muted)" }}>
                {feat.desc}
              </span>
            </motion.div>
          ))}
        </motion.div>

        {/* Setup Card */}
        <motion.div
          className="rounded-2xl p-6 relative overflow-hidden"
          style={{
            background: "var(--bg-secondary)",
            border: "1px solid var(--border)",
            boxShadow: "var(--shadow-lg)",
          }}
          variants={item}
        >
          <div className="flex items-center gap-2 mb-6">
            <div
              className="flex items-center justify-center w-6 h-6 rounded-md"
              style={{ background: "var(--accent-primary-soft)" }}
            >
              <Sparkles size={12} style={{ color: "var(--accent-primary)" }} />
            </div>
            <span className="text-xs font-semibold tracking-wide uppercase" style={{ color: "var(--text-tertiary)" }}>
              Quick Setup
            </span>
          </div>

          {/* Provider Selector */}
          <div
            className="flex gap-1 mb-6 p-1 rounded-xl"
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
                className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium relative"
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
                className="block text-xs font-semibold uppercase tracking-wider mb-2"
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
                  placeholder={
                    provider === "openai" ? "sk-..." : "Google AI API key"
                  }
                  className="w-full rounded-xl px-3 py-3 pl-10 text-sm outline-none transition-all duration-200"
                  style={{
                    background: "var(--bg-surface)",
                    border: `1px solid ${focused ? "var(--accent-primary)" : "var(--border)"}`,
                    color: "var(--text-primary)",
                    boxShadow: focused ? "0 0 0 3px var(--accent-primary-soft)" : "none",
                  }}
                  autoComplete="off"
                />
              </div>
              <p className="mt-2 text-xs flex items-center gap-1.5" style={{ color: "var(--text-muted)" }}>
                <Shield size={10} />
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
              className="w-full flex items-center justify-center gap-2 rounded-xl px-4 py-3.5 text-sm font-semibold"
              style={{
                background: "var(--gradient-accent)",
                color: "#fff",
                boxShadow: "var(--shadow-glow-teal)",
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
            className="inline-flex items-center gap-2 text-sm transition-colors"
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
        transition={{ duration: 0.5, ease: EASE_OUT }}
      >
        <button
          type="button"
          onClick={onBack}
          className="mb-4 text-sm flex items-center gap-1 transition-colors"
          style={{ color: "var(--text-secondary)" }}
        >
          ← Back to setup
        </button>

        <div
          className="rounded-2xl p-6"
          style={{
            background: "var(--bg-secondary)",
            border: "1px solid var(--border)",
            boxShadow: "var(--shadow-lg)",
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
              className="w-full rounded-xl px-4 py-3 text-sm outline-none transition-all duration-200 focus:ring-2 focus:ring-[var(--accent-primary)]"
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
              className="w-full rounded-xl px-4 py-3 text-sm outline-none transition-all duration-200 focus:ring-2 focus:ring-[var(--accent-primary)]"
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
              className="w-full rounded-xl px-4 py-3 text-sm font-semibold"
              style={{
                background: "var(--gradient-accent)",
                color: "#fff",
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

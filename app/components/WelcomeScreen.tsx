"use client";

import React, { useState } from "react";
import { FileText, KeyRound, ArrowRight, Sparkles, UserCircle } from "lucide-react";
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
      className="flex min-h-screen items-center justify-center px-4 py-10"
      style={{
        background:
          "radial-gradient(circle at top left, rgba(59,130,246,0.15), transparent 30%), radial-gradient(circle at bottom right, rgba(16,185,129,0.12), transparent 25%), var(--bg-primary)",
      }}
    >
      <div className="w-full max-w-md">
        {/* Header */}
        <div className="text-center mb-8">
          <div
            className="inline-flex items-center justify-center rounded-2xl mb-4"
            style={{
              width: 64,
              height: 64,
              background: "linear-gradient(135deg, var(--accent-soft), var(--bg-surface))",
              border: "1px solid var(--border-accent)",
            }}
          >
            <FileText size={28} style={{ color: "var(--accent)" }} />
          </div>
          <h1 className="text-2xl font-semibold mb-2" style={{ color: "var(--text-primary)" }}>
            Document RAG
          </h1>
          <p className="text-sm" style={{ color: "var(--text-secondary)" }}>
            Upload documents, ask questions, get grounded answers
          </p>
        </div>

        {/* Setup Card */}
        <div
          className="rounded-2xl border p-6"
          style={{ borderColor: "var(--border)", background: "var(--bg-secondary)" }}
        >
          <div className="flex items-center gap-2 mb-6">
            <Sparkles size={16} style={{ color: "var(--accent)" }} />
            <span className="text-sm font-medium" style={{ color: "var(--text-primary)" }}>
              Quick Setup
            </span>
          </div>

          {/* Provider Selector */}
          <div className="flex gap-2 mb-6 p-1 rounded-xl" style={{ background: "var(--bg-surface)" }}>
            <button
              type="button"
              onClick={() => setProvider("openai")}
              className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium transition-all"
              style={{
                background: provider === "openai" ? "var(--accent)" : "transparent",
                color: provider === "openai" ? "var(--accent-fg)" : "var(--text-secondary)",
              }}
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
                <path d="M22.282 9.821c.55-.443.55-1.295 0-1.738l-8.936-7.192c-.55-.443-1.318-.332-1.768.246l-8.936 11.929c-.45.579-.45 1.43 0 2.008l8.936 11.929c.45.578 1.218.689 1.768.246l8.936-7.192c.55-.443.55-1.295 0-1.738l-8.936-7.192z" />
              </svg>
              OpenAI
            </button>
            <button
              type="button"
              onClick={() => setProvider("gemini")}
              className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium transition-all"
              style={{
                background: provider === "gemini" ? "var(--accent)" : "transparent",
                color: provider === "gemini" ? "var(--accent-fg)" : "var(--text-secondary)",
              }}
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
                <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 17.93c-3.95-.49-7-3.85-7-7.93 0-.62.08-1.21.21-1.79L9 15v1c0 1.1.9 2 2 2v1.93zm6.9-2.54c-.26-.81-1-1.39-1.9-1.39h-1v-3c0-.55-.45-1-1-1H8v-2h2c.55 0 1-.45 1-1V7h2c1.1 0 2-.9 2-2v-.41c2.93 1.19 5 4.06 5 7.41 0 2.08-.8 3.97-2.1 5.39z" />
              </svg>
              Gemini
            </button>
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
                  <KeyRound size={16} />
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
                  className="w-full rounded-xl px-3 py-3 pl-10 text-sm outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]"
                  style={{
                    background: "var(--bg-surface)",
                    border: "1px solid var(--border)",
                    color: "var(--text-primary)",
                  }}
                  autoComplete="off"
                />
              </div>
              <p className="mt-2 text-xs" style={{ color: "var(--text-muted)" }}>
                Your API key is stored locally in your browser and never sent to our servers.
              </p>
            </div>

            {error && (
              <div
                className="rounded-lg px-3 py-2 text-sm"
                style={{ background: "var(--error-soft)", color: "var(--error)" }}
              >
                {error}
              </div>
            )}

            <button
              type="submit"
              className="w-full flex items-center justify-center gap-2 rounded-xl px-4 py-3 text-sm font-medium transition-all"
              style={{
                background: "var(--accent)",
                color: "var(--accent-fg)",
              }}
            >
              Get Started
              <ArrowRight size={16} />
            </button>
          </form>
        </div>

        {/* Optional Login */}
        <div className="mt-6 text-center">
          <button
            type="button"
            onClick={() => setShowLogin(true)}
            className="inline-flex items-center gap-2 text-sm"
            style={{ color: "var(--text-secondary)" }}
          >
            <UserCircle size={16} />
            Sign in for cross-device sync
          </button>
        </div>
      </div>
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
      style={{
        background:
          "radial-gradient(circle at top left, rgba(59,130,246,0.15), transparent 30%), radial-gradient(circle at bottom right, rgba(16,185,129,0.12), transparent 25%), var(--bg-primary)",
      }}
    >
      <div className="w-full max-w-md">
        <button
          type="button"
          onClick={onBack}
          className="mb-4 text-sm flex items-center gap-1"
          style={{ color: "var(--text-secondary)" }}
        >
          ← Back to setup
        </button>

        <div
          className="rounded-2xl border p-6"
          style={{ borderColor: "var(--border)", background: "var(--bg-secondary)" }}
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
              className="w-full rounded-xl px-4 py-3 text-sm outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]"
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
              className="w-full rounded-xl px-4 py-3 text-sm outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]"
              style={{
                background: "var(--bg-surface)",
                border: "1px solid var(--border)",
                color: "var(--text-primary)",
              }}
            />

            {error && (
              <div
                className="rounded-lg px-3 py-2 text-sm"
                style={{ background: "var(--error-soft)", color: "var(--error)" }}
              >
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full rounded-xl px-4 py-3 text-sm font-medium"
              style={{
                background: "var(--accent)",
                color: "var(--accent-fg)",
                opacity: loading ? 0.7 : 1,
              }}
            >
              {loading ? "Working..." : mode === "login" ? "Sign In" : "Create Account"}
            </button>
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
      </div>
    </div>
  );
}

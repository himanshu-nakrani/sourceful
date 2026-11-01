"use client";

import React, { useState } from "react";
import { ArrowRight } from "lucide-react";
import { type AuthUser, type Provider } from "../lib/api";
import { useStore, DEFAULT_CHAT, DEFAULT_EMBEDDING } from "../lib/store";
import AuthForm from "./AuthForm";
import Brand from "./Brand";
import { Button, TextField } from "./ui";

interface WelcomeScreenProps {
  onComplete: () => void;
}

/**
 * Render the initial Quick Setup console to choose an LLM provider, enter an
 * API key, optionally sign in, and complete initial app setup.
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

  /* Same contract as the old inline LoginPrompt: signing in marks setup complete. */
  const handleAuthenticated = (user: AuthUser) => {
    dispatch({ type: "SET_CURRENT_USER", payload: user });
    dispatch({ type: "SET_SETUP_COMPLETE", payload: true });
  };

  if (showLogin) {
    return (
      <main className="min-h-[100dvh]" style={{ background: "var(--bg-primary)" }}>
        <header className="border-b px-6 py-5 sm:px-10" style={{ borderColor: "var(--border)" }}>
          <div className="mx-auto flex max-w-6xl items-center justify-between gap-4">
            <Brand />
            <span className="text-[10px] font-medium tracking-[0.14em]" style={{ color: "var(--text-muted)" }}>ACCOUNT</span>
          </div>
        </header>
        <section className="mx-auto w-full max-w-[500px] px-6 py-10 sm:px-8 sm:py-16">
          <AuthForm
            onSwitchToSetup={() => setShowLogin(false)}
            onAuthenticated={handleAuthenticated}
          />
        </section>
      </main>
    );
  }

  return (
    <main className="min-h-[100dvh]" style={{ background: "var(--bg-primary)" }}>
      <header className="border-b px-6 py-5 sm:px-10" style={{ borderColor: "var(--border)" }}>
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-4">
          <Brand />
          <span className="text-[10px] font-medium tracking-[0.14em]" style={{ color: "var(--text-muted)" }}>SETUP</span>
        </div>
      </header>

      <div className="mx-auto grid w-full max-w-6xl gap-10 px-6 py-10 sm:px-10 lg:grid-cols-[minmax(0,0.95fr)_minmax(360px,1.05fr)] lg:gap-16 lg:py-20">
        <section className="max-w-md">
          <p className="text-[10px] font-medium tracking-[0.14em]" style={{ color: "var(--text-muted)" }}>
            MODEL CONFIGURATION
          </p>
          <h1
            className="mt-4 text-[38px] leading-[1.06] tracking-[-0.035em] sm:text-[44px]"
            style={{ color: "var(--text-primary)", fontFamily: "var(--font-editorial), Georgia, serif" }}
          >
            Connect a model
          </h1>
          <p className="mt-4 max-w-[360px] text-[14px] leading-6" style={{ color: "var(--text-secondary)" }}>
            Choose a provider and enter an API key to use it for document answers.
          </p>
        </section>

        <section
          className="w-full max-w-xl border-t pt-6 lg:justify-self-end lg:border-l lg:border-t-0 lg:pl-10 lg:pt-0"
          style={{ borderColor: "var(--border)" }}
          aria-label="Provider configuration"
        >
          <form onSubmit={handleSubmit} className="space-y-6">
            <div
              role="group"
              aria-label="Provider"
              className="flex gap-5 border-b"
              style={{ borderColor: "var(--border)" }}
            >
              {(["openai", "gemini"] as const).map((p) => {
                const active = provider === p;
                return (
                  <button
                    key={p}
                    type="button"
                    onClick={() => setProvider(p)}
                    aria-pressed={active}
                    className="focus-ring -mb-px rounded-t-[6px] border-b-2 px-1 py-2 text-[13px] font-medium"
                    style={{
                      background: "transparent",
                      borderBottomColor: active ? "var(--accent-primary)" : "transparent",
                      color: active ? "var(--text-primary)" : "var(--text-secondary)",
                    }}
                  >
                    {p === "openai" ? "OpenAI" : "Gemini"}
                  </button>
                );
              })}
            </div>

            <TextField
              label={provider === "openai" ? "OpenAI API key" : "Google AI API key"}
              hint="Stored for this browser session. Sent only to your self-hosted API with your requests."
              error={error}
              mono
              type="password"
              value={apiKey}
              onChange={(event) => {
                setApiKey(event.target.value);
                setError(null);
              }}
              placeholder={provider === "openai" ? "sk-..." : "Google AI API key"}
              autoComplete="off"
            />

            <Button type="submit" variant="primary" size="lg" className="w-full">
              Open workspace
              <ArrowRight size={15} aria-hidden="true" />
            </Button>
          </form>

          <div className="mt-7 border-t pt-5" style={{ borderColor: "var(--border)" }}>
            <p className="text-[13px]" style={{ color: "var(--text-secondary)" }}>Already have an account?</p>
            <Button
              type="button"
              variant="ghost"
              size="lg"
              className="mt-1"
              onClick={() => setShowLogin(true)}
            >
              Sign in
            </Button>
          </div>
        </section>
      </div>
    </main>
  );
}

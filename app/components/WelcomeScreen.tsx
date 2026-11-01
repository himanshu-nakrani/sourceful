"use client";

import React, { useState } from "react";
import { motion } from "framer-motion";
import { ArrowRight, ShieldCheck } from "lucide-react";
import { type AuthUser, type Provider } from "../lib/api";
import { staggerContainer, staggerItem } from "../lib/motion";
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
      <div
        className="flex min-h-[100dvh] flex-col items-center justify-center gap-8 px-5 py-10"
        style={{ background: "var(--bg-primary)" }}
      >
        <div className="w-full max-w-md">
          <AuthForm
            compact
            onSwitchToSetup={() => setShowLogin(false)}
            onAuthenticated={handleAuthenticated}
          />
        </div>
      </div>
    );
  }

  return (
    <div
      className="flex min-h-[100dvh] flex-col items-center justify-center gap-8 px-5 py-10"
      style={{ background: "var(--bg-primary)" }}
    >
      <Brand />
      <motion.div
        className="w-full max-w-[440px] rounded-2xl p-7 sm:p-9"
        style={{
          background: "var(--bg-surface)",
          border: "1px solid var(--border)",
          boxShadow: "var(--shadow-md)",
        }}
        variants={staggerContainer}
        initial="hidden"
        animate="show"
      >
        <motion.p
          variants={staggerItem}
          className="text-[10px] font-semibold uppercase tracking-widest"
          style={{ color: "var(--text-muted)" }}
        >
          Make it yours
        </motion.p>
        <motion.h1
          variants={staggerItem}
          className="display mt-3 text-[28px] font-semibold tracking-tight"
          style={{ color: "var(--text-primary)" }}
        >
          Connect your AI
        </motion.h1>
        <motion.p
          variants={staggerItem}
          className="mt-2 text-sm leading-relaxed"
          style={{ color: "var(--text-secondary)" }}
        >
          Choose a provider and bring your own key. A clearer view of your documents is one step away.
        </motion.p>

        <motion.form
          variants={staggerItem}
          onSubmit={handleSubmit}
          className="mt-7 flex flex-col gap-5"
        >
          {/* Provider segmented control */}
          <div
            role="group"
            aria-label="Provider"
            className="grid grid-cols-2 gap-1 rounded-lg p-1"
            style={{ background: "var(--bg-secondary)" }}
          >
            {(["openai", "gemini"] as const).map((p) => {
              const active = provider === p;
              return (
                <button
                  key={p}
                  type="button"
                  onClick={() => setProvider(p)}
                  aria-pressed={active}
                  className="rounded-md px-4 py-2 text-[13px] font-medium transition-colors focus-ring"
                  style={{
                    background: active ? "var(--bg-surface)" : "transparent",
                    color: active ? "var(--text-primary)" : "var(--text-secondary)",
                    boxShadow: active ? "var(--shadow-xs)" : "none",
                  }}
                >
                  {p === "openai" ? "OpenAI" : "Gemini"}
                </button>
              );
            })}
          </div>

          {/* API key */}
          <TextField
            label={provider === "openai" ? "OpenAI API key" : "Google AI API key"}
            hint="Stored for this browser session. Sent only to your self-hosted API with your requests."
            error={error}
            mono
            type="password"
            value={apiKey}
            onChange={(e) => {
              setApiKey(e.target.value);
              setError(null);
            }}
            placeholder={provider === "openai" ? "sk-..." : "Google AI API key"}
            autoComplete="off"
          />

          <Button type="submit" variant="primary" size="lg" className="w-full">
            Open workspace
            <ArrowRight size={15} />
          </Button>
        </motion.form>

        <motion.p variants={staggerItem} className="mt-5 flex items-center justify-center gap-1.5 text-xs" style={{ color: "var(--text-muted)" }}>
          <ShieldCheck size={13} /> Your models. Your control.
        </motion.p>
        <motion.div variants={staggerItem} className="mt-4">
          <Button
            type="button"
            variant="ghost"
            size="lg"
            className="w-full"
            onClick={() => setShowLogin(true)}
          >
            Sign in instead
          </Button>
        </motion.div>
      </motion.div>
    </div>
  );
}

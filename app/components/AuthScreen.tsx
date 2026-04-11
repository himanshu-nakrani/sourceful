"use client";

import React from "react";
import { LockKeyhole, Users } from "lucide-react";

import { login, signup } from "../lib/api";
import { useStore } from "../lib/store";

export default function AuthScreen() {
  const { dispatch } = useStore();
  const [mode, setMode] = React.useState<"login" | "signup">("login");
  const [email, setEmail] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setLoading(true);
    try {
      const user =
        mode === "login"
          ? await login(email.trim(), password)
          : await signup(email.trim(), password);
      dispatch({ type: "SET_CURRENT_USER", payload: user });
      setError(null);
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : "Authentication failed.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      className="flex min-h-screen items-center justify-center px-4 py-10"
      style={{
        background:
          "radial-gradient(circle at top left, rgba(59,130,246,0.18), transparent 28%), radial-gradient(circle at bottom right, rgba(16,185,129,0.14), transparent 24%), var(--bg-primary)",
      }}
    >
      <div className="grid w-full max-w-5xl gap-6 lg:grid-cols-[1.2fr_0.8fr]">
        <section
          className="rounded-[32px] border px-7 py-8"
          style={{ borderColor: "var(--border)", background: "rgba(14,14,17,0.9)" }}
        >
          {/* [typography] Standardized tracking to tracking-wider for consistency */}
          <p className="text-xs font-semibold uppercase tracking-wider" style={{ color: "var(--text-tertiary)" }}>
            Secure Workspace
          </p>
          <h1 className="mt-3 text-4xl font-semibold leading-tight" style={{ color: "var(--text-primary)" }}>
            Sign in to manage documents, ask grounded questions, and track shared insights.
          </h1>
          <p className="mt-4 max-w-xl text-sm leading-7" style={{ color: "var(--text-secondary)" }}>
            Email and password auth is now the default entry point. Every signed-in user gets access to the same high-level analytics dashboard, while document and chat data stay tied to authenticated accounts.
          </p>

          <div className="mt-8 grid gap-4 md:grid-cols-2">
            <FeatureCard
              icon={<LockKeyhole size={16} />}
              title="Private document access"
              description="Uploads, conversations, and reruns stay scoped to the authenticated user."
            />
            {/* [flow] Removed hardcoded admin credentials — replaced with safe description */}
            <FeatureCard
              icon={<Users size={16} />}
              title="Multi-user workspace"
              description="Admins can manage users, roles, and permissions from the settings panel."
            />
          </div>
        </section>

        <section
          className="rounded-[32px] border px-6 py-7"
          style={{ borderColor: "var(--border)", background: "var(--bg-secondary)" }}
        >
          {/* [a11y] Added role="tablist" and role="tab" with aria-selected for screen reader support */}
          <div className="inline-flex rounded-full p-1" role="tablist" style={{ background: "var(--bg-surface)", border: "1px solid var(--border)" }}>
            {(["login", "signup"] as const).map((item) => (
              <button
                key={item}
                type="button"
                role="tab"
                aria-selected={mode === item}
                onClick={() => setMode(item)}
                className="rounded-full px-4 py-2 text-sm"
                style={{
                  background: mode === item ? "var(--accent)" : "transparent",
                  color: mode === item ? "var(--accent-fg)" : "var(--text-secondary)",
                }}
              >
                {item === "login" ? "Login" : "Sign up"}
              </button>
            ))}
          </div>

          <form className="mt-6 flex flex-col gap-4" onSubmit={submit}>
            <label className="text-sm" style={{ color: "var(--text-secondary)" }}>
              Email
              <input
                required
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                className="mt-2 w-full rounded-xl px-4 py-3 outline-none"
                style={{ background: "var(--bg-surface)", border: "1px solid var(--border)", color: "var(--text-primary)" }}
                placeholder="you@example.com"
                autoComplete="email"
              />
            </label>
            <label className="text-sm" style={{ color: "var(--text-secondary)" }}>
              Password
              <input
                required
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                className="mt-2 w-full rounded-xl px-4 py-3 outline-none"
                style={{ background: "var(--bg-surface)", border: "1px solid var(--border)", color: "var(--text-primary)" }}
                placeholder={mode === "login" ? "Enter your password" : "Minimum 8 characters"}
                autoComplete={mode === "login" ? "current-password" : "new-password"}
              />
            </label>

            {error ? (
              <div className="rounded-xl px-4 py-3 text-sm" style={{ background: "var(--error-soft)", color: "var(--error)" }}>
                {error}
              </div>
            ) : null}

            <button
              type="submit"
              disabled={loading}
              className="rounded-xl px-4 py-3 text-sm font-medium"
              style={{
                background: "var(--accent)",
                color: "var(--accent-fg)",
                opacity: loading ? 0.7 : 1,
              }}
            >
              {loading ? "Working..." : mode === "login" ? "Login" : "Create account"}
            </button>
          </form>
        </section>
      </div>
    </div>
  );
}

function FeatureCard({
  icon,
  title,
  description,
}: {
  icon: React.ReactNode;
  title: string;
  description: string;
}) {
  return (
    <div className="rounded-2xl px-4 py-4" style={{ background: "var(--bg-surface)", border: "1px solid var(--border)" }}>
      <div className="inline-flex rounded-lg p-2" style={{ background: "rgba(59,130,246,0.14)", color: "#93c5fd" }}>
        {icon}
      </div>
      <h2 className="mt-4 text-base font-semibold" style={{ color: "var(--text-primary)" }}>
        {title}
      </h2>
      <p className="mt-2 text-sm leading-6" style={{ color: "var(--text-secondary)" }}>
        {description}
      </p>
    </div>
  );
}

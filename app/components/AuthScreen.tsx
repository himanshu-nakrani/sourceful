"use client";

import React from "react";
import { motion, AnimatePresence } from "framer-motion";
import { LockKeyhole, Users } from "lucide-react";

import { getGoogleOAuthClientId, googleLogin, login, signup } from "../lib/api";
import { EASE_OUT } from "../lib/motion";
import { useStore } from "../lib/store";

const container = {
  hidden: { opacity: 0 },
  show: { opacity: 1, transition: { staggerChildren: 0.1, delayChildren: 0.15 } },
};

const item = {
  hidden: { opacity: 0, y: 16, filter: "blur(4px)" },
  show: { opacity: 1, y: 0, filter: "blur(0px)", transition: { duration: 0.5, ease: EASE_OUT } },
};

export default function AuthScreen() {
  const { dispatch } = useStore();
  const [mode, setMode] = React.useState<"login" | "signup">("login");
  const [email, setEmail] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [googleClientId, setGoogleClientId] = React.useState<string | null>(null);

  /* ---- Fetch Google OAuth client_id from backend ---- */
  React.useEffect(() => {
    getGoogleOAuthClientId()
      .then((clientId) => {
        if (clientId) setGoogleClientId(clientId);
      })
      .catch(() => { /* Google sign-in will just be hidden */ });
  }, []);

  /* ---- handle Google OAuth redirect back ---- */
  React.useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const code = params.get("code");
    if (!code) return;

    // Clean URL immediately
    window.history.replaceState({}, "", window.location.pathname);

    setLoading(true);
    const redirectUri = `${window.location.origin}${window.location.pathname}`;
    googleLogin(code, redirectUri)
      .then((user) => {
        dispatch({ type: "SET_CURRENT_USER", payload: user });
        setError(null);
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : "Google sign-in failed.");
      })
      .finally(() => setLoading(false));
  }, [dispatch]);

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

  const handleGoogleSignIn = () => {
    if (!googleClientId) return;
    const redirectUri = `${window.location.origin}${window.location.pathname}`;
    const scope = "openid email profile";
    const url =
      `https://accounts.google.com/o/oauth2/v2/auth?` +
      `client_id=${encodeURIComponent(googleClientId)}` +
      `&redirect_uri=${encodeURIComponent(redirectUri)}` +
      `&response_type=code` +
      `&scope=${encodeURIComponent(scope)}` +
      `&access_type=offline` +
      `&prompt=consent`;
    window.location.href = url;
  };

  return (
    <div
      className="flex min-h-screen items-center justify-center px-4 py-10 relative overflow-hidden"
      style={{ background: "var(--bg-primary)" }}
    >
      {/* Ambient orbs */}
      <motion.div
        className="absolute top-[-15%] left-[-8%] w-[450px] h-[450px] rounded-full pointer-events-none"
        style={{ background: "radial-gradient(circle, rgba(99,102,241,0.12), transparent 70%)" }}
        animate={{ scale: [1, 1.1, 1], x: [0, 20, 0] }}
        transition={{ duration: 8, repeat: Infinity, ease: "easeInOut" }}
      />
      <motion.div
        className="absolute bottom-[-10%] right-[-8%] w-[400px] h-[400px] rounded-full pointer-events-none"
        style={{ background: "radial-gradient(circle, rgba(34,197,94,0.08), transparent 70%)" }}
        animate={{ scale: [1, 1.12, 1], x: [0, -15, 0] }}
        transition={{ duration: 10, repeat: Infinity, ease: "easeInOut" }}
      />

      <motion.div
        className="grid w-full max-w-5xl gap-6 lg:grid-cols-[1.2fr_0.8fr] relative z-10"
        variants={container}
        initial="hidden"
        animate="show"
      >
        <motion.section
          className="rounded-2xl px-5 sm:px-7 py-6 sm:py-8"
          style={{
            background: "var(--bg-secondary)",
            border: "1px solid var(--border)",
          }}
          variants={item}
        >
          <p className="text-[10px] font-semibold uppercase tracking-widest" style={{ color: "var(--text-muted)" }}>
            Secure Workspace
          </p>
          <h1
            className="mt-3 text-2xl sm:text-3xl font-semibold leading-tight"
            style={{ color: "var(--text-primary)", letterSpacing: "-0.03em" }}
          >
            Sign in to manage documents, ask grounded questions, and track shared insights.
          </h1>
          <p className="mt-4 max-w-xl text-sm leading-7" style={{ color: "var(--text-secondary)" }}>
            Email and password auth is the default entry point. Every signed-in user gets access to analytics, while document and chat data stay tied to authenticated accounts.
          </p>

          <div className="mt-8 grid gap-4 sm:grid-cols-2">
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
        </motion.section>

        <motion.section
          className="rounded-2xl px-5 sm:px-6 py-6 sm:py-7"
          style={{
            background: "var(--bg-secondary)",
            border: "1px solid var(--border)",
          }}
          variants={item}
        >
          {/* [a11y] Added role="tablist" and role="tab" with aria-selected for screen reader support */}
          <div className="inline-flex rounded-full p-1" role="tablist" style={{ background: "var(--bg-surface)", border: "1px solid var(--border)" }}>
            {(["login", "signup"] as const).map((tabItem) => (
              <motion.button
                key={tabItem}
                type="button"
                role="tab"
                aria-selected={mode === tabItem}
                onClick={() => setMode(tabItem)}
                className="rounded-full px-4 py-2 text-sm"
                style={{
                  background: mode === tabItem ? "var(--accent)" : "transparent",
                  color: mode === tabItem ? "var(--accent-fg)" : "var(--text-secondary)",
                }}
                whileTap={{ scale: 0.95 }}
              >
                {tabItem === "login" ? "Login" : "Sign up"}
              </motion.button>
            ))}
          </div>

          <form className="mt-6 flex flex-col gap-4" onSubmit={submit}>
            <label className="text-sm" style={{ color: "var(--text-secondary)" }}>
              Email
              <input
                required
                type="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                className="mt-2 w-full rounded-xl px-4 py-3 outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] transition-all duration-200"
                style={{ background: "var(--bg-surface)", border: "1px solid var(--border)", color: "var(--text-primary)" }}
                placeholder="you@example.com"
                autoComplete="email"
              />
            </label>
            <label className="text-sm" style={{ color: "var(--text-secondary)" }}>
              Password
              <input
                required
                minLength={mode === "signup" ? 8 : undefined}
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                className="mt-2 w-full rounded-xl px-4 py-3 outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] transition-all duration-200"
                style={{ background: "var(--bg-surface)", border: "1px solid var(--border)", color: "var(--text-primary)" }}
                placeholder={mode === "login" ? "Enter your password" : "Minimum 8 characters"}
                autoComplete={mode === "login" ? "current-password" : "new-password"}
              />
            </label>

            <AnimatePresence>
              {error ? (
                <motion.div
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: "auto" }}
                  exit={{ opacity: 0, height: 0 }}
                  className="rounded-xl px-4 py-3 text-sm overflow-hidden"
                  style={{ background: "var(--error-soft)", color: "var(--error)" }}
                >
                  {error}
                </motion.div>
              ) : null}
            </AnimatePresence>

            <motion.button
              type="submit"
              disabled={loading}
              className="rounded-xl px-4 py-3 text-sm font-medium"
              style={{
                background: "var(--accent)",
                color: "var(--accent-fg)",
                opacity: loading ? 0.7 : 1,
              }}
              whileHover={{ scale: 1.01 }}
              whileTap={{ scale: 0.97 }}
            >
              {loading ? "Working..." : mode === "login" ? "Login" : "Create account"}
            </motion.button>
          </form>

          {googleClientId ? (
            <>
              <div className="flex items-center gap-3 my-5">
                <div className="flex-1 h-px" style={{ background: "var(--border)" }} />
                <span className="text-[10px]" style={{ color: "var(--text-muted)" }}>or</span>
                <div className="flex-1 h-px" style={{ background: "var(--border)" }} />
              </div>

              <motion.button
                type="button"
                onClick={handleGoogleSignIn}
                disabled={loading}
                className="w-full flex items-center justify-center gap-3 rounded-xl px-4 py-3 text-sm font-medium"
                style={{
                  background: "var(--bg-surface)",
                  border: "1px solid var(--border)",
                  color: "var(--text-primary)",
                  opacity: loading ? 0.7 : 1,
                }}
                whileHover={{ borderColor: "var(--border-hover)" }}
                whileTap={{ scale: 0.97 }}
              >
                <svg width="18" height="18" viewBox="0 0 48 48">
                  <path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"/>
                  <path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"/>
                  <path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"/>
                  <path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"/>
                </svg>
                Continue with Google
              </motion.button>
            </>
          ) : null}
        </motion.section>
      </motion.div>
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
    <motion.div
      className="rounded-xl px-4 py-4"
      style={{ background: "var(--bg-surface)", border: "1px solid var(--border)" }}
      whileHover={{ borderColor: "var(--border-hover)", y: -2 }}
      transition={{ duration: 0.2 }}
    >
      <div className="inline-flex rounded-lg p-2" style={{ background: "var(--accent-brand-soft)", color: "var(--accent-brand)" }}>
        {icon}
      </div>
      <h2 className="mt-4 text-sm font-semibold" style={{ color: "var(--text-primary)", letterSpacing: "-0.01em" }}>
        {title}
      </h2>
      <p className="mt-2 text-xs leading-relaxed" style={{ color: "var(--text-tertiary)" }}>
        {description}
      </p>
    </motion.div>
  );
}

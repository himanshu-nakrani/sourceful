"use client";

import React from "react";
import { ArrowLeft } from "lucide-react";

import type { AuthUser } from "../lib/api";
import { startGoogleOAuth } from "../lib/oauth";
import OAuthCallback from "./OAuthCallback";
import { Button, ErrorBanner, TextField } from "./ui";

/** Google brand mark — third-party logo colors, kept as-is. */
function GoogleMark() {
  return (
    <svg width="16" height="16" viewBox="0 0 48 48" aria-hidden="true">
      <path
        fill="#EA4335"
        d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"
      />
      <path
        fill="#4285F4"
        d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"
      />
      <path
        fill="#FBBC05"
        d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"
      />
      <path
        fill="#34A853"
        d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"
      />
    </svg>
  );
}

/**
 * Reusable email/password auth card (login + signup) with optional Google
 * OAuth. The single source of truth for credential auth in the app: hosts the
 * OAuth client-id lookup, the `?code=` redirect-return handler, and the
 * double-submit guard (Fix 6.7.1). Authentication results are handed to the
 * caller via `onAuthenticated` — the caller decides which store actions follow.
 */
export default function AuthForm({
  onAuthenticated,
  compact = false,
  onSwitchToSetup,
}: {
  onAuthenticated: (user: AuthUser) => void;
  compact?: boolean;
  onSwitchToSetup?: () => void;
}) {
  const [mode, setMode] = React.useState<"login" | "signup">("login");
  const [email, setEmail] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [googleClientId, setGoogleClientId] = React.useState<string | null>(null);

  // Keep the latest callback without re-triggering the mount-only effects below.
  const onAuthenticatedRef = React.useRef(onAuthenticated);
  React.useEffect(() => {
    onAuthenticatedRef.current = onAuthenticated;
  }, [onAuthenticated]);

  /* ---- Fetch Google OAuth client_id from backend (button stays hidden on failure) ---- */
  React.useEffect(() => {
    let cancelled = false;
    import("../lib/api")
      .then((api) => api.getGoogleOAuthClientId())
      .then((clientId) => {
        if (!cancelled && clientId) setGoogleClientId(clientId);
      })
      .catch(() => {
        /* Google sign-in stays hidden */
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const handleOAuthAuthenticated = React.useCallback(
    (user: AuthUser) => {
      setError(null);
      setLoading(false);
      onAuthenticatedRef.current(user);
    },
    [],
  );

  const handleOAuthError = React.useCallback((message: string) => {
    setLoading(false);
    setError(message);
  }, []);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (loading) return; // [Fix 6.7.1] double-submit guard
    setLoading(true);
    try {
      const { login, signup } = await import("../lib/api");
      const user =
        mode === "login"
          ? await login(email.trim(), password)
          : await signup(email.trim(), password);
      setError(null);
      onAuthenticated(user);
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : "Authentication failed.");
    } finally {
      setLoading(false);
    }
  };

  const handleGoogleSignIn = () => {
    if (!googleClientId || loading) return;
    setError(null);
    if (!startGoogleOAuth(googleClientId)) {
      setError("Could not start Google sign-in in this browser.");
    }
  };

  return (
    <div
      className={compact ? \"rounded-[6px] border p-5 sm:p-6\" : undefined}
      style={compact ? { background: \"var(--bg-surface)\", borderColor: \"var(--border)\" } : undefined}
    >
      <OAuthCallback onAuthenticated={handleOAuthAuthenticated} onError={handleOAuthError} />
      <div className=\"w-full\">
        {onSwitchToSetup ? (
          <button
            type=\"button\"
            onClick={onSwitchToSetup}
            className=\"focus-ring mb-6 inline-flex items-center gap-2 rounded-[6px] text-[12px] font-medium\"
            style={{ color: \"var(--text-tertiary)\" }}
          >
            <ArrowLeft size={14} aria-hidden=\"true\" />
            Back to setup
          </button>
        ) : null}

        <header className=\"mb-6\">
          <h2
            className=\"text-[30px] leading-tight tracking-[-0.025em]\"
            style={{ color: \"var(--text-primary)\", fontFamily: \"var(--font-editorial), Georgia, serif\" }}
          >
            {mode === \"login\" ? \"Sign in\" : \"Create an account\"}
          </h2>
          <p className=\"mt-2 text-[13px] leading-5\" style={{ color: \"var(--text-secondary)\" }}>
            {mode === \"login\" ? \"Enter your email and password to continue.\" : \"Create an account with your email and a password.\"}
          </p>
        </header>

        <div
          role=\"group\"
          aria-label=\"Authentication mode\"
          className=\"mb-6 flex gap-5 border-b\"
          style={{ borderColor: \"var(--border)\" }}
        >
          {([\"login\", \"signup\"] as const).map((tab) => {
            const active = mode === tab;
            return (
              <button
                key={tab}
                type=\"button\"
                aria-pressed={active}
                disabled={loading}
                onClick={() => setMode(tab)}
                className=\"focus-ring -mb-px rounded-t-[6px] border-b-2 px-1 py-2 text-[13px] font-medium\"
                style={{
                  background: \"transparent\",
                  borderBottomColor: active ? \"var(--accent-primary)\" : \"transparent\",
                  color: active ? \"var(--text-primary)\" : \"var(--text-secondary)\",
                }}
              >
                {tab === \"login\" ? \"Sign in\" : \"Create account\"}
              </button>
            );
          })}
        </div>

        <form onSubmit={submit} className=\"grid gap-4\">
          <TextField
            label=\"Email\"
            type=\"email\"
            required
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            placeholder=\"you@example.com\"
            autoComplete=\"email\"
          />
          <TextField
            label=\"Password\"
            type=\"password\"
            required
            minLength={mode === \"signup\" ? 8 : undefined}
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            placeholder={mode === \"login\" ? \"Enter your password\" : \"Minimum 8 characters\"}
            autoComplete={mode === \"login\" ? \"current-password\" : \"new-password\"}
          />

          {error ? <ErrorBanner message={error} /> : null}

          <Button type=\"submit\" variant=\"primary\" size=\"lg\" className=\"w-full\" disabled={loading}>
            {loading ? \"One moment…\" : mode === \"login\" ? \"Sign in\" : \"Create account\"}
          </Button>
        </form>

        {googleClientId ? (
          <div className=\"mt-5\">
            <div className=\"mb-4 flex items-center gap-3\" aria-hidden=\"true\">
              <span className=\"h-px flex-1\" style={{ background: \"var(--border)\" }} />
              <span className=\"text-[11px]\" style={{ color: \"var(--text-muted)\" }}>or</span>
              <span className=\"h-px flex-1\" style={{ background: \"var(--border)\" }} />
            </div>
            <Button
              type=\"button\"
              variant=\"secondary\"
              size=\"lg\"
              className=\"w-full\"
              onClick={handleGoogleSignIn}
              disabled={loading}
            >
              <GoogleMark />
              Continue with Google
            </Button>
          </div>
        ) : null}
      </div>
    </div>
  );
}

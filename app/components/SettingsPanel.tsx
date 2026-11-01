"use client";

import React, { useEffect, useId, useMemo, useState } from "react";
import { useOnChange } from "../lib/use-on-change";
import { motion } from "framer-motion";
import { Check, ChevronDown, RotateCcw } from "lucide-react";
import { fetchModels, logout, type ModelsResponse, type Provider } from "../lib/api";
import { DEFAULT_CHAT, DEFAULT_EMBEDDING, useStore, type AppSettings } from "../lib/store";
import { transitionFast } from "../lib/motion";
import AuthForm from "./AuthForm";
import { Button, Modal, SelectField, SliderField, TextField, ToggleField } from "./ui";

interface SettingsPanelProps {
  open: boolean;
  onClose: () => void;
}

/**
 * Signal accent packs offered in the Display section. The hex values are the
 * pack colors themselves and are used only as swatch chip fills; everything
 * else routes through the `[data-accent]` token overrides in globals.css.
 */
const ACCENT_PACKS: { value: string; label: string; color: string }[] = [
  { value: "lime", label: "Lime", color: "#c6f24e" },
  { value: "pulse", label: "Pulse", color: "#67e8f9" },
  { value: "beam", label: "Beam", color: "#fbbf24" },
];

/**
 * Legacy persisted pack names map onto the nearest Signal pack (mirroring the
 * `[data-accent]` overrides in globals.css). Used only to highlight the active
 * swatch for users who saved a preference before the migration.
 */
const LEGACY_PACK_ALIASES: Record<string, string> = {
  terracotta: "lime",
  emerald: "pulse",
  amber: "beam",
};

/**
 * Drop the stale bearer token from sessionStorage.
 *
 * Local mirror of api.ts's private `updateStoredSession({ authToken: null })`
 * so a failed logout POST still signs the browser out locally instead of
 * leaving a dead token behind (UI half of Fix 6.4).
 */
function clearStoredAuthToken(): void {
  if (typeof window === "undefined") return;
  try {
    const raw = sessionStorage.getItem("rag-session");
    if (!raw) return;
    const parsed = JSON.parse(raw) as Record<string, unknown>;
    delete parsed.authToken;
    sessionStorage.setItem("rag-session", JSON.stringify(parsed));
  } catch {
    // Ignore storage errors — local sign-out proceeds regardless.
  }
}

/**
 * Render the settings panel as an accessible modal over the app.
 *
 * The panel configures provider credentials and models, display preferences
 * (theme, accent pack, contrast, motion), retrieval parameters, and optional
 * sign-in for cross-device sync. Credentials and model choices read from and
 * dispatch to the app store; the sign-in section embeds the shared
 * `AuthForm` (which owns the Google button and the double-submit guard).
 *
 * @param open - Whether the settings panel is visible
 * @param onClose - Callback invoked to close the panel (Done, Escape, backdrop)
 * @returns The settings modal element
 */
export default function SettingsPanel({ open, onClose }: SettingsPanelProps) {
  const { state, dispatch } = useStore();
  const { settings } = state;
  const user = state.currentUser;
  const [models, setModels] = useState<ModelsResponse | null>(null);
  const [modelsLoading, setModelsLoading] = useState(false);
  const [modelsError, setModelsError] = useState(false);
  const [modelsRetryCount, setModelsRetryCount] = useState(0);
  const [showAuth, setShowAuth] = useState(false);
  const [showAdvanced, setShowAdvanced] = useState(false);

  // [Fix 5.4] Stable auth identity built from its primitive parts so effects
  // and children that depend on it don't re-run on every render.
  const auth = useMemo(
    () => ({ clientSessionId: settings.clientSessionId, providerApiKey: settings.providerApiKey }),
    [settings.clientSessionId, settings.providerApiKey],
  );

  // Fetch models when the panel opens or provider/key/session changes. On
  // failure the silent-default fallback stays, but a subtle inline notice
  // with a retry link surfaces it.
  // One key per load request (same inputs the effect used to depend on).
  // Spinner/reset state is adjusted during render when it changes; the effect
  // below only performs the request.
  const canLoadModels = open && Boolean(auth.providerApiKey.trim());
  const modelsRequest = useMemo(
    () => ({ enabled: canLoadModels, provider: settings.provider, auth, attempt: modelsRetryCount }),
    [canLoadModels, settings.provider, auth, modelsRetryCount],
  );
  useOnChange(modelsRequest, (request) => {
    if (!request.enabled) {
      setModels(null);
      setModelsError(false);
      // Also drop the spinner: if a fetch was in flight, its `finally` is
      // skipped by the `cancelled` guard, so without this the "Loading models…"
      // hint stuck on forever.
      setModelsLoading(false);
    } else {
      setModelsLoading(true);
    }
  });

  useEffect(() => {
    if (!modelsRequest.enabled) return;
    const { auth: requestAuth, provider } = modelsRequest;
    let cancelled = false;
    const loadModels = async () => {
      try {
        const response = await fetchModels(requestAuth, provider);
        if (cancelled) return;
        setModels(response);
        setModelsError(false);
      } catch {
        // Keep defaults on error, but stop failing silently.
        if (cancelled) return;
        setModels(null);
        setModelsError(true);
      } finally {
        if (!cancelled) setModelsLoading(false);
      }
    };
    void loadModels();
    return () => {
      cancelled = true;
    };
  }, [modelsRequest]);

  const providers: { value: Provider; label: string; icon: string }[] = [
    { value: "openai", label: "OpenAI", icon: "O" },
    { value: "gemini", label: "Google Gemini", icon: "G" },
  ];

  const resolvedAccent = LEGACY_PACK_ALIASES[settings.accentPack] ?? settings.accentPack;
  const activeAccentPack =
    resolvedAccent === "lime" || resolvedAccent === "pulse" || resolvedAccent === "beam"
      ? resolvedAccent
      : "lime";

  const handleSignOut = async () => {
    try {
      await logout();
    } catch {
      // [Fix 6.4] Best-effort server logout failed — still clear the local
      // session so the UI (and stored token) end up signed out.
      clearStoredAuthToken();
    } finally {
      dispatch({ type: "SET_CURRENT_USER", payload: null });
      // Drop the BYOK provider key on sign-out. sessionStorage outlives the
      // sign-out within a tab, so without this the next person to sign in on a
      // shared browser inherits the previous user's provider credentials.
      dispatch({ type: "SET_SETTINGS", payload: { providerApiKey: "" } });
    }
  };

  const resetDefaults = () =>
    dispatch({
      type: "SET_SETTINGS",
      payload: {
        chatModel: DEFAULT_CHAT[settings.provider],
        embeddingModel: DEFAULT_EMBEDDING[settings.provider],
      },
    });

  const modelHint = modelsLoading
    ? "Loading available models…"
    : !settings.providerApiKey.trim()
      ? "Add an API key to choose available models."
      : undefined;

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Settings"
      width={520}
      height="min(720px, 88vh)"
      align="top"
      className="flex flex-col overflow-hidden"
    >
      {/* Header — title + the one primary action (Done) */}
      <div
        className="flex items-start justify-between gap-4 px-6 py-4 shrink-0"
        style={{ borderBottom: "1px solid var(--border)" }}
      >
        <div>
          <h2 className="display text-base font-semibold" style={{ color: "var(--text-primary)" }}>
            Settings
          </h2>
          <p className="text-xs mt-0.5" style={{ color: "var(--text-tertiary)" }}>
            Preferences save automatically. Your API key stays in this browser tab’s session storage.
          </p>
        </div>
        <Button variant="primary" size="sm" onClick={onClose}>
          Done
        </Button>
      </div>

      <div className="flex-1 overflow-y-auto px-6 py-5 flex flex-col gap-5">
        <section aria-labelledby="provider-section-title" className="flex flex-col gap-4">
          <div className="flex flex-col gap-1">
            <h3 id="provider-section-title" className="text-sm font-semibold" style={{ color: "var(--text-primary)" }}>
              AI provider
            </h3>
            <p className="text-xs" style={{ color: "var(--text-tertiary)" }}>
              Choose a provider, add its key, and select your models.
            </p>
          </div>

          <div role="group" aria-label="AI provider" className="flex gap-2">
            {providers.map((provider) => {
              const active = settings.provider === provider.value;
              return (
                <button
                  key={provider.value}
                  type="button"
                  onClick={() => dispatch({ type: "SET_PROVIDER", payload: provider.value })}
                  aria-pressed={active}
                  className="flex-1 flex items-center justify-center gap-2 px-3 py-2.5 rounded-lg text-[13px] font-medium transition-colors focus-ring"
                  style={{
                    background: active ? "var(--accent-primary-soft)" : "var(--bg-surface)",
                    border: `1px solid ${active ? "var(--accent-primary)" : "var(--border)"}`,
                    color: active ? "var(--text-primary)" : "var(--text-secondary)",
                  }}
                >
                  <span
                    className="data-num text-[10px] font-bold"
                    style={{ color: active ? "var(--accent-primary)" : "var(--text-muted)" }}
                  >
                    {provider.icon}
                  </span>
                  {provider.label}
                </button>
              );
            })}
          </div>

          <TextField
            label="Provider API Key"
            type="password"
            mono
            autoComplete="off"
            value={settings.providerApiKey}
            onChange={(event) =>
              dispatch({ type: "SET_SETTINGS", payload: { providerApiKey: event.target.value } })
            }
            placeholder={settings.provider === "openai" ? "sk-..." : "Google AI API key"}
            hint="Used for uploads, reprocessing, embeddings, and chat. Stored in this tab’s session storage."
          />

          <div className="flex flex-col gap-2" aria-busy={modelsLoading}>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <SelectField
                label="Chat model"
                value={settings.chatModel}
                options={(models?.chat_models ?? [DEFAULT_CHAT[settings.provider]]).map((m) => ({
                  value: m,
                  label: m,
                }))}
                onChange={(event) =>
                  dispatch({ type: "SET_SETTINGS", payload: { chatModel: event.target.value } })
                }
                disabled={!settings.providerApiKey.trim() || modelsLoading}
              />
              <SelectField
                label="Embedding model"
                value={settings.embeddingModel}
                options={(models?.embedding_models ?? [DEFAULT_EMBEDDING[settings.provider]]).map((m) => ({
                  value: m,
                  label: m,
                }))}
                onChange={(event) =>
                  dispatch({ type: "SET_SETTINGS", payload: { embeddingModel: event.target.value } })
                }
                disabled={!settings.providerApiKey.trim() || modelsLoading}
              />
            </div>
            {modelHint ? (
              <p className="text-xs" style={{ color: "var(--text-tertiary)" }} aria-live="polite">
                {modelHint}
              </p>
            ) : null}
            {modelsError ? (
              <p className="text-xs" style={{ color: "var(--text-tertiary)" }} role="status">
                Couldn&apos;t load model list — using defaults.{" "}
                <button
                  type="button"
                  onClick={() => setModelsRetryCount((n) => n + 1)}
                  className="underline underline-offset-2 rounded focus-ring"
                  style={{ color: "var(--accent-primary)" }}
                >
                  Retry
                </button>
              </p>
            ) : null}
          </div>
        </section>

        <Divider />

        <section aria-labelledby="appearance-section-title" className="flex flex-col gap-4">
          <div className="flex flex-col gap-1">
            <h3 id="appearance-section-title" className="text-sm font-semibold" style={{ color: "var(--text-primary)" }}>
              Appearance
            </h3>
            <p className="text-xs" style={{ color: "var(--text-tertiary)" }}>
              Set the theme and accessibility preferences for this browser.
            </p>
          </div>

          <div className="flex flex-col gap-1.5">
            <span className="text-[13px]" style={{ color: "var(--text-secondary)" }}>
              Theme
            </span>
            <div
              role="group"
              aria-label="Theme"
              className="grid grid-cols-2 gap-1 p-1 rounded-lg"
              style={{ background: "var(--bg-tertiary)", border: "1px solid var(--border)" }}
            >
              {(["light", "dark"] as const).map((theme) => {
                const active = settings.theme === theme;
                return (
                  <button
                    key={theme}
                    type="button"
                    aria-pressed={active}
                    onClick={() => dispatch({ type: "SET_SETTINGS", payload: { theme } })}
                    className="rounded-md px-3 py-1.5 text-xs font-medium capitalize transition-colors focus-ring"
                    style={{
                      background: active ? "var(--bg-surface)" : "transparent",
                      color: active ? "var(--text-primary)" : "var(--text-muted)",
                      border: `1px solid ${active ? "var(--border-hover)" : "transparent"}`,
                    }}
                  >
                    {theme}
                  </button>
                );
              })}
            </div>
          </div>

          <div className="flex flex-col gap-1.5">
            <span className="text-[13px]" style={{ color: "var(--text-secondary)" }}>
              Accent
            </span>
            <div role="group" aria-label="Accent color" className="flex gap-2">
              {ACCENT_PACKS.map((pack) => {
                const active = activeAccentPack === pack.value;
                return (
                  <button
                    key={pack.value}
                    type="button"
                    aria-pressed={active}
                    onClick={() =>
                      dispatch({
                        type: "SET_SETTINGS",
                        // Store union is mid-migration; the value is a plain
                        // string here so both old and widened unions accept it.
                        payload: { accentPack: pack.value as AppSettings["accentPack"] },
                      })
                    }
                    className="flex-1 flex items-center justify-center gap-1.5 px-2.5 py-2 rounded-lg text-xs font-medium transition-all focus-ring"
                    style={{
                      background: pack.color,
                      color: "var(--accent-fg)",
                      border: `1px solid ${active ? "var(--border-strong)" : "transparent"}`,
                      opacity: active ? 1 : 0.82,
                    }}
                  >
                    <span className="inline-flex w-3 justify-center">
                      {active ? <Check size={12} strokeWidth={2.5} /> : null}
                    </span>
                    {pack.label}
                  </button>
                );
              })}
            </div>
          </div>

          <ToggleField
            label="High contrast"
            description="Increase text and border contrast."
            checked={settings.highContrast}
            onCheckedChange={(checked) =>
              dispatch({ type: "SET_SETTINGS", payload: { highContrast: checked } })
            }
          />
          <ToggleField
            label="Reduce motion"
            description="Limit interface animations and transitions."
            checked={settings.reducedMotion}
            onCheckedChange={(checked) =>
              dispatch({ type: "SET_SETTINGS", payload: { reducedMotion: checked } })
            }
          />
        </section>

        <Divider />

        <CollapsibleSection
          title="Advanced settings"
          description="Retrieval tuning and session details"
          open={showAdvanced}
          onToggle={() => setShowAdvanced((value) => !value)}
        >
          <div className="flex flex-col gap-4">
            <div className="flex flex-col gap-1">
              <SliderField
                label="Top-K Chunks"
                value={settings.topK}
                min={1}
                max={20}
                step={1}
                format={(value) => `${value} chunks`}
                onChange={(event) =>
                  dispatch({
                    type: "SET_SETTINGS",
                    payload: { topK: parseFloat(event.target.value) },
                  })
                }
              />
              <p className="text-xs" style={{ color: "var(--text-tertiary)" }}>
                Number of document chunks retrieved per query.
              </p>
            </div>
            <div className="flex flex-col gap-1">
              <SliderField
                label="Similarity Threshold"
                value={settings.similarityThreshold}
                min={0}
                max={1}
                step={0.05}
                format={(value) => (value === 0 ? "Off" : value.toFixed(2))}
                onChange={(event) =>
                  dispatch({
                    type: "SET_SETTINGS",
                    payload: { similarityThreshold: parseFloat(event.target.value) },
                  })
                }
              />
              <p className="text-xs" style={{ color: "var(--text-tertiary)" }}>
                Minimum similarity score to include a chunk.
              </p>
            </div>
            <div className="flex flex-col gap-1 border-t pt-3" style={{ borderColor: "var(--border)" }}>
              <span className="text-xs font-medium" style={{ color: "var(--text-secondary)" }}>
                Browser session ID
              </span>
              <span className="data-num text-xs break-all" style={{ color: "var(--text-tertiary)" }}>
                {settings.clientSessionId}
              </span>
              <span className="text-xs" style={{ color: "var(--text-muted)" }}>
                Used to scope data for this browser session.
              </span>
            </div>
          </div>
        </CollapsibleSection>

        <Divider />

        <CollapsibleSection
          title="Account"
          description={user ? `Signed in as ${user.email}` : "Optional · sync data across devices"}
          open={showAuth}
          onToggle={() => setShowAuth((value) => !value)}
        >
          {user ? (
            <div className="flex items-center justify-between gap-3">
              <p className="text-[13px]" style={{ color: "var(--text-secondary)" }}>
                Your data is synced across devices.
              </p>
              <Button variant="secondary" size="sm" onClick={() => void handleSignOut()}>
                Sign out
              </Button>
            </div>
          ) : (
            <AuthForm
              compact
              onAuthenticated={(next) => dispatch({ type: "SET_CURRENT_USER", payload: next })}
            />
          )}
        </CollapsibleSection>
      </div>

      {/* Footer — Reset defaults */}
      <div
        className="flex items-center justify-between px-6 py-3.5 shrink-0"
        style={{ borderTop: "1px solid var(--border)" }}
      >
        <Button variant="ghost" size="sm" onClick={resetDefaults}>
          <RotateCcw size={12} />
          Reset model defaults
        </Button>
        <span className="text-[11px]" style={{ color: "var(--text-muted)" }}>
          Esc to close
        </span>
      </div>
    </Modal>
  );
}

/* ---------- Local sub-components ---------- */

function Divider() {
  return <div aria-hidden="true" className="h-px" style={{ background: "var(--border)" }} />;
}

/**
 * Section that toggles open/closed via a ghost header button with a rotating
 * chevron. Content animates in with a height reveal.
 */
function CollapsibleSection({
  title,
  description,
  open,
  onToggle,
  children,
}: {
  title: string;
  description?: string;
  open: boolean;
  onToggle: () => void;
  children: React.ReactNode;
}) {
  const contentId = useId();

  return (
    <div className="flex flex-col">
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        aria-controls={contentId}
        className="w-full flex items-center justify-between gap-3 py-1 rounded-md text-left transition-colors focus-ring"
        style={{ color: "var(--text-secondary)" }}
      >
        <span className="flex min-w-0 flex-col gap-1">
          <span className="text-[13px] font-medium">{title}</span>
          {description ? (
            <span className="text-xs" style={{ color: "var(--text-tertiary)" }}>
              {description}
            </span>
          ) : null}
        </span>
        <motion.span
          aria-hidden="true"
          animate={{ rotate: open ? 180 : 0 }}
          transition={transitionFast}
          className="shrink-0"
          style={{ color: "var(--text-muted)" }}
        >
          <ChevronDown size={14} />
        </motion.span>
      </button>
      <div id={contentId} hidden={!open} className="pt-3 pb-1">
        {children}
      </div>
    </div>
  );
}

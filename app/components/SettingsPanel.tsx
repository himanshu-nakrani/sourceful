"use client";

import React, { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { CheckCircle2, ChevronDown, KeyRound, RotateCcw, Search, UserCircle, X } from "lucide-react";
import {
  fetchModels,
  getGoogleOAuthClientId,
  login,
  logout,
  signup,
  type Provider,
  type ModelsResponse,
} from "../lib/api";
import { DEFAULT_CHAT, DEFAULT_EMBEDDING, useStore } from "../lib/store";
import { EASE_OUT } from "../lib/motion";

interface SettingsPanelProps {
  open: boolean;
  onClose: () => void;
}

/**
 * Render a centered modal that allows the user to configure provider credentials, select models, adjust retrieval settings, and optionally sign in for cross-device sync.
 *
 * Reads current settings and user from the app store and dispatches store actions to update provider, API key, selected models, retrieval parameters, and current user state (login/logout). Clicking the background overlay or the Done button invokes the close callback.
 *
 * @param open - Whether the settings panel is visible
 * @param onClose - Callback invoked to close the panel
 * @returns The settings modal element when `open` is true, otherwise `null`
 */
export default function SettingsPanel({ open, onClose }: SettingsPanelProps) {
  const { state, dispatch } = useStore();
  const { settings } = state;
  const [models, setModels] = useState<ModelsResponse | null>(null);
  const [modelsLoading, setModelsLoading] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [authError, setAuthError] = useState<string | null>(null);
  const [showAuth, setShowAuth] = useState(false);
  const [showRetrieval, setShowRetrieval] = useState(false);
  const [googleClientId, setGoogleClientId] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    getGoogleOAuthClientId()
      .then((clientId) => {
        if (clientId) setGoogleClientId(clientId);
      })
      .catch(() => {});
  }, [open]);

  // Fetch models when provider or API key changes
  useEffect(() => {
    if (!open || !settings.providerApiKey.trim()) {
      setModels(null);
      return;
    }

    const loadModels = async () => {
      setModelsLoading(true);
      try {
        const auth = {
          clientSessionId: settings.clientSessionId,
          providerApiKey: settings.providerApiKey,
        };
        const response = await fetchModels(auth, settings.provider);
        setModels(response);
      } catch {
        // Keep defaults on error
        setModels(null);
      } finally {
        setModelsLoading(false);
      }
    };

    loadModels();
  }, [open, settings.provider, settings.providerApiKey, settings.clientSessionId]);

  if (!open) return null;
  const user = state.currentUser;

  const providers: { value: Provider; label: string; icon: string }[] = [
    { value: "openai", label: "OpenAI", icon: "O" },
    { value: "gemini", label: "Google Gemini", icon: "G" },
    // { value: "vertex_search", label: "Vertex AI Search", icon: "V" },
  ];

  return (
    <motion.div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: "rgba(0, 0, 0, 0.5)", backdropFilter: "blur(8px)" }}
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      {/* [a11y] Added role="dialog" and aria-modal for assistive technology support */}
      <motion.div
        role="dialog"
        aria-modal="true"
        aria-label="Settings"
        className="rounded-2xl shadow-2xl overflow-y-auto"
        style={{
          width: "min(480px, 92vw)",
          maxHeight: "min(90vh, 90dvh)",
          background: "var(--bg-secondary)",
          border: "1px solid var(--border)",
        }}
        initial={{ opacity: 0, scale: 0.96, y: 8 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        transition={{ duration: 0.25, ease: EASE_OUT }}
      >
        <div className="flex items-center justify-between px-5 py-4" style={{ borderBottom: "1px solid var(--border)" }}>
          <div>
            <h2 className="text-sm font-semibold" style={{ color: "var(--text-primary)", letterSpacing: "-0.01em" }}>
              Settings
            </h2>
            <p className="text-[11px] mt-0.5" style={{ color: "var(--text-muted)" }}>
              Credentials stored in this browser session only.
            </p>
          </div>
          {/* [a11y] Added aria-label — icon-only button needs accessible name */}
          <motion.button
            type="button"
            onClick={onClose}
            className="p-1.5 rounded-xl"
            style={{ color: "var(--text-muted)" }}
            aria-label="Close settings"
            whileHover={{ background: "var(--bg-surface)", color: "var(--text-secondary)" }}
            whileTap={{ scale: 0.9 }}
          >
            <X size={16} />
          </motion.button>
        </div>

        <div className="px-5 py-5 flex flex-col gap-5">
          {/* Provider Selection */}
          <div className="flex flex-col gap-2">
            <label className="text-[10px] font-semibold uppercase tracking-widest" style={{ color: "var(--text-muted)" }}>
              Provider
            </label>
            <div className="flex gap-1.5">
              {providers.map((provider) => (
                <motion.button
                  key={provider.value}
                  type="button"
                  onClick={() => dispatch({ type: "SET_PROVIDER", payload: provider.value })}
                  aria-pressed={settings.provider === provider.value}
                  className="flex-1 flex items-center justify-center gap-2 px-3 py-2.5 rounded-xl text-sm font-medium"
                  style={{
                    background:
                      settings.provider === provider.value ? "var(--accent-brand-soft)" : "var(--bg-surface)",
                    border: `1px solid ${
                      settings.provider === provider.value
                        ? "var(--accent-brand)"
                        : "var(--border)"
                    }`,
                    color:
                      settings.provider === provider.value
                        ? "var(--text-primary)"
                        : "var(--text-secondary)",
                  }}
                  whileTap={{ scale: 0.97 }}
                >
                  <span className="text-xs font-bold" style={{ color: settings.provider === provider.value ? "var(--accent-brand)" : "var(--text-muted)" }}>
                    {provider.icon}
                  </span>
                  {provider.label}
                </motion.button>
              ))}
            </div>
          </div>

          <Field
            label="Provider API Key"
            icon={<KeyRound size={13} />}
            value={settings.providerApiKey}
            onChange={(value) =>
              dispatch({ type: "SET_SETTINGS", payload: { providerApiKey: value } })
            }
            placeholder={
              settings.provider === "openai"
                ? "sk-..."
                /* : settings.provider === "vertex_search"
                  ? "Google AI API key (for Gemini chat)" */
                  : "Google AI API key"
            }
            help="Used for uploads, reprocessing, embeddings, and chat."
          />

          {/* Dynamic Model Dropdowns */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <SelectField
              label="Chat Model"
              value={settings.chatModel}
              options={models?.chat_models || [DEFAULT_CHAT[settings.provider]]}
              onChange={(value) =>
                dispatch({ type: "SET_SETTINGS", payload: { chatModel: value } })
              }
              loading={modelsLoading}
              disabled={!settings.providerApiKey.trim()}
            />
            <SelectField
              label="Embedding Model"
              value={settings.embeddingModel}
              options={models?.embedding_models || [DEFAULT_EMBEDDING[settings.provider]]}
              onChange={(value) =>
                dispatch({ type: "SET_SETTINGS", payload: { embeddingModel: value } })
              }
              loading={modelsLoading}
              disabled={!settings.providerApiKey.trim()}
            />
          </div>

          <div
            className="rounded-xl p-3 flex items-start gap-3"
            style={{ background: "var(--bg-surface)", border: "1px solid var(--border)" }}
          >
            <CheckCircle2 size={14} style={{ color: "var(--success)", marginTop: 2, flexShrink: 0 }} />
            <div className="text-[11px] leading-relaxed" style={{ color: "var(--text-tertiary)" }}>
              <p>Session: <span style={{ color: "var(--text-secondary)" }}>{settings.clientSessionId}</span></p>
              <p className="mt-0.5">
                Models remembered locally. Keys stay in session storage.
              </p>
            </div>
          </div>

          {/* RAG Retrieval Settings - Collapsible */}
          <CollapsibleSection
            icon={<Search size={14} />}
            title="Retrieval Settings"
            open={showRetrieval}
            onToggle={() => setShowRetrieval(!showRetrieval)}
          >
            <div className="flex flex-col gap-4">
              <SliderField
                label="Top-K Chunks"
                value={settings.topK}
                min={1}
                max={20}
                step={1}
                onChange={(value) => dispatch({ type: "SET_SETTINGS", payload: { topK: value } })}
                format={(v) => `${v} chunks`}
                help="Number of document chunks retrieved per query."
              />
              <SliderField
                label="Similarity Threshold"
                value={settings.similarityThreshold}
                min={0}
                max={1}
                step={0.05}
                onChange={(value) => dispatch({ type: "SET_SETTINGS", payload: { similarityThreshold: value } })}
                format={(v) => v === 0 ? "Off" : v.toFixed(2)}
                help="Minimum similarity score to include a chunk."
              />
            </div>
          </CollapsibleSection>

          {/* Optional Authentication - Collapsible */}
          <CollapsibleSection
            icon={<UserCircle size={14} />}
            title={user ? `Signed in as ${user.email}` : "Sign in (optional)"}
            open={showAuth}
            onToggle={() => setShowAuth(!showAuth)}
          >
            {user ? (
              <div className="flex items-center justify-between">
                <p className="text-sm" style={{ color: "var(--text-secondary)" }}>
                  Your data is synced across devices.
                </p>
                <motion.button
                  type="button"
                  className="px-3 py-1.5 rounded-xl text-xs"
                  style={{ background: "var(--bg-surface)", border: "1px solid var(--border)" }}
                  onClick={async () => {
                    await logout();
                    dispatch({ type: "SET_CURRENT_USER", payload: null });
                  }}
                  whileTap={{ scale: 0.95 }}
                >
                  Logout
                </motion.button>
              </div>
            ) : (
              <div className="flex flex-col gap-3">
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                  <input
                    value={email}
                    onChange={(event) => setEmail(event.target.value)}
                    placeholder="Email"
                    className="rounded-xl px-3 py-2 text-sm outline-none"
                    style={{ background: "var(--bg-surface)", border: "1px solid var(--border)", color: "var(--text-primary)" }}
                  />
                  <input
                    type="password"
                    value={password}
                    onChange={(event) => setPassword(event.target.value)}
                    placeholder="Password"
                    className="rounded-xl px-3 py-2 text-sm outline-none"
                    style={{ background: "var(--bg-surface)", border: "1px solid var(--border)", color: "var(--text-primary)" }}
                  />
                </div>
                <div className="flex gap-2">
                  <motion.button
                    type="button"
                    className="flex-1 px-4 py-2 rounded-xl text-sm"
                    style={{ background: "var(--accent)", color: "var(--accent-fg)" }}
                    onClick={async () => {
                      try {
                        const next = await login(email.trim(), password);
                        dispatch({ type: "SET_CURRENT_USER", payload: next });
                        setAuthError(null);
                        setEmail("");
                        setPassword("");
                      } catch (error) {
                        setAuthError(error instanceof Error ? error.message : "Login failed.");
                      }
                    }}
                    whileTap={{ scale: 0.97 }}
                  >
                    Sign In
                  </motion.button>
                  <motion.button
                    type="button"
                    className="flex-1 px-4 py-2 rounded-xl text-sm"
                    style={{ background: "var(--bg-surface)", border: "1px solid var(--border)", color: "var(--text-primary)" }}
                    onClick={async () => {
                      try {
                        const next = await signup(email.trim(), password);
                        dispatch({ type: "SET_CURRENT_USER", payload: next });
                        setAuthError(null);
                        setEmail("");
                        setPassword("");
                      } catch (error) {
                        setAuthError(error instanceof Error ? error.message : "Signup failed.");
                      }
                    }}
                    whileTap={{ scale: 0.97 }}
                  >
                    Create Account
                  </motion.button>
                </div>
                {googleClientId ? (
                  <motion.button
                    type="button"
                    onClick={() => {
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
                    }}
                    className="w-full flex items-center justify-center gap-2 rounded-xl px-3 py-2 text-sm"
                    style={{
                      background: "var(--bg-surface)",
                      border: "1px solid var(--border)",
                      color: "var(--text-primary)",
                    }}
                    whileHover={{ borderColor: "var(--border-hover)" }}
                    whileTap={{ scale: 0.97 }}
                  >
                    <svg width="16" height="16" viewBox="0 0 48 48">
                      <path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"/>
                      <path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"/>
                      <path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"/>
                      <path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"/>
                    </svg>
                    Sign in with Google
                  </motion.button>
                ) : null}
                {authError ? (
                  <p className="text-xs" style={{ color: "var(--error)" }}>
                    {authError}
                  </p>
                ) : null}
              </div>
            )}
          </CollapsibleSection>
        </div>

        <div
          className="flex items-center justify-between px-5 py-4"
          style={{ borderTop: "1px solid var(--border)" }}
        >
          <motion.button
            type="button"
            onClick={() =>
              dispatch({
                type: "SET_SETTINGS",
                payload: {
                  chatModel: DEFAULT_CHAT[settings.provider],
                  embeddingModel: DEFAULT_EMBEDDING[settings.provider],
                },
              })
            }
            className="inline-flex items-center gap-2 px-3 py-2 rounded-xl text-xs"
            style={{ background: "var(--bg-surface)", color: "var(--text-tertiary)", border: "1px solid var(--border)" }}
            whileHover={{ borderColor: "var(--border-hover)", color: "var(--text-secondary)" }}
            whileTap={{ scale: 0.95 }}
          >
            <RotateCcw size={12} />
            Reset
          </motion.button>
          <motion.button
            type="button"
            onClick={onClose}
            className="px-5 py-2 rounded-xl text-sm font-medium"
            style={{ background: "var(--accent)", color: "var(--accent-fg)" }}
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.97 }}
            transition={{ type: "spring", stiffness: 400, damping: 17 }}
          >
            Done
          </motion.button>
        </div>
      </motion.div>
    </motion.div>
  );
}

/* ---------- Sub-components ---------- */

function CollapsibleSection({
  icon,
  title,
  open,
  onToggle,
  children,
}: {
  icon: React.ReactNode;
  title: string;
  open: boolean;
  onToggle: () => void;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-xl overflow-hidden" style={{ border: "1px solid var(--border)" }}>
      <button
        type="button"
        onClick={onToggle}
        className="w-full flex items-center justify-between px-4 py-3 text-sm"
        style={{ background: "var(--bg-surface)" }}
      >
        <span className="flex items-center gap-2" style={{ color: "var(--text-secondary)" }}>
          {icon}
          <span className="truncate">{title}</span>
        </span>
        <motion.div
          animate={{ rotate: open ? 180 : 0 }}
          transition={{ duration: 0.2 }}
        >
          <ChevronDown size={14} style={{ color: "var(--text-muted)" }} />
        </motion.div>
      </button>
      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.25, ease: EASE_OUT }}
            className="overflow-hidden"
          >
            <div className="px-4 py-4" style={{ background: "var(--bg-secondary)" }}>
              {children}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

/**
 * Renders a labeled input field with a left icon and contextual help text.
 *
 * The input is rendered as a password field with `autoComplete="off"`, suitable for credential entry.
 *
 * @param label - Visible label text shown above the input
 * @param value - Controlled input value
 * @param onChange - Callback invoked with the new input value on edit
 * @param placeholder - Placeholder text shown inside the input
 * @param help - Small help text shown below the input
 * @param icon - Icon element displayed inside the input on the left
 * @returns A JSX element containing the labeled input, icon, and help text
 */
function Field({
  label,
  value,
  onChange,
  placeholder,
  help,
  icon,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
  help: string;
  icon: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-2">
      <label className="text-[10px] font-semibold uppercase tracking-widest" style={{ color: "var(--text-muted)" }}>
        {label}
      </label>
      <div className="relative">
        <div className="absolute left-3 top-1/2 -translate-y-1/2" style={{ color: "var(--text-muted)" }}>
          {icon}
        </div>
        <input
          type="password"
          autoComplete="off"
          value={value}
          onChange={(event) => onChange(event.target.value)}
          placeholder={placeholder}
          className="w-full rounded-xl px-3 py-2.5 pl-9 text-sm outline-none transition-all duration-200"
          style={{
            background: "var(--bg-surface)",
            border: "1px solid var(--border)",
            color: "var(--text-primary)",
          }}
        />
      </div>
      <p className="text-[11px]" style={{ color: "var(--text-muted)" }}>
        {help}
      </p>
    </div>
  );
}

/**
 * Renders a labeled select control with a chevron icon and contextual messaging for loading or disabled states.
 *
 * @param onChange - Called with the newly selected value when the user changes the selection.
 * @param options - Array of string options to render as select choices.
 * @param loading - When `true`, disables the control and shows "Loading models...".
 * @param disabled - When `true` disables the control; if not loading, shows a hint prompting for an API key.
 * @returns The select field element.
 */
function SelectField({
  label,
  value,
  onChange,
  options,
  loading,
  disabled,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: string[];
  loading?: boolean;
  disabled?: boolean;
}) {
  return (
    <div className="flex flex-col gap-2">
      <label className="text-[10px] font-semibold uppercase tracking-widest" style={{ color: "var(--text-muted)" }}>
        {label}
      </label>
      <div className="relative">
        <select
          value={value}
          onChange={(event) => onChange(event.target.value)}
          disabled={disabled || loading}
          className="w-full rounded-xl px-3 py-2.5 text-sm outline-none appearance-none cursor-pointer disabled:opacity-50 transition-all duration-200"
          style={{
            background: "var(--bg-surface)",
            border: "1px solid var(--border)",
            color: disabled ? "var(--text-muted)" : "var(--text-primary)",
          }}
        >
          {options.map((option) => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
        </select>
        <div
          className="absolute right-3 top-1/2 -translate-y-1/2 pointer-events-none"
          style={{ color: "var(--text-muted)" }}
        >
          <ChevronDown size={12} />
        </div>
      </div>
      {loading && (
        <p className="text-[11px]" style={{ color: "var(--text-muted)" }}>
          Loading models...
        </p>
      )}
      {disabled && !loading && (
        <p className="text-[11px]" style={{ color: "var(--text-muted)" }}>
          Enter API key to see available models
        </p>
      )}
    </div>
  );
}

/**
 * Renders a labeled range slider with a formatted value display and help text.
 *
 * @param label - Visible label shown above the slider.
 * @param value - Current numeric value of the slider.
 * @param min - Minimum permitted value.
 * @param max - Maximum permitted value.
 * @param step - Increment step for the slider.
 * @param onChange - Callback invoked with the updated numeric value when the slider changes.
 * @param format - Formatter that returns the display string for the current value.
 * @param help - Small helper text shown below the slider.
 * @returns A JSX element containing the labeled slider, formatted value, and helper text.
 */
function SliderField({
  label,
  value,
  min,
  max,
  step,
  onChange,
  format,
  help,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  onChange: (value: number) => void;
  format: (v: number) => string;
  help: string;
}) {
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <label className="text-[10px] font-semibold uppercase tracking-widest" style={{ color: "var(--text-muted)" }}>
          {label}
        </label>
        <span className="text-xs font-medium" style={{ color: "var(--text-primary)" }}>
          {format(value)}
        </span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(parseFloat(e.target.value))}
        className="w-full h-1 rounded-full appearance-none cursor-pointer"
        style={{
          background: `linear-gradient(to right, var(--accent-brand) 0%, var(--accent-brand) ${((value - min) / (max - min)) * 100}%, var(--bg-elevated) ${((value - min) / (max - min)) * 100}%, var(--bg-elevated) 100%)`,
          accentColor: "var(--accent-brand)",
        }}
      />
      <p className="text-[11px]" style={{ color: "var(--text-muted)" }}>{help}</p>
    </div>
  );
}

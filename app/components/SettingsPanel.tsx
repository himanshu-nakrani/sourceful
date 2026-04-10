"use client";

import React from "react";
import { CheckCircle2, KeyRound, RotateCcw, X } from "lucide-react";
import {
  listUsers,
  login,
  logout,
  signup,
  updateUser,
  type AuthUser,
  type Provider,
} from "../lib/api";
import { DEFAULT_CHAT, DEFAULT_EMBEDDING, useStore } from "../lib/store";

interface SettingsPanelProps {
  open: boolean;
  onClose: () => void;
}

const CHAT_MODEL_OPTIONS: Record<Provider, string[]> = {
  openai: ["gpt-4o-mini", "gpt-4.1-mini", "gpt-4.1", "gpt-4o"],
  gemini: ["gemini-2.0-flash", "gemini-2.5-flash", "gemini-2.5-pro"],
};

const EMBEDDING_MODEL_OPTIONS: Record<Provider, string[]> = {
  openai: ["text-embedding-3-small", "text-embedding-3-large"],
  gemini: ["models/gemini-embedding-001"],
};

export default function SettingsPanel({ open, onClose }: SettingsPanelProps) {
  const { state, dispatch } = useStore();
  const { settings } = state;
  const [email, setEmail] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [authError, setAuthError] = React.useState<string | null>(null);
  const [adminUsers, setAdminUsers] = React.useState<AuthUser[]>([]);
  const [adminLoading, setAdminLoading] = React.useState(false);

  if (!open) return null;
  const user = state.currentUser;

  const providers: { value: Provider; label: string; icon: string }[] = [
    { value: "openai", label: "OpenAI", icon: "O" },
    { value: "gemini", label: "Google Gemini", icon: "G" },
  ];

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center animate-fade-in"
      style={{ background: "rgba(0, 0, 0, 0.6)", backdropFilter: "blur(4px)" }}
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      {/* [a11y] Added role="dialog" and aria-modal for assistive technology support */}
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Settings"
        className="rounded-2xl shadow-2xl animate-scale-in"
        style={{
          width: "min(520px, 92vw)",
          background: "var(--bg-secondary)",
          border: "1px solid var(--border)",
        }}
      >
        <div className="flex items-center justify-between px-5 py-4" style={{ borderBottom: "1px solid var(--border)" }}>
          <div>
            <h2 className="text-base font-semibold" style={{ color: "var(--text-primary)" }}>
              Settings
            </h2>
            <p className="text-xs mt-1" style={{ color: "var(--text-tertiary)" }}>
              Provider credentials are stored in this browser session only.
            </p>
          </div>
          {/* [a11y] Added aria-label — icon-only button needs accessible name */}
          <button type="button" onClick={onClose} className="p-1 rounded-md" style={{ color: "var(--text-tertiary)" }} aria-label="Close settings">
            <X size={18} />
          </button>
        </div>

        <div className="px-5 py-5 flex flex-col gap-5">
          <div className="rounded-xl p-3" style={{ background: "var(--bg-surface)", border: "1px solid var(--border)" }}>
            {user ? (
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="text-sm font-medium" style={{ color: "var(--text-primary)" }}>
                    Signed in as {user.email}
                  </p>
                  <p className="text-xs" style={{ color: "var(--text-tertiary)" }}>
                    Role: {user.role}
                  </p>
                </div>
                <button
                  type="button"
                  className="px-3 py-1.5 rounded-lg text-xs"
                  style={{ background: "var(--bg-secondary)", border: "1px solid var(--border)" }}
                  onClick={async () => {
                    await logout();
                    dispatch({ type: "SET_CURRENT_USER", payload: null });
                  }}
                >
                  Logout
                </button>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto_auto] gap-2 items-stretch">
                <input
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  placeholder="Email"
                  className="rounded-lg px-3 py-2 text-sm outline-none w-full min-w-0 h-11"
                  style={{ background: "var(--bg-secondary)", border: "1px solid var(--border)" }}
                />
                <input
                  type="password"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  placeholder="Password"
                  className="rounded-lg px-3 py-2 text-sm outline-none w-full min-w-0 h-11"
                  style={{ background: "var(--bg-secondary)", border: "1px solid var(--border)" }}
                />
                <button
                  type="button"
                  className="px-4 py-2 rounded-lg text-sm h-11 whitespace-nowrap inline-flex items-center justify-center"
                  style={{ background: "var(--accent)", color: "var(--accent-fg)" }}
                  onClick={async () => {
                    try {
                      const next = await login(email.trim(), password);
                      dispatch({ type: "SET_CURRENT_USER", payload: next });
                      setAuthError(null);
                    } catch (error) {
                      setAuthError(error instanceof Error ? error.message : "Login failed.");
                    }
                  }}
                >
                  Login
                </button>
                <button
                  type="button"
                  className="px-4 py-2 rounded-lg text-sm h-11 whitespace-nowrap inline-flex items-center justify-center"
                  style={{ background: "var(--bg-secondary)", border: "1px solid var(--border)" }}
                  onClick={async () => {
                    try {
                      const next = await signup(email.trim(), password);
                      dispatch({ type: "SET_CURRENT_USER", payload: next });
                      setAuthError(null);
                    } catch (error) {
                      setAuthError(error instanceof Error ? error.message : "Signup failed.");
                    }
                  }}
                >
                  Sign up
                </button>
              </div>
            )}
            {authError ? (
              <p className="text-xs mt-2" style={{ color: "var(--error)" }}>
                {authError}
              </p>
            ) : null}
          </div>

          <div className="flex flex-col gap-2">
            <label className="text-xs font-semibold uppercase tracking-wider" style={{ color: "var(--text-tertiary)" }}>
              Provider
            </label>
            <div className="flex gap-2">
              {providers.map((provider) => (
                <button
                  key={provider.value}
                  type="button"
                  onClick={() => dispatch({ type: "SET_PROVIDER", payload: provider.value })}
                  aria-pressed={settings.provider === provider.value}
                  className="flex-1 flex items-center justify-center gap-2 px-3 py-2.5 rounded-lg text-sm font-medium transition-all"
                  style={{
                    background:
                      settings.provider === provider.value ? "var(--accent-soft)" : "var(--bg-surface)",
                    border: `1px solid ${
                      settings.provider === provider.value
                        ? "var(--border-accent)"
                        : "var(--border)"
                    }`,
                    color:
                      settings.provider === provider.value
                        ? "var(--text-primary)"
                        : "var(--text-secondary)",
                  }}
                >
                  <span>{provider.icon}</span>
                  {provider.label}
                </button>
              ))}
            </div>
          </div>

          <Field
            label="Provider API Key"
            icon={<KeyRound size={14} />}
            value={settings.providerApiKey}
            onChange={(value) =>
              dispatch({ type: "SET_SETTINGS", payload: { providerApiKey: value } })
            }
            placeholder={settings.provider === "openai" ? "sk-..." : "Google AI API key"}
            help="Used for uploads, reprocessing, embeddings, and chat generation."
          />

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <PresetField
              label="Chat Model"
              value={settings.chatModel}
              options={CHAT_MODEL_OPTIONS[settings.provider]}
              onChange={(value) =>
                dispatch({ type: "SET_SETTINGS", payload: { chatModel: value } })
              }
              listId="chat-models"
            />
            <PresetField
              label="Embedding Model"
              value={settings.embeddingModel}
              options={EMBEDDING_MODEL_OPTIONS[settings.provider]}
              onChange={(value) =>
                dispatch({ type: "SET_SETTINGS", payload: { embeddingModel: value } })
              }
              listId="embedding-models"
            />
          </div>

          <div
            className="rounded-xl p-3 flex items-start gap-3"
            style={{ background: "var(--bg-surface)", border: "1px solid var(--border)" }}
          >
            <CheckCircle2 size={16} style={{ color: "var(--success)", marginTop: 2 }} />
            <div className="text-xs leading-relaxed" style={{ color: "var(--text-secondary)" }}>
              <p>Client session: <span style={{ color: "var(--text-primary)" }}>{settings.clientSessionId}</span></p>
              <p className="mt-1">
                Models are remembered locally, while keys stay in session storage by default.
              </p>
            </div>
          </div>

          {user?.role === "admin" ? (
            <div className="rounded-xl p-3" style={{ background: "var(--bg-surface)", border: "1px solid var(--border)" }}>
              <div className="flex items-center justify-between mb-2">
                <p className="text-xs font-semibold uppercase tracking-wider" style={{ color: "var(--text-tertiary)" }}>
                  User Management
                </p>
                <button
                  type="button"
                  className="text-xs px-2 py-1 rounded"
                  style={{ border: "1px solid var(--border)" }}
                  onClick={async () => {
                    setAdminLoading(true);
                    try {
                      setAdminUsers(await listUsers());
                    } finally {
                      setAdminLoading(false);
                    }
                  }}
                >
                  {adminLoading ? "Loading..." : "Refresh"}
                </button>
              </div>
              <div className="max-h-40 overflow-auto flex flex-col gap-2">
                {adminUsers.map((managedUser) => (
                  <div key={managedUser.id} className="flex items-center justify-between text-xs">
                    <span style={{ color: "var(--text-secondary)" }}>
                      {managedUser.email} ({managedUser.role})
                    </span>
                    <button
                      type="button"
                      style={{ border: "1px solid var(--border)" }}
                      className="px-2 py-0.5 rounded"
                      onClick={async () => {
                        const next = await updateUser(managedUser.id, {
                          is_active: !managedUser.is_active,
                        });
                        setAdminUsers((current) =>
                          current.map((item) => (item.id === next.id ? next : item))
                        );
                      }}
                    >
                      {managedUser.is_active ? "Disable" : "Enable"}
                    </button>
                  </div>
                ))}
              </div>
            </div>
          ) : null}
        </div>

        <div
          className="flex items-center justify-between px-5 py-4"
          style={{ borderTop: "1px solid var(--border)" }}
        >
          <button
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
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm"
            style={{ background: "var(--bg-surface)", color: "var(--text-secondary)", border: "1px solid var(--border)" }}
          >
            <RotateCcw size={14} />
            Reset Defaults
          </button>
          <button
            type="button"
            onClick={onClose}
            className="px-5 py-2 rounded-lg text-sm font-medium"
            style={{ background: "var(--accent)", color: "var(--accent-fg)" }}
          >
            Done
          </button>
        </div>
      </div>
    </div>
  );
}

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
      <label className="text-xs font-semibold uppercase tracking-wider" style={{ color: "var(--text-tertiary)" }}>
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
          className="w-full rounded-lg px-3 py-2.5 pl-9 text-sm outline-none"
          style={{
            background: "var(--bg-surface)",
            border: "1px solid var(--border)",
            color: "var(--text-primary)",
          }}
        />
      </div>
      <p className="text-xs" style={{ color: "var(--text-muted)" }}>
        {help}
      </p>
    </div>
  );
}

function PresetField({
  label,
  value,
  onChange,
  options,
  listId,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: string[];
  listId: string;
}) {
  return (
    <div className="flex flex-col gap-2">
      <label className="text-xs font-semibold uppercase tracking-wider" style={{ color: "var(--text-tertiary)" }}>
        {label}
      </label>
      <input
        list={listId}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="w-full rounded-lg px-3 py-2.5 text-sm outline-none"
        style={{
          background: "var(--bg-surface)",
          border: "1px solid var(--border)",
          color: "var(--text-primary)",
        }}
      />
      <datalist id={listId}>
        {options.map((option) => (
          <option key={option} value={option} />
        ))}
      </datalist>
    </div>
  );
}

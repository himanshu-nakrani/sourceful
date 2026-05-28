"use client";

import React, {
  createContext,
  useContext,
  useEffect,
  useReducer,
  type Dispatch,
  type ReactNode,
} from "react";
import { listWorkspaces, me, type AuthUser, type Provider, type Workspace } from "./api";

export interface AppSettings {
  provider: Provider;
  chatModel: string;
  embeddingModel: string;
  providerApiKey: string;
  clientSessionId: string;
  topK: number;
  similarityThreshold: number;
  theme: "dark" | "light";
  highContrast: boolean;
  reducedMotion: boolean;
  accentPack: "terracotta" | "emerald" | "amber";
  chatLayout: "default" | "focus" | "research";
}

interface SessionSecrets {
  providerApiKey?: string;
  clientSessionId?: string;
  authToken?: string;
}

export interface AppState {
  settings: AppSettings;
  currentUser: AuthUser | null;
  authLoading: boolean;
  activeDocumentId: string | null;
  activeDocumentIds: string[];
  activeConversationId: string | null;
  activeView: "chat" | "insights" | "users" | "models";
  sidebarOpen: boolean;
  settingsOpen: boolean;
  setupComplete: boolean;
  // Phase 0: workspace state.
  workspaces: Workspace[];
  activeWorkspaceId: string | null;
  workspacesLoading: boolean;
  workspacesError: string | null;
}

const DEFAULT_CHAT: Record<Provider, string> = {
  openai: "gpt-4o-mini",
  gemini: "gemini-2.0-flash",
  // vertex_search: "gemini-2.0-flash",
};

const DEFAULT_EMBEDDING: Record<Provider, string> = {
  openai: "text-embedding-3-small",
  gemini: "models/gemini-embedding-001",
  // vertex_search: "vertex_search_managed",
};

/**
 * Generate a client session identifier.
 *
 * When the Web Crypto API's `crypto.randomUUID` is available, the returned value is that UUID;
 * otherwise the function returns a fallback string of the form `rag-<timestamp>-<randomHex>`.
 *
 * @returns A string session identifier — a UUID when supported, otherwise a `rag-<timestamp>-<randomHex>` fallback.
 */
function generateClientSessionId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `rag-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

/**
 * Determines whether a non-empty auth token is present in session storage under the `rag-session` key.
 *
 * @returns `true` if a non-empty `authToken` exists and is accessible in `sessionStorage["rag-session"]`, `false` otherwise (including when not running in a browser or when parsing/accessing storage fails).
 */
function hasStoredAuthToken(): boolean {
  if (typeof window === "undefined") return false;
  try {
    const rawSecrets = sessionStorage.getItem("rag-session");
    if (!rawSecrets) return false;
    const parsed = JSON.parse(rawSecrets) as SessionSecrets;
    return Boolean(parsed.authToken?.trim());
  } catch {
    return false;
  }
}

/**
 * Resolve and return the application's settings by combining defaults with any persisted preferences and session secrets available in the browser.
 *
 * Loads theme from localStorage for all users. When a stored session auth token exists, additional non-sensitive preferences (provider, chatModel, embeddingModel, topK, similarityThreshold) are loaded from localStorage. Session-scoped secrets (providerApiKey, clientSessionId) are read from sessionStorage for both authenticated and anonymous users so anonymous sessions can resume after refresh.
 *
 * @returns An AppSettings object containing the resolved `provider`, `chatModel`, `embeddingModel`, `providerApiKey`, `clientSessionId`, `topK`, `similarityThreshold`, and `theme`. `providerApiKey` will be empty unless found in session storage; `clientSessionId` will be generated if not present.
 */
function loadSettings(): AppSettings {
  if (typeof window === "undefined") {
    return {
      provider: "openai",
      chatModel: DEFAULT_CHAT.openai,
      embeddingModel: DEFAULT_EMBEDDING.openai,
      providerApiKey: "",
      clientSessionId: "",
      topK: 5,
      similarityThreshold: 0.0,
      theme: "dark",
      highContrast: false,
      reducedMotion: false,
      accentPack: "terracotta",
      chatLayout: "default",
    };
  }

  const isAuthenticated = hasStoredAuthToken();

  let provider: Provider = "openai";
  let chatModel = DEFAULT_CHAT.openai;
  let embeddingModel = DEFAULT_EMBEDDING.openai;
  let providerApiKey = "";

  let topK = 5;
  let similarityThreshold = 0.0;
  let theme: "dark" | "light" = "dark";
  let highContrast = false;
  let reducedMotion = false;
  let accentPack: "terracotta" | "emerald" | "amber" = "terracotta";
  let chatLayout: "default" | "focus" | "research" = "default";

  // Load theme from localStorage regardless of auth state (it's not sensitive)
  try {
    const rawPrefs = localStorage.getItem("rag-prefs");
    if (rawPrefs) {
      const parsed = JSON.parse(rawPrefs) as Partial<AppSettings>;
      if (parsed.theme === "light" || parsed.theme === "dark") theme = parsed.theme;
      if (typeof parsed.highContrast === "boolean") highContrast = parsed.highContrast;
      if (typeof parsed.reducedMotion === "boolean") reducedMotion = parsed.reducedMotion;
      if (parsed.accentPack === "terracotta" || parsed.accentPack === "emerald" || parsed.accentPack === "amber") accentPack = parsed.accentPack;
      if (parsed.chatLayout === "focus" || parsed.chatLayout === "research") chatLayout = parsed.chatLayout;
    }
  } catch {
    // Use default
  }

  if (isAuthenticated) {
    // For authenticated users: load persisted settings
    try {
      const rawPrefs = localStorage.getItem("rag-prefs");
      if (rawPrefs) {
        const parsed = JSON.parse(rawPrefs) as Partial<AppSettings>;
        const validProviders: Provider[] = ["openai", "gemini"];
        provider = validProviders.includes(parsed.provider as Provider) ? (parsed.provider as Provider) : "openai";
        chatModel = parsed.chatModel ?? DEFAULT_CHAT[provider];
        embeddingModel = parsed.embeddingModel ?? DEFAULT_EMBEDDING[provider];
        if (typeof parsed.topK === "number") topK = parsed.topK;
        if (typeof parsed.similarityThreshold === "number") similarityThreshold = parsed.similarityThreshold;
      }
    } catch {
      // Use defaults
    }
  }

  // Load session-scoped secrets for both authenticated and anonymous users.
  // Anonymous access relies on a stable clientSessionId across refreshes (scopes backend data to anon:<clientSessionId>).
  let existingSecrets: SessionSecrets = {};
  try {
    const rawSecrets = sessionStorage.getItem("rag-session");
    existingSecrets = rawSecrets ? (JSON.parse(rawSecrets) as SessionSecrets) : {};
  } catch {
    existingSecrets = {};
  }
  providerApiKey = existingSecrets.providerApiKey ?? "";
  let clientSessionId = existingSecrets.clientSessionId ?? "";

  // Generate new session ID if not found or anonymous
  if (!clientSessionId) {
    clientSessionId = generateClientSessionId();
  }

  // Always persist the client session ID so anonymous users can resume their session after refresh.
  try {
    sessionStorage.setItem(
      "rag-session",
      JSON.stringify({
        ...existingSecrets,
        clientSessionId,
      })
    );
  } catch {
    // ignore
  }

  return {
    provider,
    chatModel,
    embeddingModel,
    providerApiKey,
    clientSessionId,
    topK,
    similarityThreshold,
    theme,
    highContrast,
    reducedMotion,
    accentPack,
    chatLayout,
  };
}

const initialState: AppState = {
  settings: loadSettings(),
  currentUser: null,
  authLoading: true,
  activeDocumentId: null,
  activeDocumentIds: [],
  activeConversationId: null,
  activeView: "chat",
  sidebarOpen: true,
  settingsOpen: false,
  setupComplete: false, // Always start as false - in-memory only, never persisted for anonymous users
  workspaces: [],
  activeWorkspaceId: null,
  workspacesLoading: false,
  workspacesError: null,
};

type Action =
  | { type: "SET_SETTINGS"; payload: Partial<AppSettings> }
  | { type: "SET_CURRENT_USER"; payload: AuthUser | null }
  | { type: "SET_AUTH_LOADING"; payload: boolean }
  | { type: "SET_PROVIDER"; payload: Provider }
  | { type: "SET_ACTIVE_DOCUMENT"; payload: string | null }
  | { type: "TOGGLE_DOCUMENT_SELECTION"; payload: string }
  | { type: "SET_ACTIVE_DOCUMENT_IDS"; payload: string[] }
  | { type: "SET_ACTIVE_CONVERSATION"; payload: string | null }
  | { type: "SET_ACTIVE_VIEW"; payload: "chat" | "insights" | "users" | "models" }
  | { type: "TOGGLE_SIDEBAR" }
  | { type: "SET_SIDEBAR"; payload: boolean }
  | { type: "TOGGLE_SETTINGS" }
  | { type: "SET_SETTINGS_OPEN"; payload: boolean }
  | { type: "SET_SETUP_COMPLETE"; payload: boolean }
  | { type: "SET_WORKSPACES"; payload: Workspace[] }
  | { type: "SET_ACTIVE_WORKSPACE"; payload: string | null }
  | { type: "UPSERT_WORKSPACE"; payload: Workspace }
  | { type: "SET_WORKSPACES_LOADING"; payload: boolean }
  | { type: "SET_WORKSPACES_ERROR"; payload: string | null };

/**
 * Persist selected app settings to browser storage.
 *
 * Always writes the user's `theme` to localStorage (under "rag-prefs"). When `isAuthenticated` is
 * true, also persists provider, model selections, `topK`, and `similarityThreshold` to localStorage.
 * Session-scoped secrets (`providerApiKey` and `clientSessionId`) are stored in sessionStorage (under
 * "rag-session") for both authenticated and anonymous users so anonymous sessions can resume after refresh.
 *
 * @param next - The full AppSettings object whose values should be persisted.
 * @param isAuthenticated - Whether the current session is authenticated; controls which
 *                          settings are persisted beyond theme.
 */
function persistSettings(next: AppSettings, isAuthenticated: boolean): void {
  if (typeof window === "undefined") return;

  // Always persist theme and display preferences regardless of auth
  try {
    const rawPrefs = localStorage.getItem("rag-prefs");
    const existing = rawPrefs ? JSON.parse(rawPrefs) : {};
    localStorage.setItem("rag-prefs", JSON.stringify({
      ...existing,
      theme: next.theme,
      highContrast: next.highContrast,
      reducedMotion: next.reducedMotion,
      accentPack: next.accentPack,
      chatLayout: next.chatLayout,
    }));
  } catch {
    // ignore
  }

  // Only persist other settings for authenticated users
  if (isAuthenticated) {
    try {
      const rawPrefs = localStorage.getItem("rag-prefs");
      const existing = rawPrefs ? JSON.parse(rawPrefs) : {};
      localStorage.setItem(
        "rag-prefs",
        JSON.stringify({
          ...existing,
          provider: next.provider,
          chatModel: next.chatModel,
          embeddingModel: next.embeddingModel,
          topK: next.topK,
          similarityThreshold: next.similarityThreshold,
          theme: next.theme,
          highContrast: next.highContrast,
          reducedMotion: next.reducedMotion,
          accentPack: next.accentPack,
          chatLayout: next.chatLayout,
        })
      );
    } catch {
      // ignore
    }
  }

  // Always persist session-scoped secrets so anonymous users can resume after refresh.
  let existing: SessionSecrets = {};
  try {
    const rawSecrets = sessionStorage.getItem("rag-session");
    existing = rawSecrets ? (JSON.parse(rawSecrets) as SessionSecrets) : {};
  } catch {
    existing = {};
  }
  const clientSessionId = next.clientSessionId || existing.clientSessionId || generateClientSessionId();
  try {
    sessionStorage.setItem(
      "rag-session",
      JSON.stringify({
        ...existing,
        providerApiKey: next.providerApiKey,
        clientSessionId,
      })
    );
  } catch {
    // ignore
  }
}

/**
 * Produce the next application state given the current state and an action.
 *
 * Handles all store actions (settings, auth, document/conversation/view, UI toggles, and in-memory flags).
 * When settings are updated, relevant values are persisted (auth-dependent) and, if `theme` is provided, the document's `data-theme` attribute is updated in the browser. The `setupComplete` flag is kept in-memory and is not persisted.
 *
 * @param state - The current application state
 * @param action - The action describing the update to apply
 * @returns The new application state after applying the action
 */
function reducer(state: AppState, action: Action): AppState {
  switch (action.type) {
    case "SET_SETTINGS": {
      const next = { ...state.settings, ...action.payload };
      persistSettings(next, Boolean(state.currentUser));
      if (typeof document !== "undefined") {
        if (action.payload.theme) {
          document.documentElement.setAttribute("data-theme", next.theme);
        }
        if (action.payload.highContrast !== undefined) {
          if (next.highContrast) {
            document.documentElement.setAttribute("data-contrast", "high");
          } else {
            document.documentElement.removeAttribute("data-contrast");
          }
        }
        if (action.payload.reducedMotion !== undefined) {
          if (next.reducedMotion) {
            document.documentElement.setAttribute("data-motion", "reduced");
          } else {
            document.documentElement.removeAttribute("data-motion");
          }
        }
        if (action.payload.accentPack !== undefined) {
          if (next.accentPack === "terracotta") {
            document.documentElement.removeAttribute("data-accent");
          } else {
            document.documentElement.setAttribute("data-accent", next.accentPack);
          }
        }
      }
      return { ...state, settings: next };
    }
    case "SET_PROVIDER": {
      const provider = action.payload;
      const next = {
        ...state.settings,
        provider,
        chatModel: DEFAULT_CHAT[provider],
        embeddingModel: DEFAULT_EMBEDDING[provider],
      };
      persistSettings(next, Boolean(state.currentUser));
      return { ...state, settings: next };
    }
    case "SET_CURRENT_USER":
      return { ...state, currentUser: action.payload };
    case "SET_AUTH_LOADING":
      return { ...state, authLoading: action.payload };
    case "SET_ACTIVE_DOCUMENT":
      return {
        ...state,
        activeDocumentId: action.payload,
        activeDocumentIds: action.payload ? [action.payload] : [],
        activeConversationId: null,
        activeView: "chat",
      };
    case "TOGGLE_DOCUMENT_SELECTION": {
      const id = action.payload;
      const ids = state.activeDocumentIds;
      const next = ids.includes(id) ? ids.filter((d) => d !== id) : [...ids, id];
      return {
        ...state,
        activeDocumentIds: next,
        activeDocumentId: next.length > 0 ? next[0] : null,
        activeConversationId: null,
      };
    }
    case "SET_ACTIVE_DOCUMENT_IDS":
      return {
        ...state,
        activeDocumentIds: action.payload,
        activeDocumentId: action.payload.length > 0 ? action.payload[0] : null,
        activeConversationId: null,
      };
    case "SET_ACTIVE_CONVERSATION":
      return { ...state, activeConversationId: action.payload, activeView: "chat" };
    case "SET_ACTIVE_VIEW":
      return { ...state, activeView: action.payload };
    case "TOGGLE_SIDEBAR":
      return { ...state, sidebarOpen: !state.sidebarOpen };
    case "SET_SIDEBAR":
      return { ...state, sidebarOpen: action.payload };
    case "TOGGLE_SETTINGS":
      return { ...state, settingsOpen: !state.settingsOpen };
    case "SET_SETTINGS_OPEN":
      return { ...state, settingsOpen: action.payload };
    case "SET_SETUP_COMPLETE":
      // Never persist setupComplete - it's in-memory only
      // For anonymous users: flushed on reload
      // For authenticated users: managed by auth state
      return { ...state, setupComplete: action.payload };
    case "SET_WORKSPACES": {
      const workspaces = action.payload;
      const stillActive = workspaces.find((w) => w.id === state.activeWorkspaceId);
      const activeWorkspaceId = stillActive
        ? stillActive.id
        : (workspaces.find((w) => w.is_default) ?? workspaces[0])?.id ?? null;
      return { ...state, workspaces, activeWorkspaceId };
    }
    case "SET_ACTIVE_WORKSPACE":
      return { ...state, activeWorkspaceId: action.payload };
    case "UPSERT_WORKSPACE": {
      const next = action.payload;
      const existing = state.workspaces.find((w) => w.id === next.id);
      const workspaces = existing
        ? state.workspaces.map((w) => (w.id === next.id ? next : w))
        : [...state.workspaces, next];
      return {
        ...state,
        workspaces,
        activeWorkspaceId: state.activeWorkspaceId ?? next.id,
      };
    }
    case "SET_WORKSPACES_LOADING":
      return { ...state, workspacesLoading: action.payload };
    case "SET_WORKSPACES_ERROR":
      return { ...state, workspacesError: action.payload };
    default:
      return state;
  }
}

const StoreContext = createContext<{
  state: AppState;
  dispatch: Dispatch<Action>;
}>({
  state: initialState,
  dispatch: () => undefined,
});

export function StoreProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(reducer, initialState);

  useEffect(() => {
    dispatch({ type: "SET_SETTINGS", payload: loadSettings() });
  }, []);

  // Phase 0 bootstrap: resolve workspaces (server auto-creates a default).
  const clientSessionId = state.settings.clientSessionId;
  useEffect(() => {
    if (!clientSessionId) return;
    let cancelled = false;
    const run = async () => {
      dispatch({ type: "SET_WORKSPACES_LOADING", payload: true });
      dispatch({ type: "SET_WORKSPACES_ERROR", payload: null });
      try {
        const workspaces = await listWorkspaces({ clientSessionId });
        if (!cancelled) {
          dispatch({ type: "SET_WORKSPACES", payload: workspaces });
        }
      } catch (err) {
        if (!cancelled) {
          dispatch({
            type: "SET_WORKSPACES_ERROR",
            payload: err instanceof Error ? err.message : "Failed to load workspaces.",
          });
        }
      } finally {
        if (!cancelled) {
          dispatch({ type: "SET_WORKSPACES_LOADING", payload: false });
        }
      }
    };
    void run();
    return () => {
      cancelled = true;
    };
  }, [clientSessionId]);

  useEffect(() => {
    let cancelled = false;
    const loadMe = async () => {
      if (!hasStoredAuthToken()) {
        dispatch({ type: "SET_CURRENT_USER", payload: null });
        dispatch({ type: "SET_AUTH_LOADING", payload: false });
        return;
      }
      dispatch({ type: "SET_AUTH_LOADING", payload: true });
      try {
        const user = await me();
        if (!cancelled) {
          dispatch({ type: "SET_CURRENT_USER", payload: user });
        }
      } catch {
        if (!cancelled) {
          dispatch({ type: "SET_CURRENT_USER", payload: null });
        }
      } finally {
        if (!cancelled) {
          dispatch({ type: "SET_AUTH_LOADING", payload: false });
        }
      }
    };
    void loadMe();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <StoreContext.Provider value={{ state, dispatch }}>
      {children}
    </StoreContext.Provider>
  );
}

export function useStore() {
  return useContext(StoreContext);
}

export { DEFAULT_CHAT, DEFAULT_EMBEDDING };

"use client";

import React, {
  createContext,
  useContext,
  useEffect,
  useReducer,
  type Dispatch,
  type ReactNode,
} from "react";
import { me, type AuthUser, type Provider } from "./api";

export interface AppSettings {
  provider: Provider;
  chatModel: string;
  embeddingModel: string;
  providerApiKey: string;
  clientSessionId: string;
}

export interface AppState {
  settings: AppSettings;
  currentUser: AuthUser | null;
  authLoading: boolean;
  activeDocumentId: string | null;
  activeConversationId: string | null;
  sidebarOpen: boolean;
  settingsOpen: boolean;
}

const DEFAULT_CHAT: Record<Provider, string> = {
  openai: "gpt-4o-mini",
  gemini: "gemini-2.0-flash",
};

const DEFAULT_EMBEDDING: Record<Provider, string> = {
  openai: "text-embedding-3-small",
  gemini: "models/gemini-embedding-001",
};

function generateClientSessionId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `rag-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function loadSettings(): AppSettings {
  if (typeof window === "undefined") {
    return {
      provider: "openai",
      chatModel: DEFAULT_CHAT.openai,
      embeddingModel: DEFAULT_EMBEDDING.openai,
      providerApiKey: "",
      clientSessionId: "",
    };
  }

  let provider: Provider = "openai";
  let chatModel = DEFAULT_CHAT.openai;
  let embeddingModel = DEFAULT_EMBEDDING.openai;
  try {
    const rawPrefs = localStorage.getItem("rag-prefs");
    if (rawPrefs) {
      const parsed = JSON.parse(rawPrefs) as Partial<AppSettings>;
      provider = parsed.provider === "gemini" ? "gemini" : "openai";
      chatModel = parsed.chatModel ?? DEFAULT_CHAT[provider];
      embeddingModel = parsed.embeddingModel ?? DEFAULT_EMBEDDING[provider];
    }
  } catch {
    // Use defaults.
  }

  let providerApiKey = "";
  let clientSessionId = "";
  try {
    const rawSecrets = sessionStorage.getItem("rag-session");
    if (rawSecrets) {
      const parsed = JSON.parse(rawSecrets) as Partial<AppSettings>;
      providerApiKey = parsed.providerApiKey ?? "";
      clientSessionId = parsed.clientSessionId ?? "";
    }
  } catch {
    // Use defaults.
  }

  if (!clientSessionId) {
    clientSessionId = generateClientSessionId();
    sessionStorage.setItem(
      "rag-session",
      JSON.stringify({ providerApiKey, clientSessionId })
    );
  }

  return {
    provider,
    chatModel,
    embeddingModel,
    providerApiKey,
    clientSessionId,
  };
}

const initialState: AppState = {
  settings: loadSettings(),
  currentUser: null,
  authLoading: true,
  activeDocumentId: null,
  activeConversationId: null,
  sidebarOpen: true,
  settingsOpen: false,
};

type Action =
  | { type: "SET_SETTINGS"; payload: Partial<AppSettings> }
  | { type: "SET_CURRENT_USER"; payload: AuthUser | null }
  | { type: "SET_AUTH_LOADING"; payload: boolean }
  | { type: "SET_PROVIDER"; payload: Provider }
  | { type: "SET_ACTIVE_DOCUMENT"; payload: string | null }
  | { type: "SET_ACTIVE_CONVERSATION"; payload: string | null }
  | { type: "TOGGLE_SIDEBAR" }
  | { type: "SET_SIDEBAR"; payload: boolean }
  | { type: "TOGGLE_SETTINGS" }
  | { type: "SET_SETTINGS_OPEN"; payload: boolean };

function persistSettings(next: AppSettings): void {
  if (typeof window === "undefined") return;
  localStorage.setItem(
    "rag-prefs",
    JSON.stringify({
      provider: next.provider,
      chatModel: next.chatModel,
      embeddingModel: next.embeddingModel,
    })
  );
  sessionStorage.setItem(
    "rag-session",
    JSON.stringify({
      providerApiKey: next.providerApiKey,
      clientSessionId: next.clientSessionId || generateClientSessionId(),
    })
  );
}

function reducer(state: AppState, action: Action): AppState {
  switch (action.type) {
    case "SET_SETTINGS": {
      const next = { ...state.settings, ...action.payload };
      persistSettings(next);
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
      persistSettings(next);
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
        activeConversationId: null,
      };
    case "SET_ACTIVE_CONVERSATION":
      return { ...state, activeConversationId: action.payload };
    case "TOGGLE_SIDEBAR":
      return { ...state, sidebarOpen: !state.sidebarOpen };
    case "SET_SIDEBAR":
      return { ...state, sidebarOpen: action.payload };
    case "TOGGLE_SETTINGS":
      return { ...state, settingsOpen: !state.settingsOpen };
    case "SET_SETTINGS_OPEN":
      return { ...state, settingsOpen: action.payload };
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

  useEffect(() => {
    let cancelled = false;
    const loadMe = async () => {
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

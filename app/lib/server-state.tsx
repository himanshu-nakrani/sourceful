"use client";

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import {
  getConversation,
  getDocumentChunks,
  listConversations,
  listDocuments,
  type ChunkPreview,
  type ConversationListItem,
  type DocumentInfo,
  type Message,
  type Citation,
} from "./api";
import { useStore } from "./store";

interface ServerStateValue {
  documents: DocumentInfo[];
  documentsLoading: boolean;
  documentsError: string | null;
  conversations: ConversationListItem[];
  conversationsLoading: boolean;
  conversationsError: string | null;
  messages: Message[];
  messagesLoading: boolean;
  messagesError: string | null;
  chunkPreview: ChunkPreview[];
  chunkPreviewLoading: boolean;
  refreshDocuments: () => Promise<void>;
  refreshConversations: (documentId?: string | null) => Promise<void>;
  refreshChunkPreview: (documentId?: string | null) => Promise<void>;
  selectDocument: (documentId: string | null) => Promise<void>;
  selectConversation: (conversationId: string | null) => Promise<void>;
  setMessages: React.Dispatch<React.SetStateAction<Message[]>>;
  addMessage: (message: Message) => void;
  appendToLastAssistant: (token: string) => void;
  updateLastAssistantSources: (sources: Citation[]) => void;
}

const ServerStateContext = createContext<ServerStateValue | null>(null);

export function ServerStateProvider({ children }: { children: ReactNode }) {
  const { state, dispatch } = useStore();
  const auth = useMemo(
    () => ({
      clientSessionId: state.settings.clientSessionId,
    }),
    [state.settings.clientSessionId]
  );

  const [documents, setDocuments] = useState<DocumentInfo[]>([]);
  const [documentsLoading, setDocumentsLoading] = useState(false);
  const [documentsError, setDocumentsError] = useState<string | null>(null);
  const [conversations, setConversations] = useState<ConversationListItem[]>([]);
  const [conversationsLoading, setConversationsLoading] = useState(false);
  const [conversationsError, setConversationsError] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [messagesLoading, setMessagesLoading] = useState(false);
  const [messagesError, setMessagesError] = useState<string | null>(null);
  const [chunkPreview, setChunkPreview] = useState<ChunkPreview[]>([]);
  const [chunkPreviewLoading, setChunkPreviewLoading] = useState(false);

  const refreshDocuments = useCallback(async () => {
    if (!auth.clientSessionId) return;
    setDocumentsLoading(true);
    try {
      const nextDocuments = await listDocuments(auth);
      setDocuments(nextDocuments);
      setDocumentsError(null);
      if (
        state.activeDocumentId &&
        !nextDocuments.some((document) => document.id === state.activeDocumentId)
      ) {
        dispatch({ type: "SET_ACTIVE_DOCUMENT", payload: null });
        setConversations([]);
        setMessages([]);
        setChunkPreview([]);
      }
    } catch (error) {
      setDocumentsError(
        error instanceof Error ? error.message : "Unable to load documents."
      );
    } finally {
      setDocumentsLoading(false);
    }
  }, [auth, dispatch, state.activeDocumentId]);

  const refreshConversations = useCallback(
    async (documentId?: string | null) => {
      const target = documentId ?? state.activeDocumentId;
      if (!auth.clientSessionId || !target) {
        setConversations([]);
        return;
      }
      setConversationsLoading(true);
      try {
        const nextConversations = await listConversations(auth, target);
        setConversations(nextConversations);
        setConversationsError(null);
      } catch (error) {
        setConversationsError(
          error instanceof Error
            ? error.message
            : "Unable to load conversations."
        );
      } finally {
        setConversationsLoading(false);
      }
    },
    [auth, state.activeDocumentId]
  );

  const refreshChunkPreview = useCallback(
    async (documentId?: string | null) => {
      const target = documentId ?? state.activeDocumentId;
      if (!auth.clientSessionId || !target) {
        setChunkPreview([]);
        return;
      }
      setChunkPreviewLoading(true);
      try {
        const nextPreview = await getDocumentChunks(auth, target);
        setChunkPreview(nextPreview);
      } catch {
        setChunkPreview([]);
      } finally {
        setChunkPreviewLoading(false);
      }
    },
    [auth, state.activeDocumentId]
  );

  const selectDocument = useCallback(
    async (documentId: string | null) => {
      dispatch({ type: "SET_ACTIVE_DOCUMENT", payload: documentId });
      dispatch({ type: "SET_ACTIVE_CONVERSATION", payload: null });
      setMessages([]);
      if (!documentId) {
        setConversations([]);
        setChunkPreview([]);
        return;
      }
      await Promise.all([
        refreshConversations(documentId),
        refreshChunkPreview(documentId),
      ]);
    },
    [dispatch, refreshChunkPreview, refreshConversations]
  );

  const selectConversation = useCallback(
    async (conversationId: string | null) => {
      dispatch({ type: "SET_ACTIVE_CONVERSATION", payload: conversationId });
      if (!conversationId) {
        setMessages([]);
        return;
      }
      setMessagesLoading(true);
      try {
        const conversation = await getConversation(auth, conversationId);
        setMessages(conversation.messages);
        setMessagesError(null);
      } catch (error) {
        setMessagesError(
          error instanceof Error ? error.message : "Unable to load messages."
        );
      } finally {
        setMessagesLoading(false);
      }
    },
    [auth, dispatch]
  );

  const addMessage = useCallback((message: Message) => {
    setMessages((current) => [...current, message]);
  }, []);

  const appendToLastAssistant = useCallback((token: string) => {
    setMessages((current) => {
      const next = [...current];
      const last = next[next.length - 1];
      if (last && last.role === "assistant") {
        next[next.length - 1] = { ...last, content: last.content + token };
      }
      return next;
    });
  }, []);

  const updateLastAssistantSources = useCallback((sources: Citation[]) => {
    setMessages((current) => {
      const next = [...current];
      const last = next[next.length - 1];
      if (last && last.role === "assistant") {
        next[next.length - 1] = { ...last, sources };
      }
      return next;
    });
  }, []);

  useEffect(() => {
    if (!auth.clientSessionId) return;
    void refreshDocuments();
  }, [auth.clientSessionId, refreshDocuments]);

  useEffect(() => {
    if (!documents.some((document) => ["queued", "processing"].includes(document.status))) {
      return;
    }
    const handle = window.setInterval(() => {
      void refreshDocuments();
    }, 4000);
    return () => window.clearInterval(handle);
  }, [documents, refreshDocuments]);

  const value = useMemo<ServerStateValue>(
    () => ({
      documents,
      documentsLoading,
      documentsError,
      conversations,
      conversationsLoading,
      conversationsError,
      messages,
      messagesLoading,
      messagesError,
      chunkPreview,
      chunkPreviewLoading,
      refreshDocuments,
      refreshConversations,
      refreshChunkPreview,
      selectDocument,
      selectConversation,
      setMessages,
      addMessage,
      appendToLastAssistant,
      updateLastAssistantSources,
    }),
    [
      addMessage,
      appendToLastAssistant,
      chunkPreview,
      chunkPreviewLoading,
      conversations,
      conversationsError,
      conversationsLoading,
      documents,
      documentsError,
      documentsLoading,
      messages,
      messagesError,
      messagesLoading,
      refreshChunkPreview,
      refreshConversations,
      refreshDocuments,
      selectConversation,
      selectDocument,
      updateLastAssistantSources,
    ]
  );

  return (
    <ServerStateContext.Provider value={value}>
      {children}
    </ServerStateContext.Provider>
  );
}

export function useServerState() {
  const context = useContext(ServerStateContext);
  if (!context) {
    throw new Error("useServerState must be used within ServerStateProvider");
  }
  return context;
}

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
  /** Fix 5.2: stream mutations are targeted at a specific message id, so a
   *  stale event from an aborted stream can never contaminate whichever
   *  assistant bubble happens to be last. Unknown ids are a no-op. */
  appendToMessage: (messageId: string, token: string) => void;
  updateMessageSources: (messageId: string, sources: Citation[]) => void;
  /** Swap the temp client-side id for the durable id returned by the backend,
   *  so downstream actions like feedback writes (Phase 3.8) reference the
   *  persisted message. */
  updateMessageId: (tempId: string, durableId: string) => void;
}

const ServerStateContext = createContext<ServerStateValue | null>(null);

/**
 * Provides server-derived application state and imperative actions to descendant components via ServerStateContext.
 *
 * The provider manages documents, conversations, messages, and chunk preview state along with loading/error flags,
 * and exposes imperative actions to refresh or select those resources.
 *
 * @param children - The subtree that will receive the server state context
 * @returns The ServerStateContext provider element that supplies server-sourced state and actions to its descendants
 */
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

  const selectConversationSeqRef = React.useRef(0);
  const documentDataSeqRef = React.useRef(0);
  // Live active document id for async callbacks; synced at commit (before
  // any passive effect or async continuation reads it), not during render.
  const activeDocumentIdRef = React.useRef(state.activeDocumentId);
  React.useLayoutEffect(() => {
    activeDocumentIdRef.current = state.activeDocumentId;
  }, [state.activeDocumentId]);

  const refreshDocuments = useCallback(async () => {
    if (!auth.clientSessionId) return;
    setDocumentsLoading(true);
    try {
      const nextDocuments = await listDocuments(auth);
      setDocuments(nextDocuments);
      setDocumentsError(null);
      const activeId = activeDocumentIdRef.current;
      if (activeId && !nextDocuments.some((document) => document.id === activeId)) {
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
  }, [auth, dispatch]);

  const refreshConversations = useCallback(
    async (documentId?: string | null) => {
      const target = documentId ?? activeDocumentIdRef.current;
      const seq = documentDataSeqRef.current;
      if (!auth.clientSessionId || !target) {
        setConversations([]);
        return;
      }
      setConversationsLoading(true);
      try {
        const nextConversations = await listConversations(auth, target);
        if (seq !== documentDataSeqRef.current) return;
        if (target !== activeDocumentIdRef.current) return;
        setConversations(nextConversations);
        setConversationsError(null);
      } catch (error) {
        if (seq !== documentDataSeqRef.current) return;
        setConversationsError(
          error instanceof Error
            ? error.message
            : "Unable to load conversations."
        );
      } finally {
        if (seq === documentDataSeqRef.current) {
          setConversationsLoading(false);
        }
      }
    },
    [auth]
  );

  const refreshChunkPreview = useCallback(
    async (documentId?: string | null) => {
      const target = documentId ?? activeDocumentIdRef.current;
      const seq = documentDataSeqRef.current;
      if (!auth.clientSessionId || !target) {
        setChunkPreview([]);
        return;
      }
      setChunkPreviewLoading(true);
      try {
        const nextPreview = await getDocumentChunks(auth, target);
        if (seq !== documentDataSeqRef.current) return;
        if (target !== activeDocumentIdRef.current) return;
        setChunkPreview(nextPreview);
      } catch {
        if (seq !== documentDataSeqRef.current) return;
        setChunkPreview([]);
      } finally {
        if (seq === documentDataSeqRef.current) {
          setChunkPreviewLoading(false);
        }
      }
    },
    [auth]
  );

  const selectDocument = useCallback(
    async (documentId: string | null) => {
      selectConversationSeqRef.current += 1;
      documentDataSeqRef.current += 1;
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
      // Fix #9: bump the sequence counter first so that a null selection
      // (deselect) also invalidates any in-flight request. Otherwise a
      // pending getConversation could resolve later and overwrite the cleared
      // messages state.
      const seq = ++selectConversationSeqRef.current;
      if (!conversationId) {
        setMessages([]);
        return;
      }
      setMessagesLoading(true);
      try {
        const conversation = await getConversation(auth, conversationId);
        // Only apply if this is still the latest request
        if (seq !== selectConversationSeqRef.current) return;
        setMessages(conversation.messages);
        setMessagesError(null);
      } catch (error) {
        if (seq !== selectConversationSeqRef.current) return;
        setMessagesError(
          error instanceof Error ? error.message : "Unable to load messages."
        );
      } finally {
        if (seq === selectConversationSeqRef.current) {
          setMessagesLoading(false);
        }
      }
    },
    [auth, dispatch]
  );

  const addMessage = useCallback((message: Message) => {
    setMessages((current) => [...current, message]);
  }, []);

  const appendToMessage = useCallback((messageId: string, token: string) => {
    setMessages((current) => {
      const idx = current.findIndex((m) => m.id === messageId);
      if (idx === -1) return current;
      const next = [...current];
      next[idx] = { ...next[idx], content: next[idx].content + token };
      return next;
    });
  }, []);

  const updateMessageSources = useCallback((messageId: string, sources: Citation[]) => {
    setMessages((current) => {
      const idx = current.findIndex((m) => m.id === messageId);
      if (idx === -1) return current;
      const next = [...current];
      next[idx] = { ...next[idx], sources };
      return next;
    });
  }, []);

  const updateMessageId = useCallback((tempId: string, durableId: string) => {
    if (!durableId) return;
    setMessages((current) => {
      const idx = current.findIndex((m) => m.id === tempId);
      if (idx === -1 || current[idx].id === durableId) return current;
      const next = [...current];
      next[idx] = { ...next[idx], id: durableId };
      return next;
    });
  }, []);

  useEffect(() => {
    if (state.authLoading) return;
    // Identity changed: invalidate in-flight requests (seq refs) and wipe the
    // previous identity's data together. Moving the wipe to render would run it
    // before the seq bump, so a late response from the old identity could
    // repopulate the new one's view; the bump must stay in an effect.
    selectConversationSeqRef.current += 1;
    documentDataSeqRef.current += 1;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- must be atomic with the seq bump above
    setConversations([]);
    setMessages([]);
    setChunkPreview([]);
    // Drop the previous identity's document list too. Leaving it in place kept
    // the prior account's documents on screen until refreshDocuments resolved.
    setDocuments([]);
    if (!auth.clientSessionId) return;
    void refreshDocuments();
  }, [state.authLoading, state.currentUser?.id, auth.clientSessionId, refreshDocuments]);

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
      appendToMessage,
      updateMessageSources,
      updateMessageId,
    }),
    [
      addMessage,
      appendToMessage,
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
      updateMessageSources,
      updateMessageId,
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

"use client";

import React, { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { useOnChange } from "../lib/use-on-change";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import {
  AlertTriangle,
  ArrowDown,
  ArrowUp,
  BarChart3,
  BookOpen,
  Bug,
  ChevronDown,
  ChevronRight,
  Focus,
  KeyRound,
  LayoutPanelLeft,
  Loader2,
  Monitor,
  PanelLeftOpen,
  PanelRight,
  RefreshCcw,
  StopCircle,
  SlidersHorizontal,
} from "lucide-react";
import TrustAnalyticsPanel from "./TrustAnalyticsPanel";
import DocumentLibrary from "./DocumentLibrary";
import MessageBubble from "./MessageBubble";
import SourceInspector from "./SourceInspector";
import { MessageSkeleton } from "./Skeleton";
import { Button, EmptyState, ErrorBanner, StatusDot } from "./ui";
import {
  listWorkspaceSources,
  reprocessDocument,
  rerunMessage,
  saveAssistantMessageAsArtifact,
  sendChatStream,
  submitFeedback,
  type ActiveLearningHint,
  type ChatMode,
  type Citation,
  type FeedbackRating,
  type GroundingSummary,
  type Message,
  type RetrievalStages,
  type WorkspaceSource,
} from "../lib/api";
import type { MessageFeedbackState } from "./MessageBubble";
import { useServerState } from "../lib/server-state";
import { useStore } from "../lib/store";
import { useWorkspaceRole } from "../lib/use-workspace-role";
import { EASE_OUT, transitionFast } from "../lib/motion";
import { useToast } from "./Toast";

interface ChatAreaProps {
  onUploadClick: () => void;
}

/** Distance from the bottom (px) within which auto-scroll stays engaged. */
const STICKY_THRESHOLD_PX = 80;

/**
 * Renders the document-aware chat interface, including message display, submission, streaming control,
 * reruns, source citations, conversation management, and contextual empty/error states.
 *
 * This component drives user interactions for asking questions about one or more indexed documents,
 * handles streaming assistant responses, and coordinates conversation lifecycle actions.
 *
 * @param onUploadClick - Callback invoked when the user chooses to upload a document from the empty state
 * @returns The chat area React element
 */
export default function ChatArea({ onUploadClick }: ChatAreaProps) {
  const { state, dispatch } = useStore();
  const {
    documents,
    messages,
    messagesLoading,
    messagesError,
    addMessage,
    appendToMessage,
    refreshConversations,
    selectConversation,
    selectDocument,
    setMessages,
    updateMessageSources,
    updateMessageId,
  } = useServerState();
  const { toast } = useToast();
  const { settings, activeConversationId, activeDocumentId, activeDocumentIds, activeWorkspaceId, sidebarOpen } = state;
  const [chatMode, setChatMode] = useState<ChatMode>("ask");
  const [savingMessageId, setSavingMessageId] = useState<string | null>(null);
  // Phase 1 — per-source retrieval filter. ``null`` means "all ready sources
  // in the workspace" (the default backend behavior). When non-null, contains
  // the explicit ``workspace_sources.id`` values to restrict retrieval to.
  const [workspaceSources, setWorkspaceSources] = useState<WorkspaceSource[]>([]);
  const [selectedSourceIds, setSelectedSourceIds] = useState<string[] | null>(null);
  const [sourceFilterOpen, setSourceFilterOpen] = useState(false);
  const sourceFilterId = React.useId();
  const sourceFilterTriggerRef = useRef<HTMLButtonElement>(null);

  const chatLayout = settings.chatLayout ?? "default";
  const router = useRouter();
  const activeDocument = useMemo(
    () => documents.find((document) => document.id === activeDocumentId) ?? null,
    [documents, activeDocumentId]
  );
  const activeDocuments = useMemo(
    () => documents.filter((d) => activeDocumentIds.includes(d.id)),
    [documents, activeDocumentIds]
  );
  const isMultiDoc = activeDocumentIds.length > 1;
  const [question, setQuestion] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [currentSources, setCurrentSources] = useState<Citation[]>([]);
  const [error, setError] = useState<string | null>(null);
  // A retry is bound to the document/conversation it failed in: the banner
  // only runs it while `stillValid()` holds (see onRetry below), because the
  // retry calls the latest callbacks (current settings) for that context.
  const [errorRetry, setErrorRetry] = useState<null | { run: () => void; stillValid: () => boolean }>(null);
  const [rerunningMessageId, setRerunningMessageId] = useState<string | null>(null);
  const [debugOpen, setDebugOpen] = useState(false);
  const [analyticsOpen, setAnalyticsOpen] = useState(false);
  const [sourcePanelOpen, setSourcePanelOpen] = useState(true);
  const [mobileSourcesOpen, setMobileSourcesOpen] = useState(false);
  const [inspectedSources, setInspectedSources] = useState<Citation[] | null>(null);
  const [selectedChunkId, setSelectedChunkId] = useState<string | null>(null);
  const desktopSourceToggleRef = useRef<HTMLButtonElement>(null);
  const [lastStages, setLastStages] = useState<RetrievalStages | null>(null);
  const [lastLatencyMs, setLastLatencyMs] = useState<number | null>(null);
  const [lastGrounding, setLastGrounding] = useState<GroundingSummary | null>(null);
  const [streamEvents, setStreamEvents] = useState<Array<{ at: number; label: string; detail?: string }>>([]);
  const latestAnswer = useMemo(
    () => [...messages].reverse().find((message) => message.role === "assistant"),
    [messages]
  );
  const visibleSources = inspectedSources ?? (streaming && currentSources.length ? currentSources : latestAnswer?.sources ?? []);
  useOnChange(`${activeDocumentId}:${activeConversationId}:${streaming}`, () => {
    setInspectedSources(null);
    setSelectedChunkId(null);
    setMobileSourcesOpen(false);
  });
  const inspectSources = (sources: Citation[], selected?: Citation) => {
    setInspectedSources(sources);
    setSelectedChunkId((selected ?? sources[0])?.chunk_id ?? null);
    setSourcePanelOpen(true);
    if (!window.matchMedia("(min-width: 1280px)").matches) setMobileSourcesOpen(true);
  };
  const closeSources = () => {
    setSourcePanelOpen(false);
    setMobileSourcesOpen(false);
    if (window.matchMedia("(min-width: 1280px)").matches) desktopSourceToggleRef.current?.focus();
  };

  const [feedbackState, setFeedbackState] = useState<Record<string, MessageFeedbackState>>({});
  const [lastHint, setLastHint] = useState<ActiveLearningHint | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const streamGenRef = useRef(0);
  const streamingRef = useRef(false);
  const streamConversationRef = useRef<string | null>(null);

  // [FIX 5.7] Stick-to-bottom scrolling. ``stickyRef`` mirrors the user's
  // scroll position without re-rendering; ``isSticky`` only drives the
  // "jump to latest" affordance.
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const stickyRef = useRef(true);
  const [isSticky, setIsSticky] = useState(true);

  const auth = useMemo(
    () => ({
      clientSessionId: settings.clientSessionId,
      providerApiKey: settings.providerApiKey,
    }),
    [settings.clientSessionId, settings.providerApiKey]
  );

  const { canEdit } = useWorkspaceRole(auth, activeWorkspaceId ?? "");

  const suggestions = [
    "Summarize the main themes",
    "List the most important findings",
    "What evidence supports the core conclusion?",
    "What should I pay attention to first?",
  ];

  // Live conversation id for async stream callbacks and retry thunks. Synced in
  // a layout effect (commit time, before any passive effect, event handler or
  // async continuation can read it) instead of being written during render.
  const activeConversationIdRef = useRef<string | null>(activeConversationId);
  useLayoutEffect(() => {
    activeConversationIdRef.current = activeConversationId;
  }, [activeConversationId]);
  const activeDocumentIdRef = useRef<string | null>(activeDocumentId ?? null);
  useLayoutEffect(() => {
    activeDocumentIdRef.current = activeDocumentId ?? null;
  }, [activeDocumentId]);
  // Switching documents drops a pending Retry from the previous document.
  useOnChange(activeDocumentId ?? null, () => setErrorRetry(null));

  // Reload the workspace's source list whenever the active workspace changes.
  // The per-source filter is opt-in: by default we keep ``selectedSourceIds``
  // null so retrieval spans every ready source in the workspace.
  const [workspaceSourcesError, setWorkspaceSourcesError] = useState<string | null>(null);

  // [FIX 5.5] Deps now include the memoized `auth` object (so a key change
  // re-fetches instead of reading stale credentials) and failures surface in
  // the source filter instead of silently resolving to an empty list.
  // Leaving a workspace clears its sources and filter. Adjusted during render
  // (no effect round-trip); fetching for a workspace stays in the effect.
  useOnChange(activeWorkspaceId ?? null, (workspaceId) => {
    if (!workspaceId) {
      setWorkspaceSources([]);
      setSelectedSourceIds(null);
      setWorkspaceSourcesError(null);
    }
  });

  useEffect(() => {
    let cancelled = false;
    if (!activeWorkspaceId) return;
    void listWorkspaceSources(auth, activeWorkspaceId)
      .then((sources) => {
        if (cancelled) return;
        setWorkspaceSources(sources);
        setWorkspaceSourcesError(null);
        // Drop any selections that no longer exist (source deleted, workspace
        // switched, etc.). Keep ``null`` if we had no explicit selection.
        setSelectedSourceIds((prev) =>
          prev ? prev.filter((id) => sources.find((s) => s.id === id)) : prev
        );
      })
      .catch((err) => {
        if (cancelled) return;
        setWorkspaceSources([]);
        setWorkspaceSourcesError(err instanceof Error ? err.message : "Failed to load sources.");
      });
    return () => {
      cancelled = true;
    };
  }, [activeWorkspaceId, auth]);

  const handleSaveToWorkspace = useCallback(
    async (message: Message) => {
      if (!activeWorkspaceId || !message.id || message.role !== "assistant") return;
      setSavingMessageId(message.id);
      try {
        await saveAssistantMessageAsArtifact(auth, activeWorkspaceId, {
          message_id: message.id,
          artifact_type: "saved_answer",
        });
        toast({ variant: "success", title: "Saved to workspace" });
      } catch (saveError) {
        toast({
          variant: "error",
          title: "Could not save answer",
          description: saveError instanceof Error ? saveError.message : "Please try again.",
        });
      } finally {
        setSavingMessageId(null);
      }
    },
    [auth, activeWorkspaceId, toast]
  );

  const handleFeedback = useCallback(
    async (message: Message, rating: FeedbackRating) => {
      const conversationId = activeConversationIdRef.current;
      if (
        !conversationId ||
        !message.id ||
        message.role !== "assistant" ||
        message.id.startsWith("temp-")
      ) {
        return;
      }
      setFeedbackState((prev) => ({ ...prev, [message.id]: "pending" }));
      try {
        await submitFeedback(auth, {
          conversation_id: conversationId,
          message_id: message.id,
          rating,
        });
        setFeedbackState((prev) => ({ ...prev, [message.id]: rating }));
      } catch (err) {
        console.error("feedback_failed", err);
        setFeedbackState((prev) => ({ ...prev, [message.id]: "error" }));
      }
    },
    [auth]
  );

  const canAsk = Boolean(
    activeDocumentId &&
      (isMultiDoc ? activeDocuments.every((d) => d.status === "ready") : activeDocument?.status === "ready") &&
      settings.providerApiKey.trim() &&
      settings.chatModel.trim() &&
      question.trim() &&
      !streaming
  );

  // [FIX 5.7] Track whether the user is near the bottom of the transcript so
  // streaming appends only auto-scroll while the view is already anchored to
  // the latest content.
  useEffect(() => {
    const element = scrollContainerRef.current;
    if (!element) return;
    const handleScroll = () => {
      const nearBottom =
        element.scrollHeight - element.scrollTop - element.clientHeight < STICKY_THRESHOLD_PX;
      stickyRef.current = nearBottom;
      setIsSticky(nearBottom);
    };
    element.addEventListener("scroll", handleScroll, { passive: true });
    return () => element.removeEventListener("scroll", handleScroll);
  }, []);

  // [FIX 5.7] Replace the unconditional smooth scroll with stick-to-bottom:
  // instant jumps while tokens stream in, a smooth glide when a new user
  // message starts a turn, and nothing at all when the user has scrolled up.
  useEffect(() => {
    if (!stickyRef.current) return;
    const last = messages[messages.length - 1];
    const startingNewTurn = last?.role === "assistant" && !last.content;
    const behavior: ScrollBehavior = streaming && !startingNewTurn ? "auto" : "smooth";
    endRef.current?.scrollIntoView({ behavior });
  }, [messages, currentSources, streaming]);

  const jumpToLatest = useCallback(() => {
    stickyRef.current = true;
    setIsSticky(true);
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, []);

  // [FIX 5.3] Abort any in-flight stream on unmount so its callbacks can't
  // keep mutating provider state after this screen is gone.
  useEffect(() => () => abortRef.current?.abort(), []);

  useEffect(() => {
    const element = textareaRef.current;
    if (!element) return;
    element.style.height = "auto";
    element.style.height = `${Math.min(element.scrollHeight, 160)}px`;
  }, [question]);

  // Retry thunks call the latest sendPrompt/handleRerun through these refs
  // (synced at commit) instead of referencing the callbacks inside their own
  // definitions, so a retry after fixing e.g. the API key uses current settings.
  const sendPromptRef = useRef<((prompt: string, options?: { replaceFailedTurn?: boolean }) => Promise<void>) | null>(null);
  const handleRerunRef = useRef<((message: Message) => Promise<void>) | null>(null);
  const handleRetryDocumentRef = useRef<(() => Promise<void>) | null>(null);

  const sendPrompt = useCallback(
    async (prompt: string, options?: { replaceFailedTurn?: boolean }) => {
      if (!activeDocumentId || !prompt.trim() || streamingRef.current) return;

      if (options?.replaceFailedTurn) {
        setMessages((current) => {
          const last = current[current.length - 1];
          const prev = current[current.length - 2];
          if (last?.role === "assistant" && prev?.role === "user" && prev.content === prompt) {
            return current.slice(0, -2);
          }
          return current;
        });
      }

      streamingRef.current = true;
      setError(null);
      setErrorRetry(null);
      setCurrentSources([]);
      setLastHint(null);
      setStreaming(true);

      const gen = ++streamGenRef.current;
      // Read the conversation id from the ref, not the captured closure value.
      // The retry thunk installed below re-invokes *this* closure instance, so
      // on the conversation-creating turn the captured `activeConversationId`
      // stays null even after onSources dispatched the real id — the retry then
      // sent conversation_id: null and the mismatch guard aborted it silently.
      const startConversationId = activeConversationIdRef.current;
      streamConversationRef.current = startConversationId;
      const uid = () =>
        typeof crypto !== "undefined" && crypto.randomUUID
          ? crypto.randomUUID()
          : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
      const assistantId = `temp-assistant-${uid()}`;

      const userMessage: Message = {
        id: `temp-user-${uid()}`,
        role: "user",
        content: prompt,
        created_at: new Date().toISOString(),
      };
      const assistantMessage: Message = {
        id: assistantId,
        role: "assistant",
        content: "",
        created_at: new Date().toISOString(),
        sources: [],
      };
      addMessage(userMessage);
      addMessage(assistantMessage);

      const controller = new AbortController();
      abortRef.current = controller;
      const startedAt = performance.now();
      setLastGrounding(null);
      setStreamEvents([{ at: 0, label: "request_sent" }]);

      const appendEvent = (label: string, detail?: string) => {
        setStreamEvents((current) => [
          ...current,
          { at: performance.now() - startedAt, label, detail },
        ]);
      };

      let activeConversation = startConversationId;
      let streamError: Error | null = null;
      let streamClean = false;

      try {
        await sendChatStream(
          auth,
          settings.provider,
          settings.chatModel,
          activeDocumentId,
          prompt,
          startConversationId,
          {
            onSources: (payload) => {
              if (gen !== streamGenRef.current) return;
              appendEvent("sources", `${payload.sources?.length ?? 0} chunks`);
              setCurrentSources(payload.sources);
              setLastStages(payload.stages ?? null);
              setLastHint((payload.stages?.active_learning_hint as ActiveLearningHint | undefined) ?? null);
              updateMessageSources(assistantId, payload.sources);
              activeConversation = payload.conversation_id;
              const current = activeConversationIdRef.current;
              if (current === null || current === payload.conversation_id) {
                streamConversationRef.current = payload.conversation_id;
                dispatch({ type: "SET_ACTIVE_CONVERSATION", payload: payload.conversation_id });
              }
            },
            onToken: (delta) => {
              if (gen !== streamGenRef.current) return;
              appendToMessage(assistantId, delta);
            },
            onGrounding: (grounding) => {
              if (gen !== streamGenRef.current) return;
              appendEvent(
                "grounding",
                grounding.score !== null ? `score=${grounding.score.toFixed(2)}` : "unverified",
              );
              setLastGrounding(grounding);
            },
            onMessageSaved: (payload) => {
              if (gen !== streamGenRef.current) return;
              appendEvent("message_saved");
              if (payload?.message_id) {
                updateMessageId(assistantId, payload.message_id);
              }
            },
            onDone: () => {
              if (gen !== streamGenRef.current) return;
              appendEvent("done");
              setLastLatencyMs(performance.now() - startedAt);
            },
            onError: (payload) => {
              if (gen !== streamGenRef.current) return;
              appendEvent("server_error", payload.code);
              streamError = new Error(payload.error || "Chat failed");
            },
          },
          controller.signal,
          settings.topK,
          settings.similarityThreshold,
          activeDocumentIds,
          {
            workspaceId: activeWorkspaceId ?? undefined,
            mode: chatMode,
            sourceIds:
              selectedSourceIds && selectedSourceIds.length
                ? selectedSourceIds
                : undefined,
          },
        );
        if (streamError) throw streamError;
        streamClean = true;
      } catch (err) {
        const aborted = err instanceof DOMException && err.name === "AbortError";
        if (!aborted && gen === streamGenRef.current) {
          setError(err instanceof Error ? err.message : "Request failed.");
          const failedDocumentId = activeDocumentId;
          const failedConversationId = startConversationId;
          setErrorRetry({
            run: () => void sendPromptRef.current?.(prompt, { replaceFailedTurn: true }),
            // A failed new chat has no conversation yet; otherwise it must match.
            stillValid: () =>
              activeDocumentIdRef.current === failedDocumentId &&
              (failedConversationId === null || activeConversationIdRef.current === failedConversationId),
          });
        }
      } finally {
        if (streamGenRef.current === gen) {
          streamingRef.current = false;
          setStreaming(false);
          if (abortRef.current === controller) {
            abortRef.current = null;
          }
        }
      }

      // [FIX 5.1] The conversation refresh moved out of the stream's
      // try/catch so a late refresh failure can no longer nuke the turn —
      // it is logged and the answer stays on screen.
      if (streamClean && activeConversation) {
        try {
          await refreshConversations(activeDocumentId);
        } catch (refreshError) {
          console.error("refresh_conversations_failed", refreshError);
        }
      }
    },
    [
      // activeConversationId is deliberately absent: the conversation id is read
      // from activeConversationIdRef so the retry thunk (which re-invokes this
      // closure) always sees the live value rather than a stale capture.
      activeDocumentId,
      activeDocumentIds,
      activeWorkspaceId,
      addMessage,
      appendToMessage,
      auth,
      chatMode,
      selectedSourceIds,
      dispatch,
      refreshConversations,
      setMessages,
      settings.chatModel,
      settings.provider,
      settings.topK,
      settings.similarityThreshold,
      updateMessageSources,
      updateMessageId,
    ]
  );

  const handleSubmit = useCallback(
    (event?: React.FormEvent) => {
      event?.preventDefault();
      if (!canAsk || !activeDocumentId) return;
      const prompt = question.trim();
      setQuestion("");
      void sendPrompt(prompt);
    },
    [canAsk, activeDocumentId, question, sendPrompt]
  );

  const handleRerun = useCallback(
    async (message: Message) => {
      if (message.id.startsWith("temp-")) return;
      if (
        streamingRef.current ||
        !activeDocumentId ||
        !activeConversationId ||
        !settings.providerApiKey.trim() ||
        !settings.chatModel.trim()
      ) {
        return;
      }
      streamingRef.current = true;
      setError(null);
      setErrorRetry(null);
      setCurrentSources([]);
      setStreaming(true);
      setRerunningMessageId(message.id);
      try {
        const response = await rerunMessage(
          auth,
          settings.provider,
          settings.chatModel,
          activeDocumentId,
          activeConversationId,
          message.id,
          settings.topK,
          settings.similarityThreshold
        );
        dispatch({ type: "SET_ACTIVE_CONVERSATION", payload: response.conversation_id });
        await refreshConversations(activeDocumentId);
        await selectConversation(response.conversation_id);
      } catch (rerunError) {
        setError(rerunError instanceof Error ? rerunError.message : "Unable to rerun message.");
        const failedDocumentId = activeDocumentId;
        const failedConversationId = activeConversationId;
        setErrorRetry({
          run: () => void handleRerunRef.current?.(message),
          stillValid: () =>
            activeDocumentIdRef.current === failedDocumentId &&
            activeConversationIdRef.current === failedConversationId,
        });
      } finally {
        streamingRef.current = false;
        setStreaming(false);
        setRerunningMessageId(null);
      }
    },
    [
      activeConversationId,
      activeDocumentId,
      auth,
      dispatch,
      refreshConversations,
      selectConversation,
      settings.chatModel,
      settings.provider,
      settings.providerApiKey,
      settings.topK,
      settings.similarityThreshold,
    ]
  );

  const handleRetryDocument = useCallback(async () => {
    if (!activeDocumentId || !settings.providerApiKey.trim()) return;
    try {
      setError(null);
      setErrorRetry(null);
      await reprocessDocument(auth, activeDocumentId, settings.embeddingModel);
    } catch (retryError) {
      setError(retryError instanceof Error ? retryError.message : "Unable to retry indexing.");
      const failedDocumentId = activeDocumentId;
      setErrorRetry({
        run: () => void handleRetryDocumentRef.current?.(),
        stillValid: () => activeDocumentIdRef.current === failedDocumentId,
      });
    }
  }, [activeDocumentId, auth, settings.providerApiKey, settings.embeddingModel]);

  useLayoutEffect(() => {
    sendPromptRef.current = sendPrompt;
    handleRerunRef.current = handleRerun;
    handleRetryDocumentRef.current = handleRetryDocument;
  }, [sendPrompt, handleRerun, handleRetryDocument]);

  const stopStreaming = useCallback(() => {
    streamGenRef.current += 1;
    abortRef.current?.abort();
    abortRef.current = null;
    streamingRef.current = false;
    setStreaming(false);
  }, []);

  useEffect(() => {
    if (!streaming) return;
    // stopStreaming() aborts the in-flight fetch (an external system) and must
    // clear `streaming` in the same pass so the composer re-enables. The
    // triggers (conversation switched, messages cleared) originate in the
    // shared server-state provider, not in an event handler here, so this
    // cannot move into a handler, and deriving `streaming` would leave the
    // abort undone.
    if (messages.length === 0) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- aborts an external request; see above
      stopStreaming();
      return;
    }
    if (activeConversationId !== streamConversationRef.current) {
      stopStreaming();
    }
  }, [activeConversationId, messages.length, streaming, stopStreaming]);

  const renderEmptyState = () => {
    const hasProvider = Boolean(settings.providerApiKey.trim());

    if (!activeDocument) return <DocumentLibrary onUploadClick={onUploadClick} />;

    if (!hasProvider) {
      return (
        <EmptyState
          icon={<KeyRound size={20} />}
          title="Connect a model"
          description="Add an OpenAI or Gemini API key in Settings to ask questions about this document."
          action={<Button variant="primary" onClick={() => dispatch({ type: "SET_SETTINGS_OPEN", payload: true })}>Connect provider</Button>}
        />
      );
    }

    if (activeDocument.status !== "ready") {
      const failed = activeDocument.status === "error";
      return (
        <EmptyState
          icon={failed ? <AlertTriangle size={20} /> : <Loader2 size={20} className="animate-spin" />}
          title={failed ? "This document needs another try" : "Getting your document ready"}
          description={failed ? activeDocument.last_error || "We couldn’t prepare this document. Try processing it again." : "We’re reading your file and preparing it for questions. This can take a moment."}
          action={failed ? <Button variant="primary" onClick={handleRetryDocument}><RefreshCcw size={14} /> Try again</Button> : undefined}
        />
      );
    }

    return (
      <div className="mx-auto w-full max-w-[620px] py-10 sm:py-16">
        <p className="index-label mb-5" style={{ color: "var(--accent-primary)" }}>Document questions</p>
        <h1 className="editorial-heading text-[42px] leading-[1.05] sm:text-[50px]" style={{ color: "var(--text-primary)" }}>Ask this document.</h1>
        <p className="mt-4 max-w-[390px] text-sm leading-7" style={{ color: "var(--text-secondary)" }}>Start with a question. Each answer includes the source passages used to write it.</p>
        <div className="mt-10" style={{ borderTop: "1px solid var(--border)" }}>
          {suggestions.map((suggestion, i) => (
            <button
              key={suggestion}
              type="button"
              onClick={() => { setQuestion(suggestion); textareaRef.current?.focus(); }}
              className="focus-ring group flex w-full items-center gap-4 py-4 text-left text-[13px] transition-colors hover:bg-[var(--bg-surface-hover)]"
              style={{ borderBottom: "1px solid var(--border)", color: "var(--text-secondary)" }}
            >
              <span className="data-num pl-1 text-[10px]" style={{ color: "var(--text-muted)" }}>{String(i + 1).padStart(2, "0")}</span>
              <span className="flex-1">{suggestion}</span>
              <ArrowUp size={14} className="mr-2 rotate-45 opacity-40 transition-opacity group-hover:opacity-100" style={{ color: "var(--accent-primary)" }} />
            </button>
          ))}
        </div>
      </div>
    );
  };

  const layoutMaxWidth = !activeDocument
    ? "max-w-[1120px]"
    : chatLayout === "focus" ? "max-w-[780px]" : chatLayout === "research" ? "max-w-full" : "max-w-[800px]";

  const multiDocStatus = activeDocuments.some((d) => d.status === "error")
    ? ("error" as const)
    : activeDocuments.every((d) => d.status === "ready")
      ? ("success" as const)
      : ("processing" as const);
  const singleDocStatus =
    activeDocument?.status === "ready"
      ? ("success" as const)
      : activeDocument?.status === "error"
        ? ("error" as const)
        : ("processing" as const);

  return (
    <main className="flex h-full w-full min-w-0 flex-1">
      <div className="relative flex h-full min-w-0 flex-1 flex-col">
      <header
        className="relative z-20 flex shrink-0 items-center gap-3 px-4 sm:px-7"
        style={{ minHeight: "var(--header-height)", borderBottom: "1px solid var(--border)", background: "var(--bg-primary)" }}
      >
        <button
          type="button"
          onClick={() => dispatch({ type: "TOGGLE_SIDEBAR" })}
          className={`focus-ring flex h-9 w-9 shrink-0 items-center justify-center rounded-lg transition-colors hover:bg-[var(--bg-secondary)] ${sidebarOpen ? "md:hidden" : ""}`}
          style={{ color: "var(--text-tertiary)" }}
          aria-label="Toggle sidebar"
          title="Toggle sidebar"
        ><PanelLeftOpen size={19} /></button>
        <nav className="flex min-w-0 flex-1 items-center gap-2.5 text-xs" aria-label="Breadcrumb">
          {activeDocument || isMultiDoc ? (
            <>
              <button type="button" onClick={() => void selectDocument(null)} className="focus-ring shrink-0 rounded-sm px-1 py-2 transition-colors hover:text-[var(--text-primary)]" style={{ color: "var(--text-muted)" }}>Library</button>
              <span aria-hidden="true" style={{ color: "var(--text-faint)" }}>/</span>
              <span className="truncate font-medium" style={{ color: "var(--text-primary)" }} title={isMultiDoc ? undefined : activeDocument?.filename}>{isMultiDoc ? `${activeDocumentIds.length} documents` : activeDocument?.filename}</span>
              <StatusDot tone={isMultiDoc ? multiDocStatus : singleDocStatus} pulse={(isMultiDoc ? multiDocStatus : singleDocStatus) === "processing"} />
            </>
          ) : (
            <>
              <span className="hidden truncate sm:inline" style={{ color: "var(--text-muted)" }}>{state.workspaces.find((workspace) => workspace.id === activeWorkspaceId)?.name ?? "Workspace"}</span>
              <span className="hidden sm:inline" aria-hidden="true" style={{ color: "var(--text-faint)" }}>/</span>
              <span style={{ color: "var(--text-primary)" }}>Library</span>
            </>
          )}
        </nav>
        {activeDocument && !isMultiDoc ? (
          <button type="button" onClick={() => router.push(`/documents/${activeDocument.id}/notebook`)} className="focus-ring flex items-center gap-2 rounded-lg px-2.5 py-2 text-xs transition-colors hover:bg-[var(--bg-secondary)]" style={{ color: "var(--text-secondary)" }} aria-label="Open notebook view" title="Open notebook view"><BookOpen size={16} /><span className="hidden sm:inline">Notebook</span></button>
        ) : null}
        {activeDocument || isMultiDoc ? (
          <details
            className="relative"
            onBlur={(event) => { if (!event.currentTarget.contains(event.relatedTarget)) event.currentTarget.open = false; }}
            onKeyDown={(event) => { if (event.key === "Escape") { event.currentTarget.open = false; event.currentTarget.querySelector("summary")?.focus(); } }}
          >
            <summary aria-label="View options" title="View options" className="focus-ring flex cursor-pointer list-none items-center gap-2 rounded-lg px-2.5 py-2 text-xs transition-colors hover:bg-[var(--bg-secondary)] [&::-webkit-details-marker]:hidden" style={{ color: "var(--text-secondary)" }}><SlidersHorizontal size={16} /><span className="hidden sm:inline">View</span><ChevronDown size={12} /></summary>
            <div className="absolute right-0 top-full z-30 mt-2 w-[264px] rounded-lg p-3" style={{ background: "var(--bg-surface)", border: "1px solid var(--border)", boxShadow: "var(--shadow-lg)" }}>
              <p className="px-1 pb-2 text-xs font-medium" style={{ color: "var(--text-secondary)" }}>Workspace view</p>
              <div className="grid grid-cols-3 gap-1 rounded-lg p-1" style={{ background: "var(--bg-secondary)" }} role="group" aria-label="Chat layout mode">
                {(["default", "focus", "research"] as const).map((mode) => {
                  const icons = { default: <Monitor size={15} />, focus: <Focus size={15} />, research: <LayoutPanelLeft size={15} /> };
                  const titles = { default: "Default", focus: "Focus", research: "Research" };
                  const active = chatLayout === mode;
                  return <button key={mode} type="button" aria-pressed={active} aria-label={`${titles[mode]} layout`} className="focus-ring flex flex-col items-center gap-1.5 rounded-md px-1 py-2.5 text-[11px] transition-colors" style={{ color: active ? "var(--text-primary)" : "var(--text-muted)", background: active ? "var(--bg-surface)" : "transparent", boxShadow: active ? "var(--shadow-xs)" : "none" }} onClick={() => { dispatch({ type: "SET_SETTINGS", payload: { chatLayout: mode } }); dispatch({ type: "SET_SIDEBAR", payload: mode !== "focus" }); setSourcePanelOpen(mode !== "focus"); }}>{icons[mode]}{titles[mode]}</button>;
                })}
              </div>
              <div className="mt-3 flex flex-col gap-1 pt-2" style={{ borderTop: "1px solid var(--border)" }}>
                <button type="button" onClick={() => setAnalyticsOpen((v) => !v)} aria-pressed={analyticsOpen} aria-label="Toggle trust analytics panel" className="focus-ring flex items-center gap-2.5 rounded-lg px-2 py-2.5 text-xs hover:bg-[var(--bg-secondary)]" style={{ color: analyticsOpen ? "var(--accent-primary)" : "var(--text-secondary)" }}><BarChart3 size={15} />Answer insights{analyticsOpen ? <span className="ml-auto">On</span> : null}</button>
                <button type="button" onClick={() => setDebugOpen((v) => !v)} aria-pressed={debugOpen} aria-label="Toggle retrieval debug panel" className="focus-ring flex items-center gap-2.5 rounded-lg px-2 py-2.5 text-xs hover:bg-[var(--bg-secondary)]" style={{ color: debugOpen ? "var(--accent-primary)" : "var(--text-secondary)" }}><Bug size={15} />Retrieval details{debugOpen ? <span className="ml-auto">On</span> : null}</button>
              </div>
            </div>
          </details>
        ) : null}
        {activeDocument ? (
          <>
            <button ref={desktopSourceToggleRef} type="button" className="focus-ring hidden items-center gap-1.5 rounded-md border px-2.5 py-1.5 text-xs transition-colors xl:inline-flex" style={{ color: sourcePanelOpen ? "var(--text-primary)" : "var(--text-secondary)", borderColor: "var(--border)", background: sourcePanelOpen ? "var(--bg-secondary)" : "transparent" }} onClick={() => setSourcePanelOpen((open) => !open)} aria-expanded={sourcePanelOpen} aria-label="Toggle sources panel"><PanelRight size={15} /><span>Sources</span></button>
            <button type="button" className="focus-ring inline-flex items-center gap-1.5 rounded-md border px-2 py-1.5 text-xs xl:hidden" style={{ color: "var(--text-secondary)", borderColor: "var(--border)" }} onClick={() => setMobileSourcesOpen(true)} aria-expanded={mobileSourcesOpen} aria-label="Open sources"><PanelRight size={15} /><span className="hidden sm:inline">Sources</span></button>
          </>
        ) : null}
        {activeDocument?.status === "error" ? <button type="button" onClick={handleRetryDocument} className="focus-ring flex h-9 w-9 items-center justify-center rounded-lg hover:bg-[var(--bg-secondary)]" style={{ color: "var(--text-tertiary)" }} aria-label="Retry processing document" title="Retry processing document"><RefreshCcw size={16} /></button> : null}
      </header>

      <TrustAnalyticsPanel
        open={analyticsOpen}
        onClose={() => setAnalyticsOpen(false)}
        messages={messages}
        latencyMs={lastLatencyMs}
      />
      <RetrievalDebugPanel
        open={debugOpen}
        stages={lastStages}
        latencyMs={lastLatencyMs}
        sources={currentSources}
        topK={settings.topK}
        grounding={lastGrounding}
        streamEvents={streamEvents}
      />

      {/* Messages area — scroll container with stick-to-bottom tracking */}
      <div className="flex-1 relative min-h-0">
        <div
          ref={scrollContainerRef}
          className={`absolute inset-0 overflow-y-auto py-7 sm:py-10 ${chatLayout === "focus" ? "px-6" : "px-4 sm:px-8"}`}
          style={{ background: "var(--bg-primary)" }}
        >
          <div className={`${layoutMaxWidth} mx-auto flex flex-col gap-6`}>
            {messagesError ? (
              <div className="px-4 py-6">
                <ErrorBanner
                  message={`Couldn't load this conversation: ${messagesError}`}
                  onRetry={activeConversationId ? () => void selectConversation(activeConversationId) : undefined}
                />
              </div>
            ) : messages.length === 0 && messagesLoading ? (
              <>
                <MessageSkeleton />
                <MessageSkeleton />
              </>
            ) : messages.length === 0 ? (
              renderEmptyState()
            ) : (
              <>
                {messages.map((message, idx) => (
                  <React.Fragment key={message.id}>
                    <motion.div
                      initial={{ opacity: 0, y: 8 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ duration: 0.25, delay: idx * 0.02, ease: EASE_OUT }}
                    >
                      <MessageBubble
                        message={message}
                        onCitationSelect={message.sources?.length ? (citation) => inspectSources(message.sources!, citation) : undefined}
                        onRerun={
                          // [FIX 5.6] no rerun on unreconciled temp ids or without a durable conversation
                          message.role === "user" &&
                          activeConversationId &&
                          !message.id.startsWith("temp-")
                            ? handleRerun
                            : undefined
                        }
                        rerunDisabled={streaming || rerunningMessageId === message.id}
                        isStreaming={
                          streaming &&
                          message.role === "assistant" &&
                          idx === messages.length - 1
                        }
                        onFeedback={
                          message.role === "assistant" &&
                          activeConversationId &&
                          !message.id.startsWith("temp-")
                            ? handleFeedback
                            : undefined
                        }
                        feedbackState={feedbackState[message.id] ?? "idle"}
                      />
                    </motion.div>
                    {message.role === "assistant" ? (
                      <div className="flex flex-wrap items-center gap-4">
                        {message.sources?.length ? (
                          <button type="button" onClick={() => inspectSources(message.sources!)} className="focus-ring inline-flex items-center gap-1.5 rounded-sm px-1 py-1 text-[11px] transition-colors hover:underline underline-offset-4" style={{ color: "var(--accent-primary)" }} aria-label={`Inspect ${message.sources.length} source passages`}><PanelRight size={13} />{message.sources.length} references<span aria-hidden="true">↗</span></button>
                        ) : null}
                        {message.id && !message.id.startsWith("temp-") && activeWorkspaceId && canEdit ? (
                          <button type="button" onClick={() => handleSaveToWorkspace(message)} disabled={savingMessageId === message.id} className="focus-ring rounded-sm px-1 py-1 text-[11px] transition-colors hover:underline underline-offset-4" style={{ color: "var(--text-tertiary)", opacity: savingMessageId === message.id ? 0.6 : 1 }} title="Save this answer to workspace notes">{savingMessageId === message.id ? "Saving…" : "Save answer"}</button>
                        ) : null}
                      </div>
                    ) : null}
                  </React.Fragment>
                ))}
                {!streaming && lastHint ? (
                  <ActiveLearningHintBanner hint={lastHint} />
                ) : null}
                {messagesLoading ? (
                  <div className="flex items-center gap-2 pl-11" style={{ color: "var(--text-muted)" }}>
                    <Loader2 size={12} className="animate-spin" />
                    <span className="text-xs">Loading conversation…</span>
                  </div>
                ) : null}
              </>
            )}
            <div ref={endRef} />
          </div>
        </div>

        {/* [FIX 5.7] Jump-to-latest affordance while detached from the bottom */}
        <AnimatePresence>
          {!isSticky && messages.length > 0 ? (
            <div className="absolute bottom-4 inset-x-0 z-20 flex justify-center pointer-events-none">
              <motion.button
                type="button"
                onClick={jumpToLatest}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={transitionFast}
                className="pointer-events-auto flex items-center gap-1.5 px-2.5 py-1.5 rounded-full text-[11px] font-medium transition-colors focus-ring"
                style={{
                  background: "var(--bg-elevated)",
                  border: "1px solid var(--border-hover)",
                  color: "var(--text-secondary)",
                  boxShadow: "var(--shadow-md)",
                }}
                aria-label="Jump to latest message"
                title="Jump to latest message"
              >
                <ArrowDown size={12} />
                Jump to latest
              </motion.button>
            </div>
          ) : null}
        </AnimatePresence>
      </div>

      {/* Error bar */}
      <AnimatePresence>
        {error ? (
          <motion.div
            className="px-4 pb-2"
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 4 }}
            transition={transitionFast}
          >
            <ErrorBanner
              message={error}
              onRetry={
                errorRetry
                  ? () => {
                      if (!errorRetry.stillValid()) {
                        setErrorRetry(null);
                        return;
                      }
                      errorRetry.run();
                    }
                  : undefined
              }
              onDismiss={() => {
                setError(null);
                setErrorRetry(null);
              }}
            />
          </motion.div>
        ) : null}
      </AnimatePresence>

      {/* Input area */}
      {activeDocument?.status === "ready" ? (
        <div className="flex-shrink-0 px-4 pb-5 pt-3 sm:px-8" style={{ background: "var(--bg-primary)" }}>
          <form onSubmit={handleSubmit} className={`${layoutMaxWidth} mx-auto relative`}>
            <div className="mb-2.5 flex flex-wrap items-center gap-3">
              <label className="flex items-center gap-1 text-xs" style={{ color: "var(--text-secondary)" }}>
                <span className="sr-only">Answer style</span>
                <select aria-label="Answer style" value={chatMode} onChange={(event) => setChatMode(event.target.value as ChatMode)} className="focus-ring cursor-pointer rounded-md px-2 py-1.5 text-xs outline-none" style={{ background: "transparent", color: "var(--text-secondary)", border: "1px solid var(--border)" }}>
                  <option value="ask">Ask a question</option>
                  <option value="compare">Compare sources</option>
                  <option value="extract">Extract details</option>
                  <option value="brief">Create a brief</option>
                </select>
              </label>

              {/* Per-source filter (Phase 1). Hidden when not inside a workspace
                  or when the workspace has fewer than 2 ready sources. */}
              {activeWorkspaceId && workspaceSourcesError ? (
                <span
                  className="ml-1 text-[10px] px-2 py-1 rounded-md"
                  style={{ color: "var(--error)", border: "1px solid var(--error-soft)" }}
                  role="alert"
                  title={workspaceSourcesError}
                >
                  source filter unavailable
                </span>
              ) : activeWorkspaceId && workspaceSources.length >= 2 ? (
                <div
                  className="ml-1 relative"
                  onBlur={(event) => {
                    if (!event.currentTarget.contains(event.relatedTarget)) setSourceFilterOpen(false);
                  }}
                  onKeyDown={(event) => {
                    if (event.key === "Escape" && sourceFilterOpen) {
                      event.stopPropagation();
                      setSourceFilterOpen(false);
                      sourceFilterTriggerRef.current?.focus();
                    }
                  }}
                >
                  <button
                    ref={sourceFilterTriggerRef}
                    type="button"
                    onClick={() => setSourceFilterOpen((v) => !v)}
                    aria-controls={sourceFilterId}
                    aria-expanded={sourceFilterOpen}
                    className="text-xs font-medium px-2.5 py-1.5 rounded-lg transition-colors flex items-center gap-1"
                    style={{
                      background: selectedSourceIds ? "var(--accent-primary-soft)" : "transparent",
                      color: selectedSourceIds ? "var(--accent-primary)" : "var(--text-muted)",
                      border: "1px solid var(--border)",
                    }}
                    title="Restrict retrieval to selected workspace sources"
                  >
                    Sources:{" "}
                    <span className="data-num">
                      {selectedSourceIds ? selectedSourceIds.length : "all"}
                    </span>
                  </button>
                  {sourceFilterOpen ? (
                    <div
                      className="absolute bottom-full mb-1 left-0 z-30 w-72 rounded-lg overflow-hidden"
                      style={{
                        background: "var(--bg-elevated)",
                        border: "1px solid var(--border)",
                        boxShadow: "var(--shadow-md)",
                      }}
                      id={sourceFilterId}
                      role="group"
                      aria-label="Filter workspace sources"
                    >
                      <div
                        className="flex items-center justify-between px-3 py-2"
                        style={{ borderBottom: "1px solid var(--border)" }}
                      >
                        <span
                          className="text-[10px] uppercase tracking-widest"
                          style={{ color: "var(--text-muted)" }}
                        >
                          Filter sources
                        </span>
                        <button
                          type="button"
                          onClick={() => {
                            setSelectedSourceIds(null);
                            setSourceFilterOpen(false);
                            sourceFilterTriggerRef.current?.focus();
                          }}
                          aria-label="Reset to all sources"
                          className="text-[10px] font-medium focus-ring rounded px-1"
                          style={{ color: "var(--accent-primary)" }}
                        >
                          Reset to all
                        </button>
                      </div>
                      <ul className="max-h-64 overflow-y-auto">
                        {workspaceSources.map((src) => {
                          const checked = selectedSourceIds
                            ? selectedSourceIds.includes(src.id)
                            : false;
                          const isReady = src.status === "ready";
                          return (
                            <li key={src.id}>
                              <label
                                className="w-full flex items-center gap-2 px-3 py-2 text-xs cursor-pointer transition-colors hover:bg-[var(--bg-surface)]"
                                style={{
                                  color: isReady
                                    ? "var(--text-primary)"
                                    : "var(--text-muted)",
                                  opacity: isReady ? 1 : 0.6,
                                }}
                              >
                                <input
                                  type="checkbox"
                                  checked={checked}
                                  disabled={!isReady}
                                  style={{ accentColor: "var(--accent-primary)" }}
                                  onChange={(e) => {
                                    setSelectedSourceIds((prev) => {
                                      const base = prev ?? [];
                                      if (e.target.checked) {
                                        return [...new Set([...base, src.id])];
                                      }
                                      const next = base.filter((id) => id !== src.id);
                                      // If unchecking the last one, fall back to
                                      // "all sources" so the user can't accidentally
                                      // submit an empty filter.
                                      return next.length === 0 ? null : next;
                                    });
                                  }}
                                />
                                <span className="flex-1 truncate">
                                  {src.source_title}
                                </span>
                                <span
                                  className="text-[10px] uppercase tracking-widest"
                                  style={{ color: "var(--text-muted)" }}
                                >
                                  {src.source_type}
                                </span>
                              </label>
                            </li>
                          );
                        })}
                      </ul>
                    </div>
                  ) : null}
                </div>
              ) : null}
            </div>
            <div
              className="flex items-end overflow-hidden rounded-lg border border-[var(--border-hover)] bg-[var(--bg-surface)] transition-[border-color,box-shadow,opacity] duration-150 focus-within:border-[var(--accent-primary)] focus-within:shadow-[0_0_0_3px_var(--accent-soft)]"
              style={{ opacity: streaming ? 0.7 : 1 }}
            >
              <textarea
                ref={textareaRef}
                value={question}
                onChange={(event) => setQuestion(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" && !event.shiftKey) {
                    event.preventDefault();
                    void handleSubmit();
                  }
                }}
                placeholder={
                  streaming
                    ? "Writing an answer…"
                    : settings.providerApiKey.trim()
                    ? "Ask your sources…"
                    : "Connect a provider first"
                }
                disabled={!settings.providerApiKey.trim() || streaming}
                rows={1}
                aria-label="Ask a question about your document"
                className="min-w-0 flex-1 resize-none rounded-lg bg-transparent px-4 py-3.5 text-sm outline-none disabled:cursor-not-allowed"
                style={{ color: "var(--text-primary)", maxHeight: 160, minHeight: 52 }}
              />
              <div className="flex items-center gap-1.5 p-2.5">
                {streaming ? (
                  <motion.button
                    type="button"
                    onClick={stopStreaming}
                    className="flex items-center justify-center rounded-md transition-colors focus-ring"
                    style={{
                      width: 32,
                      height: 32,
                      background: "var(--error-soft)",
                      color: "var(--error)",
                      border: "1px solid var(--error-soft)",
                    }}
                    aria-label="Stop generating response"
                    title="Stop generating response"
                    whileHover={{ filter: "brightness(1.15)" }}
                    whileTap={{ scale: 0.9 }}
                  >
                    <StopCircle size={16} />
                  </motion.button>
                ) : null}
                <motion.button
                  type="submit"
                  disabled={!canAsk}
                  className="flex items-center justify-center rounded-md transition-colors focus-ring disabled:cursor-not-allowed"
                  style={{
                    width: 32,
                    height: 32,
                    background: canAsk ? "var(--accent)" : "transparent",
                    color: canAsk ? "var(--accent-fg)" : "var(--text-muted)",
                    border: canAsk ? "1px solid transparent" : "1px solid var(--border)",
                  }}
                  aria-label="Send message"
                  title={
                    canAsk
                      ? "Send message"
                      : streaming
                        ? "Wait for response to finish"
                        : !activeDocumentId
                          ? "Select a document to chat"
                          : !settings.providerApiKey.trim()
                            ? "API key required"
                            : !question.trim()
                              ? "Enter a question to send"
                              : "Send message"
                  }
                  whileHover={canAsk ? { background: "var(--accent-hover)" } : {}}
                  whileTap={canAsk ? { scale: 0.92 } : {}}
                >
                  {streaming ? <Loader2 size={15} className="animate-spin" /> : <ArrowUp size={15} />}
                </motion.button>
              </div>
            </div>
            <div className="mt-3 flex items-center justify-between gap-3 px-1 text-[11px]" style={{ color: "var(--text-muted)" }}>
              <span>Check important details against the sources.</span>
              <span className="hidden shrink-0 sm:inline">↵ Send · ⇧ ↵ New line</span>
            </div>
          </form>
        </div>
      ) : null}
      </div>
      {activeDocument ? (
        <SourceInspector
          open={sourcePanelOpen}
          mobileOpen={mobileSourcesOpen}
          sources={visibleSources}
          documents={documents}
          document={activeDocument}
          selectedChunkId={selectedChunkId}
          onClose={closeSources}
          onSelect={(citation) => setSelectedChunkId(citation.chunk_id)}
          onOpenDocument={(documentId, pageNumber) => router.push(`/documents/${encodeURIComponent(documentId)}/notebook${pageNumber ? `?page=${pageNumber}` : ""}`)}
          streaming={streaming}
        />
      ) : null}
    </main>
  );
}

function RetrievalDebugPanel({
  open,
  stages,
  latencyMs,
  sources,
  topK,
  grounding,
  streamEvents,
}: {
  open: boolean;
  stages: RetrievalStages | null;
  latencyMs: number | null;
  sources: Citation[];
  topK: number;
  grounding: GroundingSummary | null;
  streamEvents: Array<{ at: number; label: string; detail?: string }>;
}) {
  const [sourcesExpanded, setSourcesExpanded] = useState(true);
  const [eventsExpanded, setEventsExpanded] = useState(false);
  return (
    <AnimatePresence initial={false}>
      {open ? (
        <motion.div
          initial={{ height: 0, opacity: 0 }}
          animate={{ height: "auto", opacity: 1 }}
          exit={{ height: 0, opacity: 0 }}
          transition={{ duration: 0.2, ease: EASE_OUT }}
          className="panel-grid"
          style={{
            borderBottom: "1px solid var(--border)",
            background: "var(--bg-secondary)",
            overflow: "hidden",
          }}
          aria-label="Retrieval debug panel"
        >
          <div className="px-4 py-3 max-w-3xl mx-auto flex flex-col gap-3">
            <div className="flex items-center gap-2 flex-wrap">
              <span
                className="text-[10px] font-semibold uppercase tracking-widest"
                style={{ color: "var(--text-tertiary)" }}
              >
                Retrieval
              </span>
              <StageChip label="top_k" value={stages?.requested_top_k ?? topK} />
              <StageChip
                label="hybrid"
                value={stages?.hybrid_enabled === undefined ? "—" : stages.hybrid_enabled ? "on" : "off"}
                accent={stages?.hybrid_enabled}
              />
              <StageChip
                label="reranker"
                value={
                  stages?.reranker_enabled === undefined ? "—" : stages.reranker_enabled ? "on" : "off"
                }
                accent={stages?.reranker_enabled}
              />
              {stages?.dense_k !== undefined ? <StageChip label="dense_k" value={stages.dense_k} /> : null}
              {stages?.dense_hits !== undefined ? <StageChip label="dense" value={stages.dense_hits} /> : null}
              {stages?.fts_hits !== undefined ? <StageChip label="fts" value={stages.fts_hits} /> : null}
              {stages?.fused_hits !== undefined ? <StageChip label="fused" value={stages.fused_hits} /> : null}
              {stages?.rerank_reordered !== undefined ? (
                <StageChip label="reordered" value={stages.rerank_reordered} />
              ) : null}
              {stages?.final_hits !== undefined ? <StageChip label="final" value={stages.final_hits} /> : null}
              {stages?.mmr_enabled ? (
                <StageChip label="mmr" value="on" accent />
              ) : null}
              {Array.isArray(stages?.query_transforms) && (stages?.query_transforms as string[]).length ? (
                <StageChip
                  label="transforms"
                  value={(stages?.query_transforms as string[]).join("+")}
                  accent
                />
              ) : null}
              {grounding?.enabled ? (
                <StageChip
                  label="grounded"
                  value={
                    grounding.score !== null && grounding.score !== undefined
                      ? grounding.score.toFixed(2)
                      : grounding.verified === null
                      ? "—"
                      : grounding.verified
                      ? "yes"
                      : "no"
                  }
                  accent={grounding.verified === true}
                />
              ) : null}
              {latencyMs !== null ? (
                <StageChip label="total" value={`${latencyMs.toFixed(0)} ms`} accent />
              ) : null}
            </div>

            {streamEvents.length > 0 ? (
              <div>
                {/* [a11y] Added aria-expanded to communicate toggle state to assistive technology */}
                <button
                  type="button"
                  onClick={() => setEventsExpanded((v) => !v)}
                  aria-expanded={eventsExpanded}
                  className="flex items-center gap-1 text-[11px] font-medium outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] rounded-sm"
                  style={{ color: "var(--text-tertiary)" }}
                >
                  {eventsExpanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
                  Stream timeline (<span className="data-num">{streamEvents.length}</span> events)
                </button>
                {eventsExpanded ? (
                  <div className="mt-2 flex flex-col gap-1">
                    {streamEvents.map((ev, i) => (
                      <div
                        key={`${ev.label}-${i}`}
                        className="flex items-center gap-2 text-[11px]"
                      >
                        <span
                          className="data-num"
                          style={{ color: "var(--accent-secondary)", minWidth: 64 }}
                        >
                          {ev.at.toFixed(0)} ms
                        </span>
                        <span
                          className="data-num"
                          style={{ color: "var(--text-secondary)", minWidth: 120 }}
                        >
                          {ev.label}
                        </span>
                        {ev.detail ? (
                          <span style={{ color: "var(--text-tertiary)" }}>{ev.detail}</span>
                        ) : null}
                      </div>
                    ))}
                  </div>
                ) : null}
              </div>
            ) : null}

            {sources.length ? (
              <div>
                {/* [a11y] Added aria-expanded to communicate toggle state to assistive technology */}
                <button
                  type="button"
                  onClick={() => setSourcesExpanded((v) => !v)}
                  aria-expanded={sourcesExpanded}
                  className="flex items-center gap-1 text-[11px] font-medium outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] rounded-sm"
                  style={{ color: "var(--text-tertiary)" }}
                >
                  {sourcesExpanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
                  Top <span className="data-num">{sources.length}</span> chunks
                </button>
                {sourcesExpanded ? (
                  <div className="mt-2 flex flex-col gap-1.5">
                    {sources.map((source, index) => (
                      <div
                        key={source.chunk_id}
                        className="px-2.5 py-1.5 rounded-md text-[11px] flex gap-2 items-baseline"
                        style={{
                          background: "var(--bg-surface)",
                          border: "1px solid var(--border)",
                        }}
                      >
                        <span className="data-num" style={{ color: "var(--text-muted)" }}>
                          [{index + 1}]
                        </span>
                        <span
                          className="data-num"
                          style={{
                            color: "var(--accent-secondary)",
                            minWidth: 54,
                          }}
                        >
                          {source.score.toFixed(4)}
                        </span>
                        {source.page_number !== null && source.page_number !== undefined ? (
                          <span className="data-num" style={{ color: "var(--text-muted)" }}>
                            p{source.page_number}
                          </span>
                        ) : null}
                        <span
                          className="truncate flex-1"
                          style={{ color: "var(--text-secondary)" }}
                          title={source.excerpt}
                        >
                          {source.excerpt}
                        </span>
                      </div>
                    ))}
                  </div>
                ) : null}
              </div>
            ) : (
              <p className="text-[11px]" style={{ color: "var(--text-muted)" }}>
                Send a question to see retrieval stages and top chunks.
              </p>
            )}
          </div>
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}

/**
 * Instrument chip for retrieval-stage readouts: muted uppercase label with a
 * cyan mono data-num value — the data, not decoration, is the signal.
 */
function StageChip({
  label,
  value,
  accent,
}: {
  label: string;
  value: string | number | boolean;
  accent?: boolean;
}) {
  return (
    <span
      className="px-2 py-0.5 rounded-md text-[10px] flex items-baseline gap-1.5"
      style={{
        background: "var(--bg-surface)",
        color: "var(--text-secondary)",
        border: `1px solid ${accent ? "var(--border-hover)" : "var(--border)"}`,
      }}
    >
      <span
        className="uppercase tracking-widest"
        style={{ color: "var(--text-muted)", fontSize: 9 }}
      >
        {label}
      </span>
      <span className="data-num" style={{ color: "var(--accent-secondary)" }}>
        {String(value)}
      </span>
    </span>
  );
}

/**
 * Banner surfacing the Phase-3.9 ``active_learning_hint`` returned by
 * the backend when retrieval confidence is low or the planner
 * abstained. Rendered inline with the chat scroll so the suggestion
 * sits next to the answer it applies to rather than floating over
 * the input area.
 */
function ActiveLearningHintBanner({ hint }: { hint: ActiveLearningHint }) {
  const isExpand = hint.action === "expand_search";
  return (
    <motion.div
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2, ease: EASE_OUT }}
      className="mx-auto w-full rounded-lg px-3 py-2 text-xs flex items-start gap-2"
      style={{
        background: "var(--info-soft)",
        border: "1px solid var(--border)",
        color: "var(--info)",
      }}
      role="note"
      aria-label="Retrieval suggestion"
    >
      <Focus size={12} style={{ marginTop: 2, flexShrink: 0 }} />
      <div className="flex-1 leading-snug">
        <div style={{ fontWeight: 500, color: "var(--info)" }}>{hint.suggestion}</div>
        <div style={{ color: "var(--text-tertiary)" }}>
          {isExpand
            ? "Try adding another document to the conversation or rephrasing with more specific terms."
            : "The agent could not ground an answer in your documents — consider rephrasing or trying a different source."}
          {typeof hint.best_score === "number" ? (
            <>
              {" (best score: "}
              <span className="data-num">{hint.best_score.toFixed(2)}</span>
              {")"}
            </>
          ) : (
            ""
          )}
        </div>
      </div>
    </motion.div>
  );
}

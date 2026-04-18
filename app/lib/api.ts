export type Provider = "openai" | "gemini";

export interface ClientAuthContext {
  clientSessionId?: string;
  providerApiKey?: string;
}

export interface ApiError {
  error: string;
  code?: string;
  request_id?: string;
  details?: unknown;
}

export type JobStatus = "queued" | "processing" | "ready" | "error";

export interface JobLifecycle {
  status: JobStatus;
  stage: string;
  progress: number;
  attempt_count: number;
  max_attempts: number;
  next_retry_at?: string | null;
  terminal?: boolean;
}

export type StreamEvent = never;

export interface Citation {
  chunk_id: string;
  document_id: string;
  excerpt: string;
  score: number;
  page_number?: number | null;
}

export interface ChunkPreview {
  chunk_id: string;
  document_id: string;
  content: string;
  page_number?: number | null;
  chunk_index: number;
}

export interface DocumentInfo {
  id: string;
  filename: string;
  provider: Provider;
  embedding_model: string;
  mime_type: string;
  checksum: string;
  chunk_count: number;
  file_size: number;
  page_count?: number | null;
  status: JobStatus;
  current_job_id?: string | null;
  current_stage?: string | null;
  last_job_id?: string | null;
  created_at: string;
  processed_at?: string | null;
  last_error?: string | null;
}

export interface JobInfo {
  id: string;
  document_id: string;
  status: JobStatus;
  stage: string;
  progress: number;
  attempt_count: number;
  max_attempts: number;
  next_retry_at?: string | null;
  terminal?: boolean;
  error_message?: string | null;
  created_at: string;
  started_at?: string | null;
  finished_at?: string | null;
  updated_at: string;
}

export interface ConversationListItem {
  id: string;
  document_id: string;
  title: string;
  created_at: string;
  updated_at: string;
  message_count: number;
}

export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources?: Citation[] | null;
  created_at: string;
}

export interface AnalyticsProviderBreakdown {
  provider: string;
  documents: number;
  ready_documents: number;
}

export interface AnalyticsOverview {
  totals: {
    users: number;
    active_users_7d: number;
    documents: number;
    ready_documents: number;
    conversations: number;
    messages: number;
    chunks: number;
  };
  recent: {
    signups_7d: number;
    uploads_7d: number;
    questions_24h: number;
    sessions_24h: number;
  };
  provider_breakdown: AnalyticsProviderBreakdown[];
}

export interface Conversation {
  id: string;
  document_id: string;
  title: string;
  created_at: string;
  updated_at: string;
  messages: Message[];
}

export interface IngestResponse {
  document_id: string;
  job_id?: string | null;
  status: string;
  embedding_model: string;
  deduplicated?: boolean;
}

export interface DocumentStatus {
  status: JobStatus;
  chunk_count: number;
  current_job_id?: string | null;
  current_stage?: string | null;
  last_job_id?: string | null;
  last_error?: string | null;
}

export interface AuthUser {
  id: string;
  email: string;
  role: "admin" | "user";
  is_active: boolean;
  is_verified: boolean;
  created_at?: string | null;
  updated_at?: string | null;
  session_token?: string;
}

export interface UpdateUserPayload {
  role?: "admin" | "user";
  is_active?: boolean;
}

const apiBase = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "";

function url(path: string): string {
  return apiBase ? `${apiBase}${path}` : path;
}

function baseHeaders(
  auth: ClientAuthContext,
  options?: { includeJson?: boolean; includeProviderKey?: boolean }
): Record<string, string> {
  const headers: Record<string, string> = {};
  const storedAuthToken = getStoredAuthToken();
  if (storedAuthToken) {
    headers.Authorization = `Bearer ${storedAuthToken}`;
  }
  if (auth.clientSessionId?.trim()) {
    headers["X-Client-Session"] = auth.clientSessionId.trim();
  }
  if (options?.includeJson) {
    headers["Content-Type"] = "application/json";
  }
  if (options?.includeProviderKey && auth.providerApiKey?.trim()) {
    headers["X-Provider-Api-Key"] = auth.providerApiKey.trim();
  }
  return headers;
}

function getStoredAuthToken(): string {
  if (typeof window === "undefined") return "";
  try {
    const rawSecrets = sessionStorage.getItem("rag-session");
    if (!rawSecrets) return "";
    const parsed = JSON.parse(rawSecrets) as { authToken?: string };
    return parsed.authToken?.trim() ?? "";
  } catch {
    return "";
  }
}

function updateStoredSession(partial: { authToken?: string | null }): void {
  if (typeof window === "undefined") return;
  try {
    const rawSecrets = sessionStorage.getItem("rag-session");
    const parsed = rawSecrets ? (JSON.parse(rawSecrets) as Record<string, unknown>) : {};
    const next = { ...parsed };
    if (partial.authToken === null || partial.authToken === undefined || !partial.authToken) {
      delete next.authToken;
    } else {
      next.authToken = partial.authToken;
    }
    sessionStorage.setItem("rag-session", JSON.stringify(next));
  } catch {
    // Ignore storage persistence errors.
  }
}

async function apiFetch(path: string, init?: RequestInit): Promise<Response> {
  return fetch(url(path), {
    credentials: "include",
    ...init,
  });
}

export async function listDocuments(auth: ClientAuthContext): Promise<DocumentInfo[]> {
  const res = await apiFetch("/api/documents", { headers: baseHeaders(auth) });
  if (!res.ok) throw new Error(await errorMessage(res));
  const data = (await res.json()) as { documents?: DocumentInfo[] };
  return data.documents ?? [];
}

export async function getDocumentStatus(
  auth: ClientAuthContext,
  documentId: string
): Promise<DocumentStatus> {
  const res = await apiFetch(`/api/documents/${documentId}/status`, {
    headers: baseHeaders(auth),
  });
  if (!res.ok) throw new Error(await errorMessage(res));
  return res.json();
}

export async function getDocumentChunks(
  auth: ClientAuthContext,
  documentId: string
): Promise<ChunkPreview[]> {
  const res = await apiFetch(`/api/documents/${documentId}/chunks`, {
    headers: baseHeaders(auth),
  });
  if (!res.ok) throw new Error(await errorMessage(res));
  return res.json();
}

export async function deleteDocument(
  auth: ClientAuthContext,
  documentId: string
): Promise<void> {
  const res = await apiFetch(`/api/documents/${documentId}`, {
    method: "DELETE",
    headers: baseHeaders(auth),
  });
  if (!res.ok) throw new Error(await errorMessage(res));
}

export async function ingestDocument(
  auth: ClientAuthContext,
  provider: Provider,
  file: File,
  embeddingModel: string
): Promise<IngestResponse> {
  const formData = new FormData();
  formData.append("provider", provider);
  formData.append("embedding_model", embeddingModel);
  formData.append("file", file);

  const res = await apiFetch("/api/ingest", {
    method: "POST",
    headers: baseHeaders(auth, { includeProviderKey: true }),
    body: formData,
  });
  if (!res.ok) throw new Error(await errorMessage(res));
  return res.json();
}

export async function reprocessDocument(
  auth: ClientAuthContext,
  documentId: string,
  embeddingModel?: string
): Promise<IngestResponse> {
  const endpoint = embeddingModel?.trim()
    ? `/api/documents/${documentId}/reprocess?embedding_model=${encodeURIComponent(
        embeddingModel.trim()
      )}`
    : `/api/documents/${documentId}/reprocess`;
  const res = await apiFetch(endpoint, {
    method: "POST",
    headers: baseHeaders(auth, { includeProviderKey: true }),
  });
  if (!res.ok) throw new Error(await errorMessage(res));
  return res.json();
}

export async function getJob(
  auth: ClientAuthContext,
  jobId: string
): Promise<JobInfo> {
  const res = await apiFetch(`/api/jobs/${jobId}`, {
    headers: baseHeaders(auth),
  });
  if (!res.ok) throw new Error(await errorMessage(res));
  return res.json();
}

export async function listConversations(
  auth: ClientAuthContext,
  documentId?: string
): Promise<ConversationListItem[]> {
  const query = documentId ? `?document_id=${encodeURIComponent(documentId)}` : "";
  const res = await apiFetch(`/api/conversations${query}`, {
    headers: baseHeaders(auth),
  });
  if (!res.ok) throw new Error(await errorMessage(res));
  const data = (await res.json()) as { conversations?: ConversationListItem[] };
  return data.conversations ?? [];
}

export async function getConversation(
  auth: ClientAuthContext,
  conversationId: string
): Promise<Conversation> {
  const res = await apiFetch(`/api/conversations/${conversationId}`, {
    headers: baseHeaders(auth),
  });
  if (!res.ok) throw new Error(await errorMessage(res));
  return res.json();
}

export async function renameConversation(
  auth: ClientAuthContext,
  conversationId: string,
  title: string
): Promise<void> {
  const res = await apiFetch(`/api/conversations/${conversationId}`, {
    method: "PATCH",
    headers: baseHeaders(auth, { includeJson: true }),
    body: JSON.stringify({ title }),
  });
  if (!res.ok) throw new Error(await errorMessage(res));
}

export async function exportConversation(
  auth: ClientAuthContext,
  conversationId: string,
  format: "markdown" | "json"
): Promise<Blob> {
  const res = await apiFetch(
    `/api/conversations/${conversationId}/export?format=${format}`,
    { headers: baseHeaders(auth) }
  );
  if (!res.ok) throw new Error(await errorMessage(res));
  return res.blob();
}

export async function deleteConversation(
  auth: ClientAuthContext,
  conversationId: string
): Promise<void> {
  const res = await apiFetch(`/api/conversations/${conversationId}`, {
    method: "DELETE",
    headers: baseHeaders(auth),
  });
  if (!res.ok) throw new Error(await errorMessage(res));
}

export interface RetrievalStages {
  hybrid_enabled?: boolean;
  reranker_enabled?: boolean;
  dense_k?: number;
  requested_top_k?: number;
  dense_hits?: number;
  fts_hits?: number;
  fused_hits?: number;
  rerank_reordered?: number;
  final_hits?: number;
  [key: string]: unknown;
}

export interface ChatResponse {
  conversation_id: string;
  message_id: string;
  sources: Citation[];
  content: string;
  stages?: RetrievalStages;
}

/**
 * Send a chat query to the server with optional retrieval controls and conversation context.
 *
 * @param provider - The LLM provider to use ("openai" | "gemini")
 * @param model - The provider model identifier (leading/trailing whitespace is trimmed)
 * @param documentId - Primary document id to scope retrievals
 * @param question - The user's question (leading/trailing whitespace is trimmed)
 * @param conversationId - Conversation id to append the message to, or `null` to start a new conversation
 * @param topK - Maximum number of retrieved passages to include for grounding
 * @param similarityThreshold - Minimum similarity score (typically 0–1) required for retrieved passages
 * @param documentIds - Optional explicit list of document ids to restrict retrieval; sent to the API only when the array contains more than one id
 * @returns The chat response object (`ChatResponse`)
 */
export async function sendChat(
  auth: ClientAuthContext,
  provider: Provider,
  model: string,
  documentId: string,
  question: string,
  conversationId: string | null,
  signal?: AbortSignal,
  topK?: number,
  similarityThreshold?: number,
  documentIds?: string[]
): Promise<ChatResponse> {
  const res = await apiFetch("/api/chat", {
    method: "POST",
    headers: baseHeaders(auth, { includeJson: true, includeProviderKey: true }),
    body: JSON.stringify({
      provider,
      model: model.trim(),
      document_id: documentId,
      document_ids: documentIds && documentIds.length > 1 ? documentIds : undefined,
      question: question.trim(),
      conversation_id: conversationId,
      top_k: topK,
      similarity_threshold: similarityThreshold,
    }),
    signal,
  });

  if (!res.ok) {
    throw new Error(await errorMessage(res));
  }

  return res.json();
}

// ---- SSE streaming chat ------------------------------------------------

export interface ChatStreamEvent {
  type: "sources" | "token" | "message_saved" | "done" | "grounding" | "error";
  data: unknown;
}

export interface GroundingSummary {
  enabled: boolean;
  verified: boolean | null;
  score: number | null;
  sentences?: Array<{ text: string; citations: number[]; supported: boolean }>;
}

export interface SendChatStreamCallbacks {
  onSources?: (payload: { conversation_id: string; sources: Citation[]; stages?: RetrievalStages }) => void;
  onToken?: (delta: string) => void;
  onMessageSaved?: (payload: { conversation_id: string; message_id: string }) => void;
  onDone?: (payload: { content: string }) => void;
  onGrounding?: (payload: GroundingSummary) => void;
  onError?: (payload: { error: string; code?: string }) => void;
}

/** Parse one SSE frame into {event, data}. Returns null on malformed input. */
function parseSseFrame(frame: string): { event: string; data: string } | null {
  let event = "message";
  const dataLines: string[] = [];
  for (const rawLine of frame.split("\n")) {
    const line = rawLine.replace(/\r$/, "");
    if (!line) continue;
    if (line.startsWith(":")) continue; // comment/heartbeat
    const idx = line.indexOf(":");
    if (idx === -1) continue;
    const field = line.slice(0, idx);
    const value = line.slice(idx + 1).replace(/^ /, "");
    if (field === "event") event = value;
    else if (field === "data") dataLines.push(value);
  }
  if (dataLines.length === 0) return null;
  return { event, data: dataLines.join("\n") };
}

export async function sendChatStream(
  auth: ClientAuthContext,
  provider: Provider,
  model: string,
  documentId: string,
  question: string,
  conversationId: string | null,
  callbacks: SendChatStreamCallbacks,
  signal?: AbortSignal,
  topK?: number,
  similarityThreshold?: number,
  documentIds?: string[]
): Promise<void> {
  const res = await apiFetch("/api/chat/stream", {
    method: "POST",
    headers: baseHeaders(auth, { includeJson: true, includeProviderKey: true }),
    body: JSON.stringify({
      provider,
      model: model.trim(),
      document_id: documentId,
      document_ids: documentIds && documentIds.length > 1 ? documentIds : undefined,
      question: question.trim(),
      conversation_id: conversationId,
      top_k: topK,
      similarity_threshold: similarityThreshold,
    }),
    signal,
  });

  if (!res.ok) {
    // When the server returns a non-2xx (e.g. auth / validation), there's
    // no SSE stream — surface the JSON error like the non-streaming path.
    throw new Error(await errorMessage(res));
  }
  const body = res.body;
  if (!body) {
    throw new Error("Streaming response has no body.");
  }

  const reader = body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";

  const dispatchFrame = (frame: string) => {
    const parsed = parseSseFrame(frame);
    if (!parsed) return;
    let payload: unknown = parsed.data;
    try {
      payload = JSON.parse(parsed.data);
    } catch {
      // Keep payload as the raw string.
    }
    switch (parsed.event) {
      case "sources":
        callbacks.onSources?.(payload as { conversation_id: string; sources: Citation[]; stages?: RetrievalStages });
        break;
      case "token":
        callbacks.onToken?.((payload as { delta: string }).delta ?? "");
        break;
      case "message_saved":
        callbacks.onMessageSaved?.(payload as { conversation_id: string; message_id: string });
        break;
      case "grounding":
        callbacks.onGrounding?.(payload as GroundingSummary);
        break;
      case "done":
        callbacks.onDone?.(payload as { content: string });
        break;
      case "error":
        callbacks.onError?.(payload as { error: string; code?: string });
        break;
    }
  };

  const consumeCompleteFrames = () => {
    // Uvicorn uses \n\n; some proxies use \r\n\r\n.
    while (true) {
      const m = buffer.match(/^([\s\S]*?)(\r\n\r\n|\n\n)/);
      if (!m) break;
      dispatchFrame(m[1]);
      buffer = buffer.slice(m[0].length);
    }
  };

  try {
    while (true) {
      const { value, done } = await reader.read();
      if (value?.byteLength) {
        buffer += decoder.decode(value, { stream: !done });
      } else if (done) {
        buffer += decoder.decode(new Uint8Array(), { stream: false });
      }
      consumeCompleteFrames();
      if (done) {
        const tail = buffer.trim();
        if (tail) {
          dispatchFrame(tail);
        }
        break;
      }
    }
  } finally {
    try {
      reader.releaseLock();
    } catch {
      /* ignore */
    }
  }
}

/**
 * Re-executes a previously sent chat message to produce an updated response.
 *
 * @param topK - Optional maximum number of retrieved documents to consider for the rerun
 * @param similarityThreshold - Optional minimum similarity score required for retrieved documents
 * @returns The updated ChatResponse for the rerun operation
 */
export async function rerunMessage(
  auth: ClientAuthContext,
  provider: Provider,
  model: string,
  documentId: string,
  conversationId: string,
  messageId: string,
  topK?: number,
  similarityThreshold?: number
): Promise<ChatResponse> {
  const res = await apiFetch("/api/chat/rerun", {
    method: "POST",
    headers: baseHeaders(auth, { includeJson: true, includeProviderKey: true }),
    body: JSON.stringify({
      provider,
      model: model.trim(),
      document_id: documentId,
      conversation_id: conversationId,
      message_id: messageId,
      top_k: topK,
      similarity_threshold: similarityThreshold,
    }),
  });
  if (!res.ok) throw new Error(await errorMessage(res));
  return res.json();
}

async function errorMessage(res: Response): Promise<string> {
  try {
    const ct = res.headers.get("content-type") ?? "";
    if (ct.includes("application/json")) {
      const data = (await res.json()) as ApiError & { detail?: string };
      if (data.error) return data.error;
      if (data.detail) return data.detail;
      if (data.code) return `Request failed (${res.status}, ${data.code})`;
      return `Request failed (${res.status})`;
    }
  } catch {
    return `Request failed (${res.status})`;
  }
  return `Request failed (${res.status})`;
}

export async function signup(email: string, password: string): Promise<AuthUser> {
  const res = await apiFetch("/api/auth/signup", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) throw new Error(await errorMessage(res));
  const user = (await res.json()) as AuthUser;
  updateStoredSession({ authToken: user.session_token ?? null });
  return user;
}

export async function login(email: string, password: string): Promise<AuthUser> {
  const res = await apiFetch("/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) throw new Error(await errorMessage(res));
  const user = (await res.json()) as AuthUser;
  updateStoredSession({ authToken: user.session_token ?? null });
  return user;
}

export async function logout(): Promise<void> {
  const res = await apiFetch("/api/auth/logout", {
    method: "POST",
    headers: baseHeaders({}),
  });
  if (!res.ok) throw new Error(await errorMessage(res));
  updateStoredSession({ authToken: null });
}

export async function me(): Promise<AuthUser | null> {
  const res = await apiFetch("/api/auth/me", { headers: baseHeaders({}) });
  if (res.status === 401) return null;
  if (!res.ok) throw new Error(await errorMessage(res));
  return res.json();
}

export async function getGoogleOAuthClientId(): Promise<string | null> {
  const res = await apiFetch("/api/auth/google/config", { headers: baseHeaders({}) });
  if (!res.ok) return null;
  try {
    const data = await res.json();
    return data.client_id || null;
  } catch {
    return null;
  }
}
export async function googleLogin(code: string, redirectUri: string): Promise<AuthUser> {
  const res = await apiFetch("/api/auth/google/callback", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ code, redirect_uri: redirectUri }),
  });
  if (!res.ok) throw new Error(await errorMessage(res));
  const user = (await res.json()) as AuthUser;
  updateStoredSession({ authToken: user.session_token ?? null });
  return user;
}

export async function changePassword(currentPassword: string, newPassword: string): Promise<void> {
  const res = await apiFetch("/api/auth/change-password", {
    method: "POST",
    headers: { ...baseHeaders({}, { includeJson: true }), "Content-Type": "application/json" },
    body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
  });
  if (!res.ok) throw new Error(await errorMessage(res));
}

export async function listUsers(): Promise<AuthUser[]> {
  const res = await apiFetch("/api/users", { headers: baseHeaders({}) });
  if (!res.ok) throw new Error(await errorMessage(res));
  const data = (await res.json()) as { users?: AuthUser[] };
  return data.users ?? [];
}

export async function updateUser(userId: string, payload: UpdateUserPayload): Promise<AuthUser> {
  const res = await apiFetch(`/api/users/${userId}`, {
    method: "PATCH",
    headers: { ...baseHeaders({}, { includeJson: true }), "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(await errorMessage(res));
  return res.json();
}

/**
 * Fetches the analytics overview containing aggregate totals, recent activity, and per-provider breakdowns.
 *
 * @returns An AnalyticsOverview containing totals, recent activity, and provider-specific counts.
 */
export async function getAnalyticsOverview(): Promise<AnalyticsOverview> {
  const res = await apiFetch("/api/analytics/overview", { headers: baseHeaders({}) });
  if (!res.ok) throw new Error(await errorMessage(res));
  return res.json();
}

export interface ModelsResponse {
  provider: Provider;
  chat_models: string[];
  embedding_models: string[];
}

/**
 * Fetches the available chat and embedding models for the given provider.
 *
 * @param provider - The model provider (`"openai"` or `"gemini"`) to query
 * @returns An object containing `provider`, `chat_models`, and `embedding_models`
 * @throws Error with the server-provided message when the request fails
 */
export async function fetchModels(
  auth: ClientAuthContext,
  provider: Provider
): Promise<ModelsResponse> {
  const res = await apiFetch(`/api/models?provider=${encodeURIComponent(provider)}`, {
    headers: baseHeaders(auth, { includeProviderKey: true }),
  });
  if (!res.ok) throw new Error(await errorMessage(res));
  return res.json();
}

export type Provider = "openai" | "gemini"; // | "vertex_search";

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

export interface ChatResponse {
  conversation_id: string;
  message_id: string;
  sources: Citation[];
  content: string;
}

export async function sendChat(
  auth: ClientAuthContext,
  provider: Provider,
  model: string,
  documentId: string,
  question: string,
  conversationId: string | null,
  signal?: AbortSignal
): Promise<ChatResponse> {
  const res = await apiFetch("/api/chat", {
    method: "POST",
    headers: baseHeaders(auth, { includeJson: true, includeProviderKey: true }),
    body: JSON.stringify({
      provider,
      model: model.trim(),
      document_id: documentId,
      question: question.trim(),
      conversation_id: conversationId,
    }),
    signal,
  });

  if (!res.ok) {
    throw new Error(await errorMessage(res));
  }

  return res.json();
}

export async function rerunMessage(
  auth: ClientAuthContext,
  provider: Provider,
  model: string,
  documentId: string,
  conversationId: string,
  messageId: string
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

export async function getAnalyticsOverview(): Promise<AnalyticsOverview> {
  const res = await apiFetch("/api/analytics/overview", { headers: baseHeaders({}) });
  if (!res.ok) throw new Error(await errorMessage(res));
  return res.json();
}

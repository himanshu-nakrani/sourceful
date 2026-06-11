"""Pydantic request and response models for the production API."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from backend.settings import settings


class Citation(BaseModel):
    chunk_id: str
    document_id: str
    excerpt: str
    score: float
    page_number: int | None = None
    # Phase 2 — distinguish primary source citations from saved-knowledge
    # artifact citations so the UI can render them differently. Defaults to
    # ``"text"`` so existing single-document chat keeps its current shape.
    chunk_type: str = "text"
    artifact_metadata: dict | None = None


class DocumentResponse(BaseModel):
    id: str
    filename: str
    provider: str
    embedding_model: str
    mime_type: str
    checksum: str
    chunk_count: int
    file_size: int
    page_count: int | None = None
    status: str
    current_job_id: str | None = None
    current_stage: str | None = None
    last_job_id: str | None = None
    created_at: datetime
    processed_at: datetime | None = None
    last_error: str | None = None
    workspace_id: str | None = None


class DocumentListResponse(BaseModel):
    documents: list[DocumentResponse]


class JobResponse(BaseModel):
    id: str
    document_id: str
    status: str
    stage: str
    progress: float
    progress_detail: str | None = None
    attempt_count: int
    max_attempts: int
    next_retry_at: datetime | None = None
    terminal: bool = False
    error_message: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    updated_at: datetime


class IngestResponse(BaseModel):
    document_id: str
    job_id: str | None = None
    status: str
    embedding_model: str
    deduplicated: bool = False


class ChatRequest(BaseModel):
    provider: Literal["openai", "gemini"]
    model: str = Field(max_length=128)
    document_id: str | None = None
    document_ids: list[str] | None = None
    question: str = Field(min_length=1, max_length=settings.max_question_length)
    conversation_id: str | None = None
    top_k: int | None = Field(default=None, ge=1, le=20)
    similarity_threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    # Phase 1 — workspace-scoped chat. When ``workspace_id`` is provided and no
    # explicit ``document_id``/``document_ids`` are supplied, retrieval spans
    # all ready sources in the workspace. ``source_ids`` optionally narrows
    # retrieval to a subset of ``workspace_sources.id`` values.
    workspace_id: str | None = None
    source_ids: list[str] | None = None
    # Phase 2 — analysis mode. ``ask`` is the default grounded Q&A mode.
    # ``compare`` produces structured similarities/differences across sources;
    # ``extract`` produces normalized field extraction; ``brief`` produces an
    # executive summary. Modes only change the system prompt; retrieval and
    # citation contracts are preserved.
    mode: Literal["ask", "compare", "extract", "brief"] | None = None


class RerunMessageRequest(BaseModel):
    provider: Literal["openai", "gemini"]
    model: str = Field(max_length=128)
    document_id: str
    conversation_id: str = Field(min_length=1)
    message_id: str = Field(min_length=1)
    top_k: int | None = Field(default=None, ge=1, le=20)
    similarity_threshold: float | None = Field(default=None, ge=0.0, le=1.0)


class MessageResponse(BaseModel):
    id: str
    role: str
    content: str
    sources: list[Citation] | None = None
    mode: str | None = None
    created_at: datetime


class ConversationResponse(BaseModel):
    id: str
    document_id: str
    title: str
    created_at: datetime
    updated_at: datetime
    messages: list[MessageResponse] = []
    workspace_id: str | None = None


class ConversationListItem(BaseModel):
    id: str
    document_id: str
    title: str
    created_at: datetime
    updated_at: datetime
    message_count: int = 0
    workspace_id: str | None = None


class ConversationListResponse(BaseModel):
    conversations: list[ConversationListItem]


class UpdateConversationRequest(BaseModel):
    title: str = Field(min_length=1, max_length=120)


class ChunkPreviewResponse(BaseModel):
    chunk_id: str
    document_id: str
    content: str
    page_number: int | None = None
    chunk_index: int


class DocumentStatusResponse(BaseModel):
    status: str
    chunk_count: int
    current_job_id: str | None = None
    current_stage: str | None = None
    last_job_id: str | None = None
    last_error: str | None = None


class SignupRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=8, max_length=256)


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=256)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=8, max_length=256)


class UserResponse(BaseModel):
    id: str
    email: str
    role: str
    is_active: bool
    is_verified: bool
    created_at: datetime | None = None
    updated_at: datetime | None = None


class AuthResponse(UserResponse):
    session_token: str


class UserListResponse(BaseModel):
    users: list[UserResponse]


class UpdateUserRequest(BaseModel):
    role: Literal["admin", "user"] | None = None
    is_active: bool | None = None


class AnalyticsProviderBreakdown(BaseModel):
    provider: str
    documents: int
    ready_documents: int


class AnalyticsTotals(BaseModel):
    users: int
    active_users_7d: int
    documents: int
    ready_documents: int
    conversations: int
    messages: int
    chunks: int


class AnalyticsRecent(BaseModel):
    signups_7d: int
    uploads_7d: int
    questions_24h: int
    sessions_24h: int


class AnalyticsOverviewResponse(BaseModel):
    totals: AnalyticsTotals
    recent: AnalyticsRecent
    provider_breakdown: list[AnalyticsProviderBreakdown]


class StructuredExtractRequest(BaseModel):
    """Request body for structured field extraction (Phase 2.6)."""
    provider: Literal["openai", "gemini"]
    model: str = Field(max_length=128)
    schema_fields: dict = Field(
        ...,
        description='JSON schema describing fields to extract. Example: {"title": "string", "author": "string"}',
    )


class StructuredExtractResponse(BaseModel):
    """Response from structured field extraction."""
    document_id: str
    fields: dict
    model: str
    token_usage: dict | None = None


class FeedbackRequest(BaseModel):
    """Phase 3.8: thumbs-up/down per assistant message."""

    conversation_id: str = Field(min_length=1)
    message_id: str = Field(min_length=1)
    rating: Literal["up", "down"]
    comment: str | None = Field(default=None, max_length=2000)


class FeedbackResponse(BaseModel):
    """Envelope returned after recording feedback."""

    id: str
    conversation_id: str
    message_id: str
    rating: Literal["up", "down"]
    comment: str | None = None
    created_at: datetime


class WorkspaceResponse(BaseModel):
    id: str
    name: str
    slug: str | None = None
    description: str | None = None
    visibility: Literal["private", "shared"] = "private"
    archived: bool = False
    is_default: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None


class WorkspaceListResponse(BaseModel):
    workspaces: list[WorkspaceResponse]


class MyRoleResponse(BaseModel):
    role: Literal["owner", "admin", "editor", "viewer"] | None = None


class CreateWorkspaceRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    visibility: Literal["private", "shared"] = "private"


class UpdateWorkspaceRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    visibility: Literal["private", "shared"] | None = None
    archived: bool | None = None


class WorkspaceSourceResponse(BaseModel):
    id: str
    workspace_id: str
    source_type: Literal["file", "url", "note"]
    document_id: str | None = None
    source_title: str
    source_url: str | None = None
    mime_type: str | None = None
    status: Literal["queued", "processing", "ready", "error"]
    last_fetched_at: datetime | None = None
    metadata: dict = Field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None
    # Phase 3 — sync state surfaced from ``workspace_sources`` columns added in
    # migration v14. ``last_sync_status`` is populated by URL refetch flows;
    # file-only sources keep these fields null.
    last_sync_status: Literal["running", "success", "error"] | None = None
    last_sync_error: str | None = None
    next_sync_at: datetime | None = None


class WorkspaceSourceListResponse(BaseModel):
    sources: list[WorkspaceSourceResponse]


class CreateUrlSourceRequest(BaseModel):
    url: str = Field(min_length=1, max_length=2048)
    title: str | None = Field(default=None, max_length=300)
    provider: Literal["openai", "gemini"] | None = None
    embedding_model: str | None = Field(default=None, max_length=128)


class ArtifactResponse(BaseModel):
    id: str
    workspace_id: str
    artifact_type: Literal["user_note", "saved_answer", "saved_brief", "extraction_result"]
    title: str
    content: str
    metadata: dict = Field(default_factory=dict)
    source_message_id: str | None = None
    created_by: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ArtifactListResponse(BaseModel):
    artifacts: list[ArtifactResponse]


class CreateArtifactRequest(BaseModel):
    artifact_type: Literal["user_note", "saved_answer", "saved_brief", "extraction_result"] = "user_note"
    title: str = Field(min_length=1, max_length=300)
    content: str = Field(min_length=1)
    metadata: dict | None = None
    source_message_id: str | None = None


class UpdateArtifactRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    content: str | None = None
    metadata: dict | None = None


class SaveAssistantMessageRequest(BaseModel):
    message_id: str = Field(min_length=1)
    title: str | None = Field(default=None, max_length=300)
    artifact_type: Literal["saved_answer", "saved_brief", "extraction_result"] | None = None


class WorkspaceMemberResponse(BaseModel):
    id: str
    workspace_id: str
    user_id: str
    email: str | None = None
    role: Literal["owner", "admin", "editor", "viewer"]
    joined_at: datetime | None = None


class WorkspaceMemberListResponse(BaseModel):
    members: list[WorkspaceMemberResponse]


class CreateWorkspaceMemberRequest(BaseModel):
    user_id: str = Field(min_length=1)
    role: Literal["admin", "editor", "viewer"] = "viewer"


class UpdateWorkspaceMemberRequest(BaseModel):
    role: Literal["admin", "editor", "viewer"]


class WorkspaceInvitationResponse(BaseModel):
    id: str
    workspace_id: str
    email: str
    role: Literal["owner", "admin", "editor", "viewer"]
    token: str
    invited_by: str | None = None
    accepted_at: datetime | None = None
    expires_at: datetime | None = None
    created_at: datetime | None = None


class WorkspaceInvitationListResponse(BaseModel):
    invitations: list[WorkspaceInvitationResponse]


class CreateWorkspaceInvitationRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    role: Literal["admin", "editor", "viewer"] = "viewer"
    expires_in_days: int | None = Field(default=14, ge=1, le=365)


class AcceptWorkspaceInvitationRequest(BaseModel):
    token: str = Field(min_length=1)


class SyncRunResponse(BaseModel):
    id: str
    workspace_id: str
    source_id: str
    status: Literal["queued", "running", "success", "error"]
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_message: str | None = None
    checksum: str | None = None


class SyncRunListResponse(BaseModel):
    runs: list[SyncRunResponse]


class FeedbackSummaryResponse(BaseModel):
    """Aggregate feedback counts surfaced to the admin analytics page."""

    total: int
    up: int
    down: int
    recent: list[FeedbackResponse] = []

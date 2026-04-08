"""Pydantic request and response models for the production API."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class Citation(BaseModel):
    chunk_id: str
    document_id: str
    excerpt: str
    score: float
    page_number: int | None = None


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


class DocumentListResponse(BaseModel):
    documents: list[DocumentResponse]


class JobResponse(BaseModel):
    id: str
    document_id: str
    status: str
    stage: str
    progress: float
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
    document_id: str
    question: str = Field(min_length=1)
    conversation_id: str | None = None


class MessageResponse(BaseModel):
    id: str
    role: str
    content: str
    sources: list[Citation] | None = None
    created_at: datetime


class ConversationResponse(BaseModel):
    id: str
    document_id: str
    title: str
    created_at: datetime
    updated_at: datetime
    messages: list[MessageResponse] = []


class ConversationListItem(BaseModel):
    id: str
    document_id: str
    title: str
    created_at: datetime
    updated_at: datetime
    message_count: int = 0


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


class UserListResponse(BaseModel):
    users: list[UserResponse]


class UpdateUserRequest(BaseModel):
    role: Literal["admin", "user"] | None = None
    is_active: bool | None = None

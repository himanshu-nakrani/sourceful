from collections.abc import Iterable

from backend.settings import settings


SQLITE_MIGRATION_VERSION = 12
POSTGRES_MIGRATION_VERSION = 12


def _split_statements(script: str) -> list[str]:
    """
    Split an SQL script into individual statements.
    
    Parameters:
        script (str): The SQL script containing one or more statements.
    
    Returns:
        list[str]: Trimmed SQL statements with empty segments removed.
    """
    return [statement.strip() for statement in script.split(";") if statement.strip()]


SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY
);
CREATE TABLE IF NOT EXISTS service_heartbeats (
    service_name TEXT PRIMARY KEY,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS rate_limit_windows (
    bucket_id TEXT NOT NULL,
    window_start INTEGER NOT NULL,
    request_count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (bucket_id, window_start)
);
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL,
    filename TEXT NOT NULL,
    provider TEXT NOT NULL,
    embedding_model TEXT NOT NULL,
    mime_type TEXT NOT NULL,
    checksum TEXT NOT NULL,
    file_bytes BLOB,
    chunk_count INTEGER NOT NULL DEFAULT 0,
    file_size INTEGER NOT NULL DEFAULT 0,
    page_count INTEGER,
    status TEXT NOT NULL DEFAULT 'queued',
    current_job_id TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    processed_at TEXT,
    last_error TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_documents_owner_checksum_model
    ON documents (owner_id, checksum, provider, embedding_model);
CREATE INDEX IF NOT EXISTS idx_documents_owner_created
    ON documents (owner_id, created_at DESC);
CREATE TABLE IF NOT EXISTS document_jobs (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL,
    owner_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    embedding_model TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued',
    stage TEXT NOT NULL DEFAULT 'queued',
    progress REAL NOT NULL DEFAULT 0,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 3,
    error_message TEXT,
    payload_filename TEXT NOT NULL,
    payload_mime_type TEXT NOT NULL,
    payload_bytes BLOB,
    provider_api_key TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    started_at TEXT,
    finished_at TEXT,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_document_jobs_status_created
    ON document_jobs (status, created_at ASC);
CREATE TABLE IF NOT EXISTS document_chunks (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL,
    owner_id TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    page_number INTEGER,
    embedding_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_document_chunks_document
    ON document_chunks (document_id, chunk_index);
CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL,
    document_id TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT 'New conversation',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_conversations_owner_document
    ON conversations (owner_id, document_id, updated_at DESC);
CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL,
    conversation_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    sources_json TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_messages_conversation_created
    ON messages (conversation_id, created_at ASC);
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'user',
    is_active INTEGER NOT NULL DEFAULT 1,
    is_verified INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_users_email ON users (email);
CREATE TABLE IF NOT EXISTS auth_sessions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    token_hash TEXT NOT NULL UNIQUE,
    user_agent TEXT,
    ip_address TEXT,
    expires_at TEXT NOT NULL,
    revoked INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_auth_sessions_user ON auth_sessions (user_id, revoked);
CREATE INDEX IF NOT EXISTS idx_auth_sessions_expires ON auth_sessions (expires_at);

-- Phase 4: Workspaces, Usage, Prompts, Connectors (v10)
CREATE TABLE IF NOT EXISTS workspaces (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    slug TEXT NOT NULL UNIQUE,
    owner_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    settings TEXT DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_workspaces_slug ON workspaces(slug);
CREATE INDEX IF NOT EXISTS idx_workspaces_owner ON workspaces(owner_id);

CREATE TABLE IF NOT EXISTS workspace_members (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role TEXT NOT NULL DEFAULT 'viewer' CHECK (role IN ('owner', 'admin', 'editor', 'viewer')),
    joined_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(workspace_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_workspace_members_workspace ON workspace_members(workspace_id);
CREATE INDEX IF NOT EXISTS idx_workspace_members_user ON workspace_members(user_id);

ALTER TABLE documents ADD COLUMN workspace_id TEXT REFERENCES workspaces(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS idx_documents_workspace ON documents(workspace_id);

CREATE TABLE IF NOT EXISTS usage_records (
    id TEXT PRIMARY KEY,
    workspace_id TEXT REFERENCES workspaces(id) ON DELETE CASCADE,
    user_id TEXT REFERENCES users(id) ON DELETE SET NULL,
    resource_type TEXT NOT NULL CHECK (resource_type IN ('tokens_input', 'tokens_output', 'storage_bytes', 'api_calls', 'searches')),
    quantity INTEGER NOT NULL DEFAULT 0,
    period TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_usage_records_workspace_period ON usage_records(workspace_id, period);
CREATE INDEX IF NOT EXISTS idx_usage_records_user ON usage_records(user_id);

CREATE TABLE IF NOT EXISTS workspace_quotas (
    workspace_id TEXT PRIMARY KEY REFERENCES workspaces(id) ON DELETE CASCADE,
    max_storage_bytes INTEGER DEFAULT 1073741824,
    max_tokens_per_month INTEGER DEFAULT 1000000,
    max_documents INTEGER DEFAULT 100,
    max_members INTEGER DEFAULT 10
);

CREATE TABLE IF NOT EXISTS prompts (
    id TEXT PRIMARY KEY,
    workspace_id TEXT REFERENCES workspaces(id) ON DELETE CASCADE,
    created_by TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT,
    system_prompt TEXT,
    user_prompt_template TEXT,
    variables TEXT DEFAULT '[]',
    is_shared BOOLEAN NOT NULL DEFAULT FALSE,
    is_default BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_prompts_workspace ON prompts(workspace_id);

CREATE TABLE IF NOT EXISTS share_links (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    resource_type TEXT NOT NULL CHECK (resource_type IN ('document', 'conversation', 'workspace')),
    resource_id TEXT NOT NULL,
    token TEXT NOT NULL UNIQUE,
    permissions TEXT NOT NULL DEFAULT '{"role": "viewer"}',
    expires_at TEXT,
    access_count INTEGER DEFAULT 0,
    last_accessed_at TEXT,
    created_by TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_share_links_token ON share_links(token);
CREATE INDEX IF NOT EXISTS idx_share_links_resource ON share_links(resource_type, resource_id);

CREATE TABLE IF NOT EXISTS connectors (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    source_type TEXT NOT NULL CHECK (source_type IN ('google_drive', 'notion', 'confluence', 's3')),
    name TEXT NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    credentials_encrypted TEXT,
    sync_interval_minutes INTEGER DEFAULT 60,
    last_sync_at TEXT,
    last_sync_status TEXT CHECK (last_sync_status IN ('success', 'error', 'in_progress', NULL)),
    last_sync_error TEXT,
    include_paths TEXT DEFAULT '[]',
    exclude_paths TEXT DEFAULT '[]',
    options TEXT DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_connectors_workspace ON connectors(workspace_id);

CREATE TABLE IF NOT EXISTS connector_syncs (
    id TEXT PRIMARY KEY,
    connector_id TEXT NOT NULL REFERENCES connectors(id) ON DELETE CASCADE,
    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TEXT,
    status TEXT NOT NULL CHECK (status IN ('success', 'error', 'partial')),
    documents_added INTEGER DEFAULT 0,
    documents_updated INTEGER DEFAULT 0,
    documents_failed INTEGER DEFAULT 0,
    error_message TEXT
);
CREATE INDEX IF NOT EXISTS idx_connector_syncs_connector ON connector_syncs(connector_id);

-- v12: knowledge-workspace Phase 0 additions
ALTER TABLE workspaces ADD COLUMN owner_scope TEXT;
ALTER TABLE workspaces ADD COLUMN description TEXT;
ALTER TABLE workspaces ADD COLUMN visibility TEXT NOT NULL DEFAULT 'private';
ALTER TABLE workspaces ADD COLUMN archived INTEGER NOT NULL DEFAULT 0;
ALTER TABLE workspaces ADD COLUMN is_default INTEGER NOT NULL DEFAULT 0;
CREATE INDEX IF NOT EXISTS idx_workspaces_owner_scope ON workspaces(owner_scope);

ALTER TABLE conversations ADD COLUMN workspace_id TEXT REFERENCES workspaces(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS idx_conversations_workspace ON conversations(workspace_id);

CREATE TABLE IF NOT EXISTS workspace_sources (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    source_type TEXT NOT NULL DEFAULT 'file' CHECK (source_type IN ('file', 'url', 'note')),
    document_id TEXT REFERENCES documents(id) ON DELETE CASCADE,
    source_title TEXT NOT NULL,
    source_url TEXT,
    mime_type TEXT,
    status TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued','processing','ready','error')),
    last_fetched_at TEXT,
    metadata_json TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_workspace_sources_workspace ON workspace_sources(workspace_id);
CREATE INDEX IF NOT EXISTS idx_workspace_sources_document ON workspace_sources(document_id);

INSERT OR IGNORE INTO schema_migrations (version) VALUES (1), (11), (12);
"""


POSTGRES_SCHEMA = """
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY
);
CREATE TABLE IF NOT EXISTS service_heartbeats (
    service_name TEXT PRIMARY KEY,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS rate_limit_windows (
    bucket_id TEXT NOT NULL,
    window_start BIGINT NOT NULL,
    request_count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (bucket_id, window_start)
);
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL,
    filename TEXT NOT NULL,
    provider TEXT NOT NULL,
    embedding_model TEXT NOT NULL,
    mime_type TEXT NOT NULL,
    checksum TEXT NOT NULL,
    file_bytes BYTEA,
    chunk_count INTEGER NOT NULL DEFAULT 0,
    file_size INTEGER NOT NULL DEFAULT 0,
    page_count INTEGER,
    status TEXT NOT NULL DEFAULT 'queued',
    current_job_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processed_at TIMESTAMPTZ,
    last_error TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_documents_owner_checksum_model
    ON documents (owner_id, checksum, provider, embedding_model);
CREATE INDEX IF NOT EXISTS idx_documents_owner_created
    ON documents (owner_id, created_at DESC);
CREATE TABLE IF NOT EXISTS document_jobs (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    owner_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    embedding_model TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued',
    stage TEXT NOT NULL DEFAULT 'queued',
    progress DOUBLE PRECISION NOT NULL DEFAULT 0,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 3,
    error_message TEXT,
    payload_filename TEXT NOT NULL,
    payload_mime_type TEXT NOT NULL,
    payload_bytes BYTEA,
    provider_api_key TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_document_jobs_status_created
    ON document_jobs (status, created_at ASC);
CREATE TABLE IF NOT EXISTS document_chunks (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    owner_id TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    page_number INTEGER,
    embedding VECTOR,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_document_chunks_document
    ON document_chunks (document_id, chunk_index);
CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL,
    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    title TEXT NOT NULL DEFAULT 'New conversation',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_conversations_owner_document
    ON conversations (owner_id, document_id, updated_at DESC);
CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    sources_json TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_messages_conversation_created
    ON messages (conversation_id, created_at ASC);
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'user',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    is_verified BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_users_email ON users (email);
CREATE TABLE IF NOT EXISTS auth_sessions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL UNIQUE,
    user_agent TEXT,
    ip_address TEXT,
    expires_at TIMESTAMPTZ NOT NULL,
    revoked BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_auth_sessions_user ON auth_sessions (user_id, revoked);
CREATE INDEX IF NOT EXISTS idx_auth_sessions_expires ON auth_sessions (expires_at);

-- Phase 4: Workspaces, Usage, Prompts, Connectors (v10)
CREATE TABLE IF NOT EXISTS workspaces (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    slug TEXT NOT NULL UNIQUE,
    owner_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    settings JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_workspaces_slug ON workspaces(slug);
CREATE INDEX IF NOT EXISTS idx_workspaces_owner ON workspaces(owner_id);

CREATE TABLE IF NOT EXISTS workspace_members (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role TEXT NOT NULL DEFAULT 'viewer' CHECK (role IN ('owner', 'admin', 'editor', 'viewer')),
    joined_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(workspace_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_workspace_members_workspace ON workspace_members(workspace_id);
CREATE INDEX IF NOT EXISTS idx_workspace_members_user ON workspace_members(user_id);

ALTER TABLE documents ADD COLUMN IF NOT EXISTS workspace_id TEXT REFERENCES workspaces(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS idx_documents_workspace ON documents(workspace_id);

CREATE TABLE IF NOT EXISTS usage_records (
    id TEXT PRIMARY KEY,
    workspace_id TEXT REFERENCES workspaces(id) ON DELETE CASCADE,
    user_id TEXT REFERENCES users(id) ON DELETE SET NULL,
    resource_type TEXT NOT NULL CHECK (resource_type IN ('tokens_input', 'tokens_output', 'storage_bytes', 'api_calls', 'searches')),
    quantity INTEGER NOT NULL DEFAULT 0,
    period TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_usage_records_workspace_period ON usage_records(workspace_id, period);
CREATE INDEX IF NOT EXISTS idx_usage_records_user ON usage_records(user_id);

CREATE TABLE IF NOT EXISTS workspace_quotas (
    workspace_id TEXT PRIMARY KEY REFERENCES workspaces(id) ON DELETE CASCADE,
    max_storage_bytes INTEGER DEFAULT 1073741824,
    max_tokens_per_month INTEGER DEFAULT 1000000,
    max_documents INTEGER DEFAULT 100,
    max_members INTEGER DEFAULT 10
);

CREATE TABLE IF NOT EXISTS prompts (
    id TEXT PRIMARY KEY,
    workspace_id TEXT REFERENCES workspaces(id) ON DELETE CASCADE,
    created_by TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT,
    system_prompt TEXT,
    user_prompt_template TEXT,
    variables JSONB DEFAULT '[]',
    is_shared BOOLEAN NOT NULL DEFAULT FALSE,
    is_default BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_prompts_workspace ON prompts(workspace_id);

CREATE TABLE IF NOT EXISTS share_links (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    resource_type TEXT NOT NULL CHECK (resource_type IN ('document', 'conversation', 'workspace')),
    resource_id TEXT NOT NULL,
    token TEXT NOT NULL UNIQUE,
    permissions JSONB NOT NULL DEFAULT '{"role": "viewer"}',
    expires_at TIMESTAMPTZ,
    access_count INTEGER DEFAULT 0,
    last_accessed_at TIMESTAMPTZ,
    created_by TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_share_links_token ON share_links(token);
CREATE INDEX IF NOT EXISTS idx_share_links_resource ON share_links(resource_type, resource_id);

CREATE TABLE IF NOT EXISTS connectors (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    source_type TEXT NOT NULL CHECK (source_type IN ('google_drive', 'notion', 'confluence', 's3')),
    name TEXT NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    credentials_encrypted TEXT,
    sync_interval_minutes INTEGER DEFAULT 60,
    last_sync_at TIMESTAMPTZ,
    last_sync_status TEXT CHECK (last_sync_status IN ('success', 'error', 'in_progress', NULL)),
    last_sync_error TEXT,
    include_paths JSONB DEFAULT '[]',
    exclude_paths JSONB DEFAULT '[]',
    options JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_connectors_workspace ON connectors(workspace_id);

CREATE TABLE IF NOT EXISTS connector_syncs (
    id TEXT PRIMARY KEY,
    connector_id TEXT NOT NULL REFERENCES connectors(id) ON DELETE CASCADE,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    status TEXT NOT NULL CHECK (status IN ('success', 'error', 'partial')),
    documents_added INTEGER DEFAULT 0,
    documents_updated INTEGER DEFAULT 0,
    documents_failed INTEGER DEFAULT 0,
    error_message TEXT
);
CREATE INDEX IF NOT EXISTS idx_connector_syncs_connector ON connector_syncs(connector_id);

-- v12: knowledge-workspace Phase 0 additions
ALTER TABLE workspaces ADD COLUMN IF NOT EXISTS owner_scope TEXT;
ALTER TABLE workspaces ADD COLUMN IF NOT EXISTS description TEXT;
ALTER TABLE workspaces ADD COLUMN IF NOT EXISTS visibility TEXT NOT NULL DEFAULT 'private';
ALTER TABLE workspaces ADD COLUMN IF NOT EXISTS archived BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE workspaces ADD COLUMN IF NOT EXISTS is_default BOOLEAN NOT NULL DEFAULT FALSE;
CREATE INDEX IF NOT EXISTS idx_workspaces_owner_scope ON workspaces(owner_scope);

ALTER TABLE conversations ADD COLUMN IF NOT EXISTS workspace_id TEXT REFERENCES workspaces(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS idx_conversations_workspace ON conversations(workspace_id);

CREATE TABLE IF NOT EXISTS workspace_sources (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    source_type TEXT NOT NULL DEFAULT 'file' CHECK (source_type IN ('file', 'url', 'note')),
    document_id TEXT REFERENCES documents(id) ON DELETE CASCADE,
    source_title TEXT NOT NULL,
    source_url TEXT,
    mime_type TEXT,
    status TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued','processing','ready','error')),
    last_fetched_at TIMESTAMPTZ,
    metadata_json JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_workspace_sources_workspace ON workspace_sources(workspace_id);
CREATE INDEX IF NOT EXISTS idx_workspace_sources_document ON workspace_sources(document_id);

INSERT INTO schema_migrations (version) VALUES (1), (11), (12) ON CONFLICT (version) DO NOTHING;
"""


def schema_version() -> int:
    return POSTGRES_MIGRATION_VERSION if settings.using_postgres else SQLITE_MIGRATION_VERSION


def migration_statements() -> Iterable[str]:
    script = POSTGRES_SCHEMA if settings.using_postgres else SQLITE_SCHEMA
    return _split_statements(script)


# Migration v10: Phase 4 - Workspaces, Usage, Prompts, Connectors
_SQLITE_V10 = """
-- Workspaces for multi-tenancy
CREATE TABLE IF NOT EXISTS workspaces (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    slug TEXT NOT NULL UNIQUE,
    owner_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    settings TEXT DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_workspaces_slug ON workspaces(slug);
CREATE INDEX IF NOT EXISTS idx_workspaces_owner ON workspaces(owner_id);

-- Workspace membership with RBAC
CREATE TABLE IF NOT EXISTS workspace_members (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role TEXT NOT NULL DEFAULT 'viewer' CHECK (role IN ('owner', 'admin', 'editor', 'viewer')),
    joined_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(workspace_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_workspace_members_workspace ON workspace_members(workspace_id);
CREATE INDEX IF NOT EXISTS idx_workspace_members_user ON workspace_members(user_id);

-- Add workspace_id to documents (skip if already exists from fresh schema)
-- ALTER TABLE documents ADD COLUMN workspace_id TEXT REFERENCES workspaces(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS idx_documents_workspace ON documents(workspace_id);

-- Usage metering
CREATE TABLE IF NOT EXISTS usage_records (
    id TEXT PRIMARY KEY,
    workspace_id TEXT REFERENCES workspaces(id) ON DELETE CASCADE,
    user_id TEXT REFERENCES users(id) ON DELETE SET NULL,
    resource_type TEXT NOT NULL CHECK (resource_type IN ('tokens_input', 'tokens_output', 'storage_bytes', 'api_calls', 'searches')),
    quantity INTEGER NOT NULL DEFAULT 0,
    period TEXT NOT NULL, -- YYYY-MM format for monthly aggregation
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_usage_records_workspace_period ON usage_records(workspace_id, period);
CREATE INDEX IF NOT EXISTS idx_usage_records_user ON usage_records(user_id);

-- Quotas per workspace
CREATE TABLE IF NOT EXISTS workspace_quotas (
    workspace_id TEXT PRIMARY KEY REFERENCES workspaces(id) ON DELETE CASCADE,
    max_storage_bytes INTEGER DEFAULT 1073741824, -- 1GB
    max_tokens_per_month INTEGER DEFAULT 1000000, -- 1M tokens
    max_documents INTEGER DEFAULT 100,
    max_members INTEGER DEFAULT 10
);

-- Prompt library
CREATE TABLE IF NOT EXISTS prompts (
    id TEXT PRIMARY KEY,
    workspace_id TEXT REFERENCES workspaces(id) ON DELETE CASCADE,
    created_by TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT,
    system_prompt TEXT,
    user_prompt_template TEXT,
    variables TEXT DEFAULT '[]', -- JSON array of variable names
    is_shared BOOLEAN NOT NULL DEFAULT FALSE,
    is_default BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_prompts_workspace ON prompts(workspace_id);

-- Shareable links
CREATE TABLE IF NOT EXISTS share_links (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    resource_type TEXT NOT NULL CHECK (resource_type IN ('document', 'conversation', 'workspace')),
    resource_id TEXT NOT NULL,
    token TEXT NOT NULL UNIQUE, -- Random token for URL
    permissions TEXT NOT NULL DEFAULT '{"role": "viewer"}', -- JSON permissions
    expires_at TEXT,
    access_count INTEGER DEFAULT 0,
    last_accessed_at TEXT,
    created_by TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_share_links_token ON share_links(token);
CREATE INDEX IF NOT EXISTS idx_share_links_resource ON share_links(resource_type, resource_id);

-- Connectors for external sources
CREATE TABLE IF NOT EXISTS connectors (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    source_type TEXT NOT NULL CHECK (source_type IN ('google_drive', 'notion', 'confluence', 's3')),
    name TEXT NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    credentials_encrypted TEXT, -- Encrypted credentials JSON
    sync_interval_minutes INTEGER DEFAULT 60,
    last_sync_at TEXT,
    last_sync_status TEXT CHECK (last_sync_status IN ('success', 'error', 'in_progress', NULL)),
    last_sync_error TEXT,
    include_paths TEXT DEFAULT '[]', -- JSON array of patterns
    exclude_paths TEXT DEFAULT '[]',
    options TEXT DEFAULT '{}', -- JSON source-specific options
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_connectors_workspace ON connectors(workspace_id);

-- Connector sync history
CREATE TABLE IF NOT EXISTS connector_syncs (
    id TEXT PRIMARY KEY,
    connector_id TEXT NOT NULL REFERENCES connectors(id) ON DELETE CASCADE,
    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TEXT,
    status TEXT NOT NULL CHECK (status IN ('success', 'error', 'partial')),
    documents_added INTEGER DEFAULT 0,
    documents_updated INTEGER DEFAULT 0,
    documents_failed INTEGER DEFAULT 0,
    error_message TEXT
);
CREATE INDEX IF NOT EXISTS idx_connector_syncs_connector ON connector_syncs(connector_id);

INSERT INTO schema_migrations (version) VALUES (10) ON CONFLICT (version) DO NOTHING;
"""

_POSTGRES_V10 = """
-- Workspaces for multi-tenancy
CREATE TABLE IF NOT EXISTS workspaces (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    slug TEXT NOT NULL UNIQUE,
    owner_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    settings JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_workspaces_slug ON workspaces(slug);
CREATE INDEX IF NOT EXISTS idx_workspaces_owner ON workspaces(owner_id);

-- Workspace membership with RBAC
CREATE TABLE IF NOT EXISTS workspace_members (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role TEXT NOT NULL DEFAULT 'viewer' CHECK (role IN ('owner', 'admin', 'editor', 'viewer')),
    joined_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(workspace_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_workspace_members_workspace ON workspace_members(workspace_id);
CREATE INDEX IF NOT EXISTS idx_workspace_members_user ON workspace_members(user_id);

-- Add workspace_id to documents
ALTER TABLE documents ADD COLUMN IF NOT EXISTS workspace_id TEXT REFERENCES workspaces(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS idx_documents_workspace ON documents(workspace_id);

-- Usage metering
CREATE TABLE IF NOT EXISTS usage_records (
    id TEXT PRIMARY KEY,
    workspace_id TEXT REFERENCES workspaces(id) ON DELETE CASCADE,
    user_id TEXT REFERENCES users(id) ON DELETE SET NULL,
    resource_type TEXT NOT NULL CHECK (resource_type IN ('tokens_input', 'tokens_output', 'storage_bytes', 'api_calls', 'searches')),
    quantity INTEGER NOT NULL DEFAULT 0,
    period TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_usage_records_workspace_period ON usage_records(workspace_id, period);
CREATE INDEX IF NOT EXISTS idx_usage_records_user ON usage_records(user_id);

-- Quotas per workspace
CREATE TABLE IF NOT EXISTS workspace_quotas (
    workspace_id TEXT PRIMARY KEY REFERENCES workspaces(id) ON DELETE CASCADE,
    max_storage_bytes INTEGER DEFAULT 1073741824,
    max_tokens_per_month INTEGER DEFAULT 1000000,
    max_documents INTEGER DEFAULT 100,
    max_members INTEGER DEFAULT 10
);

-- Prompt library
CREATE TABLE IF NOT EXISTS prompts (
    id TEXT PRIMARY KEY,
    workspace_id TEXT REFERENCES workspaces(id) ON DELETE CASCADE,
    created_by TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT,
    system_prompt TEXT,
    user_prompt_template TEXT,
    variables JSONB DEFAULT '[]',
    is_shared BOOLEAN NOT NULL DEFAULT FALSE,
    is_default BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_prompts_workspace ON prompts(workspace_id);

-- Shareable links
CREATE TABLE IF NOT EXISTS share_links (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    resource_type TEXT NOT NULL CHECK (resource_type IN ('document', 'conversation', 'workspace')),
    resource_id TEXT NOT NULL,
    token TEXT NOT NULL UNIQUE,
    permissions JSONB NOT NULL DEFAULT '{"role": "viewer"}',
    expires_at TIMESTAMPTZ,
    access_count INTEGER DEFAULT 0,
    last_accessed_at TIMESTAMPTZ,
    created_by TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_share_links_token ON share_links(token);
CREATE INDEX IF NOT EXISTS idx_share_links_resource ON share_links(resource_type, resource_id);

-- Connectors for external sources
CREATE TABLE IF NOT EXISTS connectors (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    source_type TEXT NOT NULL CHECK (source_type IN ('google_drive', 'notion', 'confluence', 's3')),
    name TEXT NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    credentials_encrypted TEXT,
    sync_interval_minutes INTEGER DEFAULT 60,
    last_sync_at TIMESTAMPTZ,
    last_sync_status TEXT CHECK (last_sync_status IN ('success', 'error', 'in_progress', NULL)),
    last_sync_error TEXT,
    include_paths JSONB DEFAULT '[]',
    exclude_paths JSONB DEFAULT '[]',
    options JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_connectors_workspace ON connectors(workspace_id);

-- Connector sync history
CREATE TABLE IF NOT EXISTS connector_syncs (
    id TEXT PRIMARY KEY,
    connector_id TEXT NOT NULL REFERENCES connectors(id) ON DELETE CASCADE,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    status TEXT NOT NULL CHECK (status IN ('success', 'error', 'partial')),
    documents_added INTEGER DEFAULT 0,
    documents_updated INTEGER DEFAULT 0,
    documents_failed INTEGER DEFAULT 0,
    error_message TEXT
);
CREATE INDEX IF NOT EXISTS idx_connector_syncs_connector ON connector_syncs(connector_id);

INSERT INTO schema_migrations (version) VALUES (10) ON CONFLICT (version) DO NOTHING;
"""

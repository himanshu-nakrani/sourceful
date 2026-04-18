from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "backend/.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    max_document_bytes: int = Field(default=10 * 1024 * 1024, alias="MAX_DOCUMENT_BYTES")
    max_chunks: int = Field(default=800, alias="MAX_CHUNKS")
    chunk_size: int = Field(default=1200, alias="CHUNK_SIZE")
    chunk_overlap: int = Field(default=200, alias="CHUNK_OVERLAP")
    chunk_strategy: str = Field(default="fixed", alias="CHUNK_STRATEGY")
    chunk_semantic_threshold: float = Field(default=0.78, alias="CHUNK_SEMANTIC_THRESHOLD")
    rag_top_k: int = Field(default=5, alias="RAG_TOP_K")
    max_model_name_length: int = Field(default=128, alias="MAX_MODEL_NAME_LENGTH")

    database_url: str | None = Field(default=None, alias="DATABASE_URL")
    database_path: str = Field(default="data/ragapp.db", alias="DATABASE_PATH")
    vector_store_directory: str = Field(default="data/vectors", alias="VECTOR_STORE_DIRECTORY")
    document_registry_path: str = Field(default="data/documents.json", alias="DOCUMENT_REGISTRY_PATH")

    cors_origins: str = Field(
        default=(
            "http://localhost:3000,http://127.0.0.1:3000,"
            "http://localhost:3001,http://127.0.0.1:3001,"
            "http://localhost:3002,http://127.0.0.1:3002"
        ),
        alias="CORS_ORIGINS",
    )
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    rate_limit_rpm: int = Field(default=60, alias="RATE_LIMIT_RPM")
    max_conversation_history: int = Field(default=50, alias="MAX_CONVERSATION_HISTORY")
    max_question_length: int = Field(default=2000, alias="MAX_QUESTION_LENGTH")
    allowed_file_types: str = Field(
        default=".pdf,.txt,.md,.docx,.csv",
        alias="ALLOWED_FILE_TYPES",
    )
    request_timeout_seconds: float = Field(default=60.0, alias="REQUEST_TIMEOUT_SECONDS")
    worker_poll_interval_seconds: float = Field(default=1.5, alias="WORKER_POLL_INTERVAL_SECONDS")
    worker_heartbeat_ttl_seconds: int = Field(default=60, alias="WORKER_HEARTBEAT_TTL_SECONDS")
    service_name: str = Field(default="document-rag", alias="SERVICE_NAME")
    auth_cookie_name: str = Field(default="rag_session", alias="AUTH_COOKIE_NAME")
    auth_cookie_ttl_hours: int = Field(default=168, alias="AUTH_COOKIE_TTL_HOURS")
    auth_secure_cookies: bool = Field(default=False, alias="AUTH_SECURE_COOKIES")

    default_superuser_email: str = Field(default="admin@example.com", alias="DEFAULT_SUPERUSER_EMAIL")
    default_superuser_password: str = Field(..., alias="DEFAULT_SUPERUSER_PASSWORD")

    default_embedding_model_openai: str = Field(
        default="text-embedding-3-small",
        alias="DEFAULT_EMBEDDING_MODEL_OPENAI",
    )
    default_embedding_model_gemini: str = Field(
        default="models/gemini-embedding-001",
        alias="DEFAULT_EMBEDDING_MODEL_GEMINI",
    )
    default_chat_model_openai: str = Field(default="gpt-4o-mini", alias="DEFAULT_CHAT_MODEL_OPENAI")
    default_chat_model_gemini: str = Field(default="gemini-2.5-flash", alias="DEFAULT_CHAT_MODEL_GEMINI")
    default_embedding_model_vertex_search: str = Field(
        default="vertex_search_managed",
        alias="DEFAULT_EMBEDDING_MODEL_VERTEX_SEARCH",
    )
    default_chat_model_vertex_search: str = Field(
        default="gemini-2.5-flash",
        alias="DEFAULT_CHAT_MODEL_VERTEX_SEARCH",
    )

    vertex_search_project: str | None = Field(default="gen-lang-client-0318750942", alias="VERTEX_SEARCH_PROJECT")
    vertex_search_location: str = Field(default="global", alias="VERTEX_SEARCH_LOCATION")
    vertex_search_datastore_id: str | None = Field(default="docuqa-data_1775953648723", alias="VERTEX_SEARCH_DATASTORE_ID")

    google_oauth_client_id: str = Field(
        default="",
        alias="GOOGLE_OAUTH_CLIENT_ID",
    )
    google_oauth_client_secret: str = Field(
        default="",
        alias="GOOGLE_OAUTH_CLIENT_SECRET",
    )

    # ---- Retrieval feature flags (Phase 0/1) ----
    # All default OFF so behavior is unchanged unless explicitly enabled.
    retrieval_hybrid_enabled: bool = Field(default=False, alias="RETRIEVAL_HYBRID_ENABLED")
    retrieval_reranker_enabled: bool = Field(default=False, alias="RETRIEVAL_RERANKER_ENABLED")
    retrieval_contextual_enabled: bool = Field(default=False, alias="RETRIEVAL_CONTEXTUAL_ENABLED")
    retrieval_graph_enabled: bool = Field(default=False, alias="RETRIEVAL_GRAPH_ENABLED")
    retrieval_agent_enabled: bool = Field(default=False, alias="RETRIEVAL_AGENT_ENABLED")

    # Over-fetch factor when reranker is on (retrieve K*factor, rerank down to K)
    reranker_overfetch_factor: int = Field(default=4, alias="RERANKER_OVERFETCH_FACTOR")

    # Reranker provider: "cohere" | "jina" | "bge-local" | "noop"
    reranker_provider: str = Field(default="noop", alias="RERANKER_PROVIDER")
    reranker_model: str = Field(default="rerank-english-v3.0", alias="RERANKER_MODEL")
    reranker_api_key: str | None = Field(default=None, alias="RERANKER_API_KEY")
    reranker_timeout_seconds: float = Field(default=10.0, alias="RERANKER_TIMEOUT_SECONDS")

    # Hybrid search tuning
    hybrid_fts_weight: float = Field(default=1.0, alias="HYBRID_FTS_WEIGHT")
    hybrid_vector_weight: float = Field(default=1.0, alias="HYBRID_VECTOR_WEIGHT")
    hybrid_rrf_k: int = Field(default=60, alias="HYBRID_RRF_K")

    # pgvector HNSW tuning
    pgvector_hnsw_m: int = Field(default=16, alias="PGVECTOR_HNSW_M")
    pgvector_hnsw_ef_construction: int = Field(default=64, alias="PGVECTOR_HNSW_EF_CONSTRUCTION")

    # MMR diversification. lambda=1.0 disables diversity (pure relevance);
    # lambda<1.0 trades relevance for diversity. OFF by default.
    retrieval_mmr_enabled: bool = Field(default=False, alias="RETRIEVAL_MMR_ENABLED")
    retrieval_mmr_lambda: float = Field(default=0.7, alias="RETRIEVAL_MMR_LAMBDA")

    # Query transformations (HyDE / multi-query / step-back). All lanes are
    # RRF-fused with the original dense lane when enabled.
    retrieval_query_transforms_enabled: bool = Field(
        default=False, alias="RETRIEVAL_QUERY_TRANSFORMS_ENABLED"
    )
    # Comma-separated: any of "hyde", "multi_query", "step_back".
    retrieval_query_transforms: str = Field(
        default="multi_query", alias="RETRIEVAL_QUERY_TRANSFORMS"
    )
    retrieval_multi_query_count: int = Field(default=3, alias="RETRIEVAL_MULTI_QUERY_COUNT")

    # Parent-document retrieval. Embeds small child windows but returns the
    # bigger parent window as the citation excerpt to the LLM.
    retrieval_parent_doc_enabled: bool = Field(
        default=False, alias="RETRIEVAL_PARENT_DOC_ENABLED"
    )
    retrieval_parent_window_chars: int = Field(
        default=2400, alias="RETRIEVAL_PARENT_WINDOW_CHARS"
    )
    retrieval_child_window_chars: int = Field(
        default=600, alias="RETRIEVAL_CHILD_WINDOW_CHARS"
    )

    # Context compression before prompt-build. "none" | "heuristic" | "llmlingua".
    context_compression_mode: str = Field(default="none", alias="CONTEXT_COMPRESSION_MODE")
    context_compression_target_tokens: int = Field(
        default=2000, alias="CONTEXT_COMPRESSION_TARGET_TOKENS"
    )

    # Groundedness verifier (second-pass LLM call after generation).
    groundedness_verifier_enabled: bool = Field(
        default=False, alias="GROUNDEDNESS_VERIFIER_ENABLED"
    )
    groundedness_min_score: float = Field(default=0.5, alias="GROUNDEDNESS_MIN_SCORE")

    # ---- Tracing (Langfuse, no-op when unset) ----
    langfuse_public_key: str | None = Field(default=None, alias="LANGFUSE_PUBLIC_KEY")
    langfuse_secret_key: str | None = Field(default=None, alias="LANGFUSE_SECRET_KEY")
    langfuse_host: str = Field(default="https://cloud.langfuse.com", alias="LANGFUSE_HOST")

    @property
    def langfuse_configured(self) -> bool:
        return bool(self.langfuse_public_key and self.langfuse_secret_key)

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def allowed_extensions(self) -> set[str]:
        return {item.strip().lower() for item in self.allowed_file_types.split(",") if item.strip()}

    @property
    def using_postgres(self) -> bool:
        return bool(self.database_url)

    @property
    def vertex_search_configured(self) -> bool:
        return bool(self.vertex_search_project and self.vertex_search_datastore_id)

settings = Settings()
 
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
    rag_top_k: int = Field(default=5, alias="RAG_TOP_K")
    max_model_name_length: int = Field(default=128, alias="MAX_MODEL_NAME_LENGTH")

    database_url: str | None = Field(default=None, alias="DATABASE_URL")
    database_path: str = Field(default="data/ragapp.db", alias="DATABASE_PATH")
    vector_store_directory: str = Field(default="data/vectors", alias="VECTOR_STORE_DIRECTORY")
    document_registry_path: str = Field(default="data/documents.json", alias="DOCUMENT_REGISTRY_PATH")

    cors_origins: str = Field(
        default="http://localhost:3000,http://127.0.0.1:3000",
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

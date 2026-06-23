"""Application configuration — typed, validated, environment-driven.

A single `Settings` object is the source of truth for every runtime knob. It is
loaded once and cached (`get_settings`) so the same immutable instance is shared
process-wide. Values come from environment variables (or a local `.env` in
development); validation fails fast at startup rather than deep inside a request.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any, Literal
from urllib.parse import urlsplit, urlunsplit

from pydantic import Field, ValidationInfo, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Allowed values for the Stage 14 backend-selection flags.
_CACHE_BACKENDS = {"noop", "memory", "redis"}
_VECTOR_SEARCH_MODES = {"scan", "hnsw", "auto"}
_LOCK_BACKENDS = {"memory", "redis"}
_AUDIT_BACKENDS = {"memory", "postgres"}

# Stage 19.4 — secrets management. Fields whose values must never be logged or
# echoed, and URL fields whose embedded credentials must be redacted.
_SECRET_FIELDS = {
    "jwt_secret", "neo4j_password", "openai_api_key", "anthropic_api_key",
    "nvidia_api_key", "langsmith_api_key",
}
_URL_FIELDS = {"postgres_url", "redis_url", "neo4j_uri"}
# Placeholder secrets that must not survive into a production deployment.
_INSECURE_SECRETS = {"neo4j", "password", "changeme", "change-me", "admin", ""}


def mask_secret(value: Any) -> str | None:
    """Mask a secret for safe display: keep nothing but a length hint."""
    if value is None:
        return None
    text = str(value)
    return "***redacted***" if text else ""


def redact_url_credentials(url: str) -> str:
    """Return ``url`` with any embedded ``user:password@`` credentials masked."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return "***redacted***"
    if not parts.hostname or "@" not in parts.netloc:
        return url
    host = parts.hostname or ""
    port = f":{parts.port}" if parts.port else ""
    netloc = f"***:***@{host}{port}"
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))

Environment = Literal["development", "staging", "production"]


class Settings(BaseSettings):
    """Strongly-typed application settings.

    Field names map case-insensitively to environment variables, e.g.
    `postgres_url` <- `POSTGRES_URL`. Missing required values raise at import
    of the settings object, so the process cannot boot half-configured.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Application -------------------------------------------------------
    app_name: str = "MemoryArena"
    app_env: Environment = "development"
    app_debug: bool = False
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    version: str = "0.1.0"
    api_v1_prefix: str = "/api/v1"
    log_level: str = "INFO"

    # --- PostgreSQL --------------------------------------------------------
    # Async SQLAlchemy URL, e.g. postgresql+asyncpg://user:pass@host:5432/db
    postgres_url: str = Field(..., description="Async PostgreSQL connection URL")
    postgres_pool_size: int = 20
    postgres_max_overflow: int = 10
    postgres_pool_timeout: int = 30

    # --- Redis -------------------------------------------------------------
    # Optional: only used when CACHE_BACKEND=redis, AUTH_ENABLED=true, or
    # RATE_LIMIT_ENABLED=true. The default is a harmless placeholder so a minimal
    # (free-tier) deployment with the no-op backends boots without configuring it;
    # the async client is lazy, so it never connects unless actually used.
    redis_url: str = "redis://localhost:6379/0"
    redis_max_connections: int = 50

    # --- Neo4j -------------------------------------------------------------
    # Optional: only connected when GRAPH_BACKEND=neo4j (default is the in-memory
    # graph). Defaults are placeholders so a minimal deployment boots; when the
    # neo4j backend is enabled, real values are required (verified at connect).
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_username: str = "neo4j"
    neo4j_password: str = "neo4j"
    neo4j_database: str = "neo4j"
    neo4j_max_connection_pool_size: int = 50

    # --- LLM providers ----------------------------------------------------
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    nvidia_api_key: str | None = None
    # Provider selection for LLM generation (agent answers + extraction):
    # "deterministic" (offline default; dev/tests), "openai", "anthropic", or
    # "nvidia" (NVIDIA NIM via ChatNVIDIA). For non-OpenAI providers, set
    # LLM_MODEL to a model id that provider serves.
    llm_provider: str = "deterministic"
    llm_model: str = "gpt-4o-mini"
    # Provider for MEMORY EXTRACTION (ingestion + conversational capture),
    # independent of answer generation. Defaults to "deterministic" (local,
    # rule-based, free) so capture keeps working when the answer provider (e.g.
    # NVIDIA) is rate-limited. Accepts the same values as llm_provider.
    extraction_llm_provider: str = "deterministic"
    # Extraction workflow engine: "sequential" (offline default, no LangGraph)
    # or "langgraph" (production; requires the langgraph package).
    workflow_engine: str = "sequential"

    # --- Embeddings -------------------------------------------------------
    # Provider selection: "hash" (deterministic, dependency-free dev default),
    # "openai", or "bge" (local sentence-transformers).
    embedding_provider: str = "hash"
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536

    # --- Knowledge graph --------------------------------------------------
    # Backend: "memory" (offline default) or "neo4j".
    graph_backend: str = "memory"

    # --- Consolidation ----------------------------------------------------
    # Engine: "sequential" (offline default, no LangGraph) or "langgraph".
    consolidation_engine: str = "sequential"
    consolidation_candidate_pool: int = 50
    consolidation_contradict_confidence: float = 0.60
    consolidation_supersede_confidence: float = 0.80

    # --- Context compression ----------------------------------------------
    # Compressor for the context-assembly pipeline: "heuristic" (offline
    # default; whitespace + budget pruning, no LLM) or "llm" (LLM summarization
    # with validation and heuristic fallback).
    context_compressor: str = "heuristic"

    # --- Query-time agent runtime -----------------------------------------
    # Runtime: "sequential" (offline default, no LangGraph) or "langgraph".
    agent_runtime: str = "sequential"
    agent_max_iterations: int = 1
    agent_max_tool_calls: int = 8
    agent_max_citations: int = 10
    agent_timeout_seconds: float = 30.0
    agent_top_k: int = 10
    agent_max_tokens: int = 2000
    agent_answer_max_tokens: int = 512

    # --- Observability (Stage 13) -----------------------------------------
    # Trace recorder for query-time request traces: "in_memory" (default;
    # bounded ring buffer, readable via GET /observability/traces) or "noop".
    # When LANGSMITH_ENABLED is true, the LangSmith exporter takes precedence.
    trace_recorder: str = "in_memory"
    trace_recorder_capacity: int = 200
    # LangSmith export is optional and OFF by default; the langsmith package is
    # imported lazily only when this is enabled (no test/runtime dependency).
    langsmith_enabled: bool = False
    langsmith_api_key: str | None = None
    langsmith_project: str = "memoryarena"
    # Performance metrics sink (Stage 14 Phase 5): "noop" (default) or "memory"
    # (in-process counters + latency aggregates, read via /observability/metrics).
    metrics_sink: str = "noop"

    # --- Maintenance workflows (Stage 11) ---------------------------------
    # When enabled, the lifespan registers the inference handler and the
    # scheduled sweeps/summary jobs. The in-process scheduler runs no live
    # ticker by default; a production driver triggers jobs on these crons.
    maintenance_enabled: bool = True
    inference_confidence_threshold: float = 0.5
    inference_candidate_pool: int = 50
    summary_top_n: int = 10
    summary_max_chars: int = 1200
    decay_cron: str = "0 3 * * *"
    archival_cron: str = "0 4 * * *"
    promotion_cron: str = "0 5 * * *"
    summary_cron: str = "0 6 * * *"

    # --- Stage 17.1: autonomous memory intelligence -----------------------
    # The maintenance job (importance evolution + promotion + clustering +
    # forgetting) is registered on the scheduler; the event handler triggers
    # promotion/clustering reactively after each memory is created. Importance
    # evolution per-retrieval is always on (in the retrieval tracker).
    intelligence_maintenance_enabled: bool = True
    intelligence_event_enabled: bool = True
    intelligence_cron: str = "0 2 * * *"
    # Cron-aware autonomy (Phase 1): the scheduler evaluates each job's cron
    # every ``scheduler_tick_seconds`` and fires only the due ones (so the
    # maintenance job — and ForgettingEngine — run on ``intelligence_cron``,
    # daily at 02:00, not on a fixed interval). 0 disables the live driver.
    scheduler_tick_seconds: float = 60.0
    # Legacy "run every N seconds ignoring cron" driver; kept for dev/tests only.
    # 0 by default — cron mode above is the production driver.
    scheduler_interval_seconds: float = 0.0
    # --- Distributed locking (Stage 18.3) ---------------------------------
    # Coordinates single-owner maintenance across instances: "memory" (default;
    # process-local, no Redis) | "redis" (cross-instance lease). The periodic
    # intelligence maintenance job runs under this lock so only one owner per
    # ``intelligence_lock_key`` executes a cycle at a time.
    lock_backend: str = "memory"
    intelligence_lock_key: str = "intelligence:maintenance"
    # Lease TTL for the maintenance lock; renewed between chunks so a long cycle
    # keeps ownership, while a crashed owner's lease lapses and frees the lock.
    intelligence_lock_ttl_seconds: int = 300
    # --- Parallel intelligence execution (Stage 18.4) ---------------------
    # Max tenants processed concurrently per maintenance cycle. Each tenant uses
    # its own unit of work and disjoint rows, so this overlaps DB/graph I/O up to
    # the ceiling. Keep <= the DB connection pool size. Default 1 = sequential
    # (safe for a single shared connection, e.g. SQLite); raise it on Postgres.
    intelligence_max_concurrency: int = 1
    # --- Audit logging (Stage 19.3) ---------------------------------------
    # Where the audit trail is written: "memory" (default; process-local) or
    # "postgres" (durable audit_log table). Auditing of writes/lifecycle/
    # intelligence actions is always active; this only selects the sink.
    audit_backend: str = "memory"

    # --- Security ----------------------------------------------------------
    jwt_secret: str = Field(..., min_length=16, description="JWT signing secret")
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    # Rotating refresh-token lifetime (Stage 14 Phase 2).
    refresh_token_expire_days: int = 14

    # --- CORS --------------------------------------------------------------
    cors_allowed_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])
    # Whether to send Access-Control-Allow-Credentials. Wildcard origins are
    # unsafe when this is true (a browser will not honor it, and it signals a
    # misconfiguration), so production rejects that combination.
    cors_allow_credentials: bool = True

    # --- Stage 14 hardening flags -----------------------------------------
    # All default to today's behavior so existing clients/tests are unaffected;
    # production adapters are selected (in later phases) by these flags.
    # Authentication enforcement (Phase 2/3). When false, user_id continues to be
    # taken from the request as before (backward compatible).
    auth_enabled: bool = False
    # API rate limiting (Phase 4). When false, the no-op limiter is used.
    rate_limit_enabled: bool = False
    # Fixed-window rate-limit policy (per-identity, per-tier; requests/window).
    rate_limit_window_seconds: int = 60
    rate_limit_default_auth: int = 120          # authenticated, default tier
    rate_limit_default_anon: int = 30           # anonymous (per-IP), default tier
    rate_limit_auth_endpoints_anon: int = 5     # /auth/* per-IP (brute-force defense)
    rate_limit_query_auth: int = 20             # /query (LLM cost)
    rate_limit_query_anon: int = 5
    rate_limit_ingest_auth: int = 30            # /ingest (writes)
    # Honor X-Forwarded-For (first hop) for the client IP behind a trusted proxy.
    rate_limit_trust_forwarded_for: bool = False
    # Cache backend for analytics/health (Phase 5): "noop" (default) | "memory" | "redis".
    cache_backend: str = "noop"
    # TTL safety-net for cached read aggregates (bounds staleness if an
    # invalidation signal is ever missed). Event-driven invalidation is primary.
    cache_ttl_seconds: int = 60
    # Vector search mode (Phase 6): "scan" (default; brute-force, all dialects),
    # "hnsw" (pgvector ANN pushdown), or "auto" (ANN on PostgreSQL, scan elsewhere).
    vector_search_mode: str = "scan"

    # --- Conversational memory capture (Stage 15) -------------------------
    # When true, a user's /query turn is run through a lightweight policy and,
    # if it looks like a durable user fact, submitted to the existing ingestion
    # pipeline (off the request path). OFF by default — opt-in.
    conversation_capture_enabled: bool = False
    capture_min_tokens: int = 2  # minimum tokens for a turn to be capture-eligible

    # --- Deployment (Stage 14 deployment-readiness) -----------------------
    # Create the schema on startup via Base.metadata.create_all. Intended for
    # SQLite/free-tier deploys where Alembic cannot run (migration 0001 enables
    # the pgvector extension). OFF by default; Postgres deploys use Alembic.
    auto_create_schema: bool = False
    # Idempotently seed demo data (users/memories) on startup for a portfolio
    # demo. OFF by default; safe to re-run (skips users that already exist).
    seed_demo_on_startup: bool = False

    @property
    def is_sqlite(self) -> bool:
        return self.postgres_url.startswith("sqlite")

    # --- Derived helpers ---------------------------------------------------
    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def docs_enabled(self) -> bool:
        # OpenAPI/Swagger is disabled in production by default for surface reduction.
        return not self.is_production

    @field_validator("log_level")
    @classmethod
    def _normalise_log_level(cls, value: str) -> str:
        level = value.upper()
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if level not in allowed:
            raise ValueError(f"log_level must be one of {sorted(allowed)}")
        return level

    @field_validator("jwt_secret")
    @classmethod
    def _reject_default_secret(cls, value: str, info: ValidationInfo) -> str:
        if value.lower().startswith("change-me"):
            raise ValueError("JWT_SECRET must be set to a real secret (not the template default)")
        return value

    @field_validator("cors_allowed_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        # Allow a comma-separated string in the environment as well as a JSON list.
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("cache_backend")
    @classmethod
    def _validate_cache_backend(cls, value: str) -> str:
        backend = value.lower()
        if backend not in _CACHE_BACKENDS:
            raise ValueError(f"cache_backend must be one of {sorted(_CACHE_BACKENDS)}")
        return backend

    @field_validator("vector_search_mode")
    @classmethod
    def _validate_vector_search_mode(cls, value: str) -> str:
        mode = value.lower()
        if mode not in _VECTOR_SEARCH_MODES:
            raise ValueError(f"vector_search_mode must be one of {sorted(_VECTOR_SEARCH_MODES)}")
        return mode

    @field_validator("lock_backend")
    @classmethod
    def _validate_lock_backend(cls, value: str) -> str:
        backend = value.lower()
        if backend not in _LOCK_BACKENDS:
            raise ValueError(f"lock_backend must be one of {sorted(_LOCK_BACKENDS)}")
        return backend

    @field_validator("audit_backend")
    @classmethod
    def _validate_audit_backend(cls, value: str) -> str:
        backend = value.lower()
        if backend not in _AUDIT_BACKENDS:
            raise ValueError(f"audit_backend must be one of {sorted(_AUDIT_BACKENDS)}")
        return backend

    @model_validator(mode="after")
    def _validate_production_profile(self) -> "Settings":
        """Fail fast on unsafe production configuration.

        Only enforced when ``app_env == 'production'`` so dev/test (the defaults)
        are unaffected. Deliberately minimal and backward compatible:
        ``AUTH_ENABLED=false`` and the existing JWT-secret rules are still allowed
        in production. The ``cache_backend`` / ``vector_search_mode`` values are
        validated for all environments by the field validators above.
        """
        if not self.is_production:
            return self
        if self.app_debug:
            raise ValueError("APP_DEBUG must be False in production")
        if self.cors_allow_credentials and "*" in self.cors_allowed_origins:
            raise ValueError(
                "Wildcard CORS origin '*' is not allowed in production when "
                "cors_allow_credentials is true"
            )
        # Stage 19.4: refuse to start in production with placeholder secrets, so a
        # forgotten default can never reach a real deployment.
        if self.neo4j_password in _INSECURE_SECRETS:
            raise ValueError("NEO4J_PASSWORD must not be a default/placeholder in production")
        if self.llm_provider == "nvidia" and not self.nvidia_api_key:
            raise ValueError("NVIDIA_API_KEY is required when LLM_PROVIDER=nvidia in production")
        return self

    def redacted(self) -> dict[str, Any]:
        """Settings as a dict with secret-bearing values masked (Stage 19.4).

        Safe to log or expose via a diagnostics endpoint: every secret field and
        every credential embedded in a connection URL is replaced with a masked
        placeholder, so a config dump never leaks a secret.
        """
        out: dict[str, Any] = {}
        for name, value in self.model_dump().items():
            if name in _SECRET_FIELDS:
                out[name] = mask_secret(value)
            elif name in _URL_FIELDS and isinstance(value, str):
                out[name] = redact_url_credentials(value)
            else:
                out[name] = value
        return out


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide cached Settings instance."""
    return Settings()  # type: ignore[call-arg]  # values supplied via environment

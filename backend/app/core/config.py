"""Application configuration — typed, validated, environment-driven.

A single `Settings` object is the source of truth for every runtime knob. It is
loaded once and cached (`get_settings`) so the same immutable instance is shared
process-wide. Values come from environment variables (or a local `.env` in
development); validation fails fast at startup rather than deep inside a request.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, ValidationInfo, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

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
    redis_url: str = Field(..., description="Redis connection URL")
    redis_max_connections: int = 50

    # --- Neo4j -------------------------------------------------------------
    neo4j_uri: str = Field(..., description="Neo4j Bolt URI")
    neo4j_username: str = Field(...)
    neo4j_password: str = Field(...)
    neo4j_database: str = "neo4j"
    neo4j_max_connection_pool_size: int = 50

    # --- LLM providers (optional; no LLM chat calls) ----------------------
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None

    # --- Embeddings -------------------------------------------------------
    # Provider selection: "hash" (deterministic, dependency-free dev default),
    # "openai", or "bge" (local sentence-transformers).
    embedding_provider: str = "hash"
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536

    # --- Knowledge graph --------------------------------------------------
    # Backend: "memory" (offline default) or "neo4j".
    graph_backend: str = "memory"

    # --- Security ----------------------------------------------------------
    jwt_secret: str = Field(..., min_length=16, description="JWT signing secret")
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30

    # --- CORS --------------------------------------------------------------
    cors_allowed_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])

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


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide cached Settings instance."""
    return Settings()  # type: ignore[call-arg]  # values supplied via environment

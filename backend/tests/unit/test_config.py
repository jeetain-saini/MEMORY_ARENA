"""Unit tests for Settings validation (no infrastructure required)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import Settings

_BASE_ENV = {
    "POSTGRES_URL": "postgresql+asyncpg://u:p@localhost:5432/db",
    "REDIS_URL": "redis://localhost:6379/0",
    "NEO4J_URI": "bolt://localhost:7687",
    "NEO4J_USERNAME": "neo4j",
    "NEO4J_PASSWORD": "secret",
    "JWT_SECRET": "a-sufficiently-long-secret",
}


def test_settings_load_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key, value in _BASE_ENV.items():
        monkeypatch.setenv(key, value)
    settings = Settings()  # type: ignore[call-arg]
    assert settings.postgres_url.endswith("/db")
    assert settings.app_env == "development"
    assert settings.docs_enabled is True


def test_log_level_is_normalised(monkeypatch: pytest.MonkeyPatch) -> None:
    for key, value in _BASE_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("LOG_LEVEL", "debug")
    assert Settings().log_level == "DEBUG"  # type: ignore[call-arg]


def test_rejects_template_default_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    for key, value in _BASE_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("JWT_SECRET", "change-me-please")
    with pytest.raises(ValidationError):
        Settings()  # type: ignore[call-arg]


def test_production_disables_docs(monkeypatch: pytest.MonkeyPatch) -> None:
    for key, value in _BASE_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("APP_ENV", "production")
    settings = Settings()  # type: ignore[call-arg]
    assert settings.is_production is True
    assert settings.docs_enabled is False


# --- Stage 14 hardening flags ---------------------------------------------

def test_hardening_flags_default_to_existing_behavior(monkeypatch: pytest.MonkeyPatch) -> None:
    for key, value in _BASE_ENV.items():
        monkeypatch.setenv(key, value)
    settings = Settings()  # type: ignore[call-arg]
    assert settings.auth_enabled is False
    assert settings.rate_limit_enabled is False
    assert settings.cache_backend == "noop"
    assert settings.vector_search_mode == "scan"
    assert settings.cors_allow_credentials is True


def test_cache_backend_is_validated_and_normalised(monkeypatch: pytest.MonkeyPatch) -> None:
    for key, value in _BASE_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("CACHE_BACKEND", "Redis")
    assert Settings().cache_backend == "redis"  # type: ignore[call-arg]


def test_invalid_cache_backend_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    for key, value in _BASE_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("CACHE_BACKEND", "memcached")
    with pytest.raises(ValidationError):
        Settings()  # type: ignore[call-arg]


def test_invalid_vector_search_mode_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    for key, value in _BASE_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("VECTOR_SEARCH_MODE", "annoy")
    with pytest.raises(ValidationError):
        Settings()  # type: ignore[call-arg]


# --- Production profile validation ----------------------------------------

def test_production_rejects_wildcard_cors_with_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    for key, value in _BASE_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", '["*"]')
    with pytest.raises(ValidationError):
        Settings()  # type: ignore[call-arg]


def test_production_allows_wildcard_cors_without_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    for key, value in _BASE_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", '["*"]')
    monkeypatch.setenv("CORS_ALLOW_CREDENTIALS", "false")
    settings = Settings()  # type: ignore[call-arg]
    assert settings.cors_allowed_origins == ["*"]


def test_production_rejects_app_debug(monkeypatch: pytest.MonkeyPatch) -> None:
    for key, value in _BASE_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("APP_DEBUG", "true")
    with pytest.raises(ValidationError):
        Settings()  # type: ignore[call-arg]


def test_production_allows_auth_disabled_with_safe_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    # AUTH_ENABLED=false remains valid in production (backward compatible).
    for key, value in _BASE_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("APP_ENV", "production")
    settings = Settings()  # type: ignore[call-arg]
    assert settings.is_production is True
    assert settings.auth_enabled is False


def test_development_allows_wildcard_cors(monkeypatch: pytest.MonkeyPatch) -> None:
    # Production-only enforcement: development is unaffected.
    for key, value in _BASE_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", '["*"]')
    settings = Settings()  # type: ignore[call-arg]
    assert settings.cors_allowed_origins == ["*"]


# --- Deployment: optional Redis/Neo4j + flags -----------------------------

def test_minimal_env_boots_without_redis_or_neo4j(monkeypatch: pytest.MonkeyPatch) -> None:
    # A free-tier deploy provides only the database URL + JWT secret.
    for key in ("REDIS_URL", "NEO4J_URI", "NEO4J_USERNAME", "NEO4J_PASSWORD"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("POSTGRES_URL", "sqlite+aiosqlite:///./demo.db")
    monkeypatch.setenv("JWT_SECRET", "a-sufficiently-long-secret")
    settings = Settings()  # type: ignore[call-arg]
    assert settings.redis_url.startswith("redis://")     # placeholder default
    assert settings.neo4j_uri.startswith("bolt://")      # placeholder default
    assert settings.is_sqlite is True
    assert settings.auto_create_schema is False
    assert settings.seed_demo_on_startup is False


def test_postgres_url_is_still_required(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in ("POSTGRES_URL", "REDIS_URL", "NEO4J_URI"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("JWT_SECRET", "a-sufficiently-long-secret")
    with pytest.raises(ValidationError):
        Settings()  # type: ignore[call-arg]


def test_deployment_flags_can_be_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    for key, value in _BASE_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("AUTO_CREATE_SCHEMA", "true")
    monkeypatch.setenv("SEED_DEMO_ON_STARTUP", "true")
    settings = Settings()  # type: ignore[call-arg]
    assert settings.auto_create_schema is True
    assert settings.seed_demo_on_startup is True


def test_is_sqlite_false_for_postgres(monkeypatch: pytest.MonkeyPatch) -> None:
    for key, value in _BASE_ENV.items():
        monkeypatch.setenv(key, value)
    assert Settings().is_sqlite is False  # type: ignore[call-arg]  (_BASE_ENV uses postgres URL)

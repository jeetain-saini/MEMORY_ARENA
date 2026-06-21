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

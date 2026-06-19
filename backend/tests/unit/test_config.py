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

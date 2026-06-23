"""Stage 19.4 — secrets management tests.

Proves secret-bearing settings and credentialed URLs are redacted for safe
display, and that production refuses to boot with placeholder secrets.
"""

from __future__ import annotations

import pytest

from app.core.config import Settings, mask_secret, redact_url_credentials

_BASE_ENV = {
    "POSTGRES_URL": "postgresql+asyncpg://u:p@localhost:5432/db",
    "REDIS_URL": "redis://localhost:6379/0",
    "NEO4J_URI": "bolt://localhost:7687",
    "NEO4J_USERNAME": "neo4j",
    "NEO4J_PASSWORD": "a-real-secret",
    "JWT_SECRET": "a-sufficiently-long-secret",
}


def _settings(monkeypatch, **overrides) -> Settings:
    for key, value in {**_BASE_ENV, **overrides}.items():
        monkeypatch.setenv(key, value)
    return Settings()  # type: ignore[call-arg]


# --- helpers ---------------------------------------------------------------

def test_mask_secret_hides_value() -> None:
    assert mask_secret("super-secret") == "***redacted***"
    assert mask_secret(None) is None
    assert mask_secret("") == ""


def test_redact_url_credentials() -> None:
    assert redact_url_credentials(
        "postgresql+asyncpg://user:pass@host:5432/db"
    ) == "postgresql+asyncpg://***:***@host:5432/db"
    # URLs without credentials are unchanged.
    assert redact_url_credentials("redis://localhost:6379/0") == "redis://localhost:6379/0"
    assert redact_url_credentials("bolt://localhost:7687") == "bolt://localhost:7687"


# --- redacted() dump -------------------------------------------------------

def test_redacted_masks_secrets_and_urls(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(monkeypatch, NVIDIA_API_KEY="nvapi-very-secret")
    dump = settings.redacted()

    # Secret fields masked.
    assert dump["jwt_secret"] == "***redacted***"
    assert dump["neo4j_password"] == "***redacted***"
    assert dump["nvidia_api_key"] == "***redacted***"
    # Credentialed URL redacted; credential-free URL untouched.
    assert dump["postgres_url"] == "postgresql+asyncpg://***:***@localhost:5432/db"
    assert dump["redis_url"] == "redis://localhost:6379/0"
    # Non-secret fields pass through.
    assert dump["app_env"] == "development"

    # The real secret never appears anywhere in the dump.
    assert "a-sufficiently-long-secret" not in str(dump)
    assert "nvapi-very-secret" not in str(dump)


# --- production secret validation ------------------------------------------

def test_production_rejects_default_neo4j_password(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValueError):
        _settings(monkeypatch, APP_ENV="production", NEO4J_PASSWORD="neo4j",
                  CORS_ALLOW_CREDENTIALS="false")


def test_production_requires_nvidia_key_when_selected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    with pytest.raises(ValueError):
        _settings(monkeypatch, APP_ENV="production", LLM_PROVIDER="nvidia",
                  CORS_ALLOW_CREDENTIALS="false")


def test_production_boots_with_real_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(
        monkeypatch, APP_ENV="production", NEO4J_PASSWORD="a-real-secret",
        CORS_ALLOW_CREDENTIALS="false",
    )
    assert settings.is_production is True
    # redacted() still hides the secret in production.
    assert settings.redacted()["neo4j_password"] == "***redacted***"

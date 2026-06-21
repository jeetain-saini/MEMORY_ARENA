"""API tests for the /auth endpoints (route mapping + AUTH_ENABLED gating).

The route layer is exercised with a fake AuthService (no DB), focusing on schema
mapping, the standard envelope, error->HTTP mapping, and the feature-flag gate
(404 when AUTH_ENABLED is false). AuthService↔DB behavior is covered separately
in test_auth_service.py.
"""

from __future__ import annotations

import os
from uuid import uuid4

import pytest

os.environ.setdefault("POSTGRES_URL", "postgresql+asyncpg://u:p@localhost:5432/db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("NEO4J_URI", "bolt://localhost:7687")
os.environ.setdefault("NEO4J_USERNAME", "neo4j")
os.environ.setdefault("NEO4J_PASSWORD", "secret")
os.environ.setdefault("JWT_SECRET", "a-sufficiently-long-secret")

from fastapi.testclient import TestClient  # noqa: E402

from app.api.v1.dependencies.providers import get_auth_service  # noqa: E402
from app.application.dto.auth_dto import AuthIdentity, TokenPair  # noqa: E402
from app.application.exceptions import (  # noqa: E402
    AuthenticationError,
    EmailAlreadyRegisteredError,
)
from app.core.config import get_settings  # noqa: E402
from app.main import create_app  # noqa: E402


class _FakeAuthService:
    async def register(self, command):
        if command.email == "dup@example.com":
            raise EmailAlreadyRegisteredError(command.email)
        return AuthIdentity(user_id=uuid4(), email=command.email.lower())

    async def login(self, credentials):
        if credentials.password == "wrong":
            raise AuthenticationError()
        return TokenPair(access_token="acc.tok", refresh_token="ref.tok", expires_in=900)

    async def refresh(self, refresh_token):
        if refresh_token == "bad":
            raise AuthenticationError()
        return TokenPair(access_token="acc.tok2", refresh_token="ref.tok2", expires_in=900)

    async def logout(self, refresh_token):
        return None


def _client(*, auth_enabled: bool, monkeypatch) -> TestClient:
    if auth_enabled:
        monkeypatch.setenv("AUTH_ENABLED", "true")
    else:
        monkeypatch.delenv("AUTH_ENABLED", raising=False)
    get_settings.cache_clear()
    app = create_app()
    app.dependency_overrides[get_auth_service] = lambda: _FakeAuthService()
    return TestClient(app)


@pytest.fixture()
def enabled_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    client = _client(auth_enabled=True, monkeypatch=monkeypatch)
    yield client
    get_settings.cache_clear()


@pytest.fixture()
def disabled_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    client = _client(auth_enabled=False, monkeypatch=monkeypatch)
    yield client
    get_settings.cache_clear()


# --- enabled --------------------------------------------------------------

def test_register_returns_identity(enabled_client: TestClient) -> None:
    resp = enabled_client.post(
        "/api/v1/auth/register", json={"email": "new@example.com", "password": "password123"}
    )
    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["email"] == "new@example.com"
    assert "user_id" in data


def test_register_duplicate_is_409(enabled_client: TestClient) -> None:
    resp = enabled_client.post(
        "/api/v1/auth/register", json={"email": "dup@example.com", "password": "password123"}
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "email_already_registered"


def test_login_returns_token_pair(enabled_client: TestClient) -> None:
    resp = enabled_client.post(
        "/api/v1/auth/login", json={"email": "u@example.com", "password": "password123"}
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["access_token"] and data["refresh_token"]
    assert data["token_type"] == "bearer"
    assert data["expires_in"] == 900


def test_login_bad_credentials_is_401(enabled_client: TestClient) -> None:
    resp = enabled_client.post(
        "/api/v1/auth/login", json={"email": "u@example.com", "password": "wrong"}
    )
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "authentication_error"
    assert resp.headers.get("WWW-Authenticate") == "Bearer"


def test_refresh_returns_new_pair(enabled_client: TestClient) -> None:
    resp = enabled_client.post("/api/v1/auth/refresh", json={"refresh_token": "ref.tok"})
    assert resp.status_code == 200
    assert resp.json()["data"]["access_token"] == "acc.tok2"


def test_refresh_invalid_is_401(enabled_client: TestClient) -> None:
    resp = enabled_client.post("/api/v1/auth/refresh", json={"refresh_token": "bad"})
    assert resp.status_code == 401


def test_logout_ok(enabled_client: TestClient) -> None:
    resp = enabled_client.post("/api/v1/auth/logout", json={"refresh_token": "ref.tok"})
    assert resp.status_code == 200
    assert resp.json()["data"]["logged_out"] is True


def test_register_short_password_is_422(enabled_client: TestClient) -> None:
    resp = enabled_client.post(
        "/api/v1/auth/register", json={"email": "x@example.com", "password": "short"}
    )
    assert resp.status_code == 422


# --- disabled (default) ---------------------------------------------------

def test_endpoints_are_404_when_auth_disabled(disabled_client: TestClient) -> None:
    login = disabled_client.post(
        "/api/v1/auth/login", json={"email": "u@example.com", "password": "password123"}
    )
    register = disabled_client.post(
        "/api/v1/auth/register", json={"email": "u@example.com", "password": "password123"}
    )
    assert login.status_code == 404
    assert register.status_code == 404

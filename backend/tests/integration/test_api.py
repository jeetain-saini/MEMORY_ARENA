"""API endpoint tests using FastAPI's TestClient.

The MemoryService dependency is overridden with an in-memory fake, so these
tests exercise the HTTP layer (routing, validation, envelopes, status codes,
error mapping) without a database. The TestClient is used WITHOUT its context
manager so the app's startup lifespan (which would open real DB connections)
does not run.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest

# Settings require these before the app is constructed.
os.environ.setdefault("POSTGRES_URL", "postgresql+asyncpg://u:p@localhost:5432/db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("NEO4J_URI", "bolt://localhost:7687")
os.environ.setdefault("NEO4J_USERNAME", "neo4j")
os.environ.setdefault("NEO4J_PASSWORD", "secret")
os.environ.setdefault("JWT_SECRET", "a-sufficiently-long-secret")

from fastapi.testclient import TestClient  # noqa: E402

from app.api.v1.dependencies.providers import get_memory_service  # noqa: E402
from app.application.dto.memory_dto import (  # noqa: E402
    CreateMemoryRequest,
    CreateMemoryResponse,
    MemorySearchRequest,
    UpdateMemoryRequest,
)
from app.application.exceptions import MemoryNotFoundException  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.domain.value_objects.memory_status import MemoryStatus  # noqa: E402
from app.domain.value_objects.memory_type import MemoryType  # noqa: E402
from app.main import create_app  # noqa: E402


class FakeMemoryService:
    """In-memory stand-in for MemoryService (no DB, no events)."""

    def __init__(self) -> None:
        self._store: dict[UUID, CreateMemoryResponse] = {}

    def _make(self, user_id, content, memory_type, version=1) -> CreateMemoryResponse:
        now = datetime.now(timezone.utc)
        return CreateMemoryResponse(
            id=uuid4(), user_id=user_id, content=content, memory_type=memory_type,
            status=MemoryStatus.ACTIVE, total_score=0.475, version=version,
            is_promoted=False, created_at=now, updated_at=now,
        )

    async def create(self, request: CreateMemoryRequest) -> CreateMemoryResponse:
        resp = self._make(request.user_id, request.content, request.memory_type)
        self._store[resp.id] = resp
        return resp

    async def get_by_id(self, memory_id: UUID) -> CreateMemoryResponse:
        if memory_id not in self._store:
            raise MemoryNotFoundException(memory_id)
        return self._store[memory_id]

    async def update(self, request: UpdateMemoryRequest) -> CreateMemoryResponse:
        existing = self._store.get(request.memory_id)
        if existing is None:
            raise MemoryNotFoundException(request.memory_id)
        updated = self._make(
            existing.user_id, request.content or existing.content, existing.memory_type, version=2
        )
        updated = updated.__class__(**{**updated.__dict__, "id": request.memory_id})
        self._store[request.memory_id] = updated
        return updated

    async def delete(self, *, memory_id: UUID, user_id: UUID) -> None:
        if memory_id not in self._store:
            raise MemoryNotFoundException(memory_id)
        del self._store[memory_id]

    async def search(self, request: MemorySearchRequest) -> list[CreateMemoryResponse]:
        return [m for m in self._store.values() if m.user_id == request.user_id]

    async def list_by_user(self, user_id: UUID, *, limit=20, offset=0) -> list[CreateMemoryResponse]:
        return [m for m in self._store.values() if m.user_id == user_id]


@pytest.fixture()
def client() -> TestClient:
    get_settings.cache_clear()
    app = create_app()
    fake = FakeMemoryService()
    app.dependency_overrides[get_memory_service] = lambda: fake
    return TestClient(app)


def test_create_returns_201_envelope(client: TestClient) -> None:
    body = {"user_id": str(uuid4()), "content": "remember this", "memory_type": "fact"}
    resp = client.post("/api/v1/memories", json=body)
    assert resp.status_code == 201
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["content"] == "remember this"
    assert data["data"]["memory_type"] == "fact"


def test_create_validation_error_returns_422(client: TestClient) -> None:
    body = {"user_id": str(uuid4()), "content": "   ", "memory_type": "fact"}
    resp = client.post("/api/v1/memories", json=body)
    assert resp.status_code == 422
    assert resp.json()["success"] is False


def test_create_invalid_enum_returns_422(client: TestClient) -> None:
    body = {"user_id": str(uuid4()), "content": "ok", "memory_type": "not_a_type"}
    resp = client.post("/api/v1/memories", json=body)
    assert resp.status_code == 422


def test_get_roundtrip_and_not_found(client: TestClient) -> None:
    created = client.post(
        "/api/v1/memories",
        json={"user_id": str(uuid4()), "content": "x", "memory_type": "goal"},
    ).json()["data"]

    ok = client.get(f"/api/v1/memories/{created['id']}")
    assert ok.status_code == 200
    assert ok.json()["data"]["id"] == created["id"]

    missing = client.get(f"/api/v1/memories/{uuid4()}")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "memory_not_found"


def test_update_memory(client: TestClient) -> None:
    user_id = str(uuid4())
    created = client.post(
        "/api/v1/memories", json={"user_id": user_id, "content": "v1", "memory_type": "fact"}
    ).json()["data"]

    resp = client.put(
        f"/api/v1/memories/{created['id']}", json={"user_id": user_id, "content": "v2"}
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["content"] == "v2"
    assert resp.json()["data"]["version"] == 2


def test_update_requires_a_field(client: TestClient) -> None:
    resp = client.put(f"/api/v1/memories/{uuid4()}", json={"user_id": str(uuid4())})
    assert resp.status_code == 422


def test_delete_memory(client: TestClient) -> None:
    user_id = str(uuid4())
    created = client.post(
        "/api/v1/memories", json={"user_id": user_id, "content": "bye", "memory_type": "fact"}
    ).json()["data"]

    resp = client.delete(f"/api/v1/memories/{created['id']}", params={"user_id": user_id})
    assert resp.status_code == 200
    assert resp.json()["data"]["deleted"] is True


def test_search_and_list(client: TestClient) -> None:
    user_id = str(uuid4())
    client.post(
        "/api/v1/memories", json={"user_id": user_id, "content": "a", "memory_type": "fact"}
    )
    search = client.post("/api/v1/memories/search", json={"user_id": user_id})
    assert search.status_code == 200
    assert len(search.json()["data"]) == 1

    listed = client.get(f"/api/v1/memories/user/{user_id}")
    assert listed.status_code == 200
    assert len(listed.json()["data"]) == 1

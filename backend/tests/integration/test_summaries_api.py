"""API tests for the summary read endpoints (fake service; no DB)."""

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

from app.api.v1.dependencies.providers import get_summary_service  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.domain.entities.memory_summary import MemorySummary  # noqa: E402
from app.domain.value_objects.memory_type import MemoryType  # noqa: E402
from app.main import create_app  # noqa: E402

USER_ID = uuid4()


def _summary(scope: MemoryType, text: str) -> MemorySummary:
    return MemorySummary.create(
        user_id=USER_ID, scope=scope, summary_text=text, source_memory_ids=[uuid4()]
    )


class FakeSummaryService:
    def __init__(self) -> None:
        self._store = {
            MemoryType.PROJECT: _summary(MemoryType.PROJECT, "project summary"),
            MemoryType.GOAL: _summary(MemoryType.GOAL, "goal summary"),
        }

    async def list_for_user(self, user_id):
        return list(self._store.values())

    async def get(self, user_id, scope: MemoryType):
        return self._store.get(scope)


@pytest.fixture()
def client() -> TestClient:
    get_settings.cache_clear()
    app = create_app()
    app.dependency_overrides[get_summary_service] = lambda: FakeSummaryService()
    return TestClient(app)


def test_list_summaries(client: TestClient) -> None:
    resp = client.get(f"/api/v1/summaries/{USER_ID}")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data) == 2
    assert {d["scope"] for d in data} == {"project", "goal"}


def test_list_serialization_shape(client: TestClient) -> None:
    resp = client.get(f"/api/v1/summaries/{USER_ID}")
    summary = resp.json()["data"][0]
    assert set(summary) == {
        "id",
        "user_id",
        "scope",
        "summary_text",
        "source_memory_ids",
        "source_count",
        "version",
        "created_at",
        "updated_at",
    }
    assert summary["source_count"] == len(summary["source_memory_ids"])


def test_list_filtered_by_scope_query(client: TestClient) -> None:
    resp = client.get(f"/api/v1/summaries/{USER_ID}", params={"scope": "project"})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data) == 1
    assert data[0]["scope"] == "project"


def test_list_filtered_by_missing_scope_is_empty(client: TestClient) -> None:
    resp = client.get(f"/api/v1/summaries/{USER_ID}", params={"scope": "experience"})
    assert resp.status_code == 200
    assert resp.json()["data"] == []


def test_get_summary_by_scope(client: TestClient) -> None:
    resp = client.get(f"/api/v1/summaries/{USER_ID}/goal")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["scope"] == "goal"
    assert data["summary_text"] == "goal summary"


def test_get_summary_missing_scope_is_404(client: TestClient) -> None:
    resp = client.get(f"/api/v1/summaries/{USER_ID}/experience")
    assert resp.status_code == 404
    body = resp.json()
    assert body["success"] is False
    assert body["error"]["code"] == "summary_not_found"


def test_invalid_scope_is_422(client: TestClient) -> None:
    resp = client.get(f"/api/v1/summaries/{USER_ID}/not_a_scope")
    assert resp.status_code == 422

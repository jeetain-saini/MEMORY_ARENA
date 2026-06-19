"""API tests for POST /api/v1/ingest (fake processor; no DB, no LLM)."""

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

from app.api.v1.dependencies.providers import get_workflow_processor  # noqa: E402
from app.application.interfaces.workflow_job_processor import WorkflowJob  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.main import create_app  # noqa: E402


class _SpyProcessor:
    def __init__(self) -> None:
        self.jobs: list[WorkflowJob] = []

    async def submit(self, job: WorkflowJob) -> None:
        self.jobs.append(job)


@pytest.fixture()
def spy() -> _SpyProcessor:
    return _SpyProcessor()


@pytest.fixture()
def client(spy: _SpyProcessor) -> TestClient:
    get_settings.cache_clear()
    app = create_app()
    app.dependency_overrides[get_workflow_processor] = lambda: spy
    return TestClient(app)


def test_ingest_returns_202_and_queued(client: TestClient, spy: _SpyProcessor) -> None:
    user_id = str(uuid4())
    resp = client.post("/api/v1/ingest", json={"user_id": user_id, "text": "I prefer dark mode."})
    assert resp.status_code == 202
    data = resp.json()["data"]
    assert data["status"] == "queued"
    assert data["job_id"]
    # The job was enqueued with the request payload.
    assert len(spy.jobs) == 1
    assert str(spy.jobs[0].user_id) == user_id
    assert spy.jobs[0].raw_text == "I prefer dark mode."


def test_ingest_empty_text_is_422(client: TestClient, spy: _SpyProcessor) -> None:
    resp = client.post("/api/v1/ingest", json={"user_id": str(uuid4()), "text": ""})
    assert resp.status_code == 422
    assert spy.jobs == []


def test_ingest_invalid_user_id_is_422(client: TestClient) -> None:
    resp = client.post("/api/v1/ingest", json={"user_id": "not-a-uuid", "text": "hello world"})
    assert resp.status_code == 422


def test_ingest_missing_text_is_422(client: TestClient) -> None:
    resp = client.post("/api/v1/ingest", json={"user_id": str(uuid4())})
    assert resp.status_code == 422

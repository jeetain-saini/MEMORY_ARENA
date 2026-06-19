"""API tests for the Memory Intelligence endpoints (fakes; no DB)."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest

os.environ.setdefault("POSTGRES_URL", "postgresql+asyncpg://u:p@localhost:5432/db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("NEO4J_URI", "bolt://localhost:7687")
os.environ.setdefault("NEO4J_USERNAME", "neo4j")
os.environ.setdefault("NEO4J_PASSWORD", "secret")
os.environ.setdefault("JWT_SECRET", "a-sufficiently-long-secret")

from fastapi.testclient import TestClient  # noqa: E402

from app.api.v1.dependencies.providers import (  # noqa: E402
    get_memory_analytics_service,
    get_memory_intelligence_service,
)
from app.application.dto.analytics_dto import MemoryAnalytics  # noqa: E402
from app.application.dto.memory_dto import CreateMemoryResponse  # noqa: E402
from app.application.exceptions import (  # noqa: E402
    MemoryNotFoundException,
    MemoryValidationException,
)
from app.core.config import get_settings  # noqa: E402
from app.domain.exceptions.errors import InvalidMemoryStateError  # noqa: E402
from app.domain.value_objects.memory_status import MemoryStatus  # noqa: E402
from app.domain.value_objects.memory_type import MemoryType  # noqa: E402
from app.main import create_app  # noqa: E402


def _response(memory_id: UUID, *, status=MemoryStatus.ACTIVE, promoted=False, priority=0):
    now = datetime.now(timezone.utc)
    return CreateMemoryResponse(
        id=memory_id, user_id=uuid4(), content="x", memory_type=MemoryType.FACT,
        status=status, total_score=0.5, version=1, is_promoted=promoted,
        priority=priority, created_at=now, updated_at=now,
    )


class FakeIntelligence:
    def __init__(self) -> None:
        self.missing: UUID | None = None
        self.promote_fails = False
        self.archive_not_eligible = False

    async def reinforce_memory(self, memory_id, *, user_id=None, step=None):
        if memory_id == self.missing:
            raise MemoryNotFoundException(memory_id)
        return _response(memory_id)

    async def promote_memory(self, memory_id, *, user_id=None):
        if self.promote_fails:
            raise InvalidMemoryStateError("below threshold")
        return _response(memory_id, promoted=True, priority=1)

    async def archive_memory(self, memory_id, *, user_id=None, force=False, now=None):
        if self.archive_not_eligible and not force:
            raise MemoryValidationException("not eligible")
        return _response(memory_id, status=MemoryStatus.ARCHIVED)


class FakeAnalytics:
    async def get_analytics(self, user_id=None):
        return MemoryAnalytics(
            total_memories=3, active_memories=2, archived_memories=1,
            promoted_memories=1, average_score=0.5,
            score_distribution={"0.0-0.2": 0, "0.4-0.6": 3},
        )


@pytest.fixture()
def setup():
    get_settings.cache_clear()
    app = create_app()
    intel = FakeIntelligence()
    app.dependency_overrides[get_memory_intelligence_service] = lambda: intel
    app.dependency_overrides[get_memory_analytics_service] = lambda: FakeAnalytics()
    return TestClient(app), intel


def test_reinforce_endpoint(setup) -> None:
    client, _ = setup
    resp = client.post(f"/api/v1/memories/{uuid4()}/reinforce", params={"user_id": str(uuid4())})
    assert resp.status_code == 200
    assert resp.json()["success"] is True


def test_reinforce_not_found(setup) -> None:
    client, intel = setup
    mid = uuid4()
    intel.missing = mid
    resp = client.post(f"/api/v1/memories/{mid}/reinforce", params={"user_id": str(uuid4())})
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "memory_not_found"


def test_promote_endpoint(setup) -> None:
    client, _ = setup
    resp = client.post(f"/api/v1/memories/{uuid4()}/promote", params={"user_id": str(uuid4())})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["is_promoted"] is True
    assert data["priority"] == 1


def test_promote_below_threshold_returns_409(setup) -> None:
    client, intel = setup
    intel.promote_fails = True
    resp = client.post(f"/api/v1/memories/{uuid4()}/promote", params={"user_id": str(uuid4())})
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "invalid_memory_state"


def test_archive_endpoint(setup) -> None:
    client, _ = setup
    resp = client.post(f"/api/v1/memories/{uuid4()}/archive", params={"user_id": str(uuid4())})
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "archived"


def test_archive_not_eligible_returns_422(setup) -> None:
    client, intel = setup
    intel.archive_not_eligible = True
    resp = client.post(f"/api/v1/memories/{uuid4()}/archive", params={"user_id": str(uuid4())})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "memory_validation_error"


def test_analytics_endpoint(setup) -> None:
    client, _ = setup
    resp = client.get("/api/v1/memories/analytics")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total_memories"] == 3
    assert data["promoted_memories"] == 1
    assert "score_distribution" in data

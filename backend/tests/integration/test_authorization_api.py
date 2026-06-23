"""API-level authorization tests (Stage 14 Phase 3).

Covers, through the real HTTP stack:
* explicit user_id mismatch -> 403 across every protected user-scoped endpoint
  (the parametrized matrix doubles as the coverage check),
* cross-user by-id graph access -> 404 (and owner -> 200),
* missing token under AUTH_ENABLED=true -> 401.

A principal override simulates an authenticated owner; scope checks run before any
datastore access, so no live DB is needed for the 403 matrix.
"""

from __future__ import annotations

import asyncio
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

from app.api.v1.dependencies.providers import (  # noqa: E402
    get_current_principal,
    get_graph_repository,
    get_unit_of_work,
    get_workflow_processor,
)
from app.application.dto.auth_dto import AuthPrincipal  # noqa: E402
from app.application.dto.graph_dto import GraphNode, NodeType  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.infrastructure.database.session import create_session_factory  # noqa: E402
from app.infrastructure.database.unit_of_work import SQLAlchemyUnitOfWork  # noqa: E402
from app.infrastructure.graph.in_memory_graph_repository import InMemoryGraphRepository  # noqa: E402
from app.main import create_app  # noqa: E402
from tests.integration._db import make_engine  # noqa: E402

OWNER = uuid4()
OTHER = uuid4()
OWNER_MEM = uuid4()
OTHER_MEM = uuid4()

# SQLite factory for service construction only (never entered: scope checks fire
# first), so the matrix needs no live database.
_ENGINE = asyncio.run(make_engine())
_FACTORY = create_session_factory(_ENGINE)


class _FakeWorkflowProcessor:
    async def submit(self, job) -> None:
        self.job = job


def _graph_repo() -> InMemoryGraphRepository:
    repo = InMemoryGraphRepository()

    async def seed() -> None:
        await repo.create_node(
            GraphNode(node_id=str(OWNER_MEM), node_type=NodeType.MEMORY, label="o",
                      properties={"user_id": str(OWNER)})
        )
        await repo.create_node(
            GraphNode(node_id=str(OTHER_MEM), node_type=NodeType.MEMORY, label="x",
                      properties={"user_id": str(OTHER)})
        )

    asyncio.run(seed())
    return repo


def _client(principal: AuthPrincipal | None) -> TestClient:
    get_settings.cache_clear()
    app = create_app()
    app.dependency_overrides[get_current_principal] = lambda: principal
    app.dependency_overrides[get_unit_of_work] = lambda: SQLAlchemyUnitOfWork(_FACTORY)
    app.dependency_overrides[get_workflow_processor] = lambda: _FakeWorkflowProcessor()
    repo = _graph_repo()
    app.dependency_overrides[get_graph_repository] = lambda: repo
    return TestClient(app)


@pytest.fixture()
def owner_client() -> TestClient:
    return _client(AuthPrincipal(user_id=OWNER, tenant_id=OWNER))


# Protected endpoints carrying an explicit OTHER user_id -> must be 403.
# (method, url, json-body) — the OTHER scope is the cross-user attempt.
_MISMATCH_MATRIX = [
    ("POST", "/api/v1/memories", {"user_id": str(OTHER), "content": "x", "memory_type": "fact"}),
    ("POST", "/api/v1/memories/search", {"user_id": str(OTHER), "query": "x"}),
    ("GET", f"/api/v1/memories/user/{OTHER}", None),
    ("GET", f"/api/v1/memories/analytics?user_id={OTHER}", None),
    ("GET", f"/api/v1/memories/health?user_id={OTHER}", None),
    ("POST", "/api/v1/retrieval/debug", {"user_id": str(OTHER), "query": "x"}),
    ("POST", "/api/v1/retrieval/search", {"user_id": str(OTHER), "query": "x"}),
    ("POST", "/api/v1/context/debug", {"user_id": str(OTHER), "query": "x"}),
    ("POST", "/api/v1/context/build", {"user_id": str(OTHER), "query": "x"}),
    ("POST", "/api/v1/graph/search", {"user_id": str(OTHER), "query": "x"}),
    ("POST", "/api/v1/graph/debug", {"user_id": str(OTHER), "query": "x"}),
    ("POST", "/api/v1/query", {"user_id": str(OTHER), "query": "x"}),
    ("POST", "/api/v1/query/stream", {"user_id": str(OTHER), "query": "x"}),
    ("POST", "/api/v1/ingest", {"user_id": str(OTHER), "text": "hello world"}),
    ("GET", f"/api/v1/summaries/{OTHER}", None),
    ("GET", f"/api/v1/summaries/{OTHER}/project", None),
    ("GET", f"/api/v1/observability/traces?user_id={OTHER}", None),
]


@pytest.mark.parametrize("method,url,body", _MISMATCH_MATRIX)
def test_cross_user_scope_is_forbidden(owner_client: TestClient, method: str, url: str, body) -> None:
    resp = owner_client.request(method, url, json=body)
    assert resp.status_code == 403, f"{method} {url} -> {resp.status_code}"
    assert resp.json()["error"]["code"] == "authorization_error"


def test_owner_scope_is_allowed_for_graph_by_id(owner_client: TestClient) -> None:
    # The owner's own memory node resolves (200); another user's -> 404.
    ok = owner_client.get(f"/api/v1/graph/memory/{OWNER_MEM}")
    assert ok.status_code == 200
    nope = owner_client.get(f"/api/v1/graph/memory/{OTHER_MEM}")
    assert nope.status_code == 404


def test_traverse_other_users_node_is_404(owner_client: TestClient) -> None:
    resp = owner_client.post("/api/v1/graph/traverse", json={"node_id": str(OTHER_MEM), "depth": 1})
    assert resp.status_code == 404


def test_traverse_own_node_ok(owner_client: TestClient) -> None:
    resp = owner_client.post("/api/v1/graph/traverse", json={"node_id": str(OWNER_MEM), "depth": 1})
    assert resp.status_code == 200


# --- 401 under real auth (no principal override) ---------------------------

@pytest.fixture()
def auth_enabled_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("AUTH_ENABLED", "true")
    get_settings.cache_clear()
    app = create_app()
    # No principal override: the real get_current_principal runs (missing token).
    app.dependency_overrides[get_unit_of_work] = lambda: SQLAlchemyUnitOfWork(_FACTORY)
    yield TestClient(app)
    get_settings.cache_clear()


def test_missing_token_is_401(auth_enabled_client: TestClient) -> None:
    for url, body in (
        (f"/api/v1/memories/user/{OWNER}", None),
        ("/api/v1/query", {"user_id": str(OWNER), "query": "x"}),
    ):
        resp = auth_enabled_client.request("POST" if body else "GET", url, json=body)
        assert resp.status_code == 401, f"{url} -> {resp.status_code}"


# --- coverage check --------------------------------------------------------

def test_every_protected_route_is_covered() -> None:
    """Guard against a newly-added protected route escaping the matrix above."""
    app = create_app()
    protected_prefixes = (
        "/api/v1/memories", "/api/v1/retrieval", "/api/v1/context", "/api/v1/graph",
        "/api/v1/query", "/api/v1/ingest", "/api/v1/summaries", "/api/v1/observability",
    )
    open_paths = {
        "/api/v1/memories/{memory_id}",          # by-id: covered at service level
        "/api/v1/graph/memory/{memory_id}",      # by-id: covered above
        "/api/v1/graph/traverse",                # by-id: covered above
        # Aggregate, non-user-scoped operational endpoints (no user_id; expose
        # only process-wide counters/latencies) — like /health, not user-scoped.
        "/api/v1/observability/metrics",
        "/api/v1/observability/prometheus",  # Phase 4: Prometheus scrape target
    }
    discovered = {
        route.path
        for route in app.routes
        if getattr(route, "path", "").startswith(protected_prefixes)
    }
    tested = {url.split("?")[0] for _m, url, _b in _MISMATCH_MATRIX}
    # Normalize parametrized paths in the matrix to their templates.
    tested |= {
        "/api/v1/memories/user/{user_id}", "/api/v1/memories/analytics",
        "/api/v1/memories/health", "/api/v1/summaries/{user_id}",
        "/api/v1/summaries/{user_id}/{scope}", "/api/v1/observability/traces",
        # Stage 16: route-level authorize_owner on the path user_id.
        "/api/v1/graph/overview/{user_id}",
    }
    tested |= open_paths
    # Intelligence + by-id mutate routes are covered at the service level.
    service_level = {
        "/api/v1/memories/{memory_id}/reinforce", "/api/v1/memories/{memory_id}/promote",
        "/api/v1/memories/{memory_id}/archive",
        # Stage 16: service-level authorize_owner (restore on the memory's owner;
        # resolve validates ownership of both keep_id and archive_id).
        "/api/v1/memories/{memory_id}/restore",
        "/api/v1/memories/contradictions/resolve",
        # Stage 17: intelligence engines authorize_owner on the path user_id.
        "/api/v1/intelligence/promote/{user_id}",
        "/api/v1/intelligence/forget/{user_id}",
        "/api/v1/intelligence/cluster/{user_id}",
    }
    tested |= service_level
    uncovered = {
        p for p in discovered
        if p not in tested and not p.endswith(("/search", "/build", "/debug"))
        and p not in {
            "/api/v1/memories", "/api/v1/memories/search", "/api/v1/retrieval/search",
            "/api/v1/retrieval/debug", "/api/v1/context/build", "/api/v1/context/debug",
            "/api/v1/graph/search", "/api/v1/graph/debug", "/api/v1/query",
            "/api/v1/query/stream", "/api/v1/ingest",
        }
    }
    assert uncovered == set(), f"protected routes missing authorization coverage: {uncovered}"

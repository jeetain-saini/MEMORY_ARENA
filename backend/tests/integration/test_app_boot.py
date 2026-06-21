"""Full-app boot on the free-tier profile: SQLite + in-memory graph, no Neo4j.

Runs the real lifespan (TestClient as a context manager) against a file SQLite
with AUTO_CREATE_SCHEMA, confirming the app starts without Neo4j/Redis, creates
the schema, and serves DB-backed + liveness endpoints — i.e. a single Render
instance boots end-to-end. The process-wide event dispatcher is snapshotted and
restored so this does not leak handler registrations into other tests.
"""

from __future__ import annotations

import os
from uuid import uuid4

os.environ.setdefault("POSTGRES_URL", "postgresql+asyncpg://u:p@localhost:5432/db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("NEO4J_URI", "bolt://localhost:7687")
os.environ.setdefault("NEO4J_USERNAME", "neo4j")
os.environ.setdefault("NEO4J_PASSWORD", "secret")
os.environ.setdefault("JWT_SECRET", "a-sufficiently-long-secret")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.infrastructure.events.in_process_dispatcher import in_process_dispatcher  # noqa: E402
from app.main import create_app  # noqa: E402


@pytest.fixture()
def isolate_dispatcher():
    saved = {k: list(v) for k, v in in_process_dispatcher._handlers.items()}
    yield
    in_process_dispatcher._handlers.clear()
    in_process_dispatcher._handlers.update(saved)


def test_app_boots_on_sqlite_without_neo4j(
    isolate_dispatcher, tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = (tmp_path / "boot.db").as_posix()
    monkeypatch.setenv("POSTGRES_URL", f"sqlite+aiosqlite:///{db}")
    monkeypatch.setenv("AUTO_CREATE_SCHEMA", "true")
    monkeypatch.setenv("GRAPH_BACKEND", "memory")
    monkeypatch.delenv("SEED_DEMO_ON_STARTUP", raising=False)
    get_settings.cache_clear()
    try:
        app = create_app()
        # Context-manager form runs the full startup + shutdown lifespan.
        with TestClient(app) as client:
            # Liveness (always 200; what Render's health check should target).
            assert client.get("/api/v1/version").status_code == 200
            # DB-backed read works -> schema was auto-created, sessions reach SQLite.
            resp = client.get(f"/api/v1/memories/user/{uuid4()}")
            assert resp.status_code == 200
            assert resp.json()["data"] == []
    finally:
        get_settings.cache_clear()

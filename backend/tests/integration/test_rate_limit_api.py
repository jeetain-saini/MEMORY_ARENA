"""API tests for rate limiting (Stage 14 Phase 4).

Exercises the router-level dependency end-to-end with an in-memory limiter +
FrozenClock (deterministic windows): 429 + Retry-After, success headers, window
reset, auth-vs-anon keying, exempt routes, single-consumption on /query/stream,
a coverage guard, and backward compatibility when disabled.
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

from app.api.v1.dependencies.providers import get_query_use_case  # noqa: E402
from app.api.v1.dependencies.ratelimit import (  # noqa: E402
    enforce_rate_limit,
    get_rate_limit_config,
    get_rate_limiter,
)
from app.application.dto.agent_dto import AgentStreamEvent  # noqa: E402
from app.application.services.observability.frozen_clock import FrozenClock  # noqa: E402
from app.application.services.ratelimit.config import RateLimitConfig  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.infrastructure.observability.monotonic_clock import MonotonicClock  # noqa: E402
from app.infrastructure.ratelimit.in_memory_limiter import InMemoryRateLimiter  # noqa: E402
from app.infrastructure.security.jwt_token_service import JwtTokenService  # noqa: E402
from app.main import create_app  # noqa: E402

# Small limits for fast, deterministic assertions.
_TEST_CONFIG = RateLimitConfig(window_seconds=60, default_auth=3, default_anon=2, query_anon=1)


class _FakeQuery:
    async def execute(self, request):  # pragma: no cover - not used by stream tests
        raise NotImplementedError

    def stream(self, request):
        async def gen():
            yield AgentStreamEvent(event="step", data={"i": 1})
            yield AgentStreamEvent(event="answer", data={"answer": "x"})
            yield AgentStreamEvent(event="done", data={"finish_reason": "completed"})

        return gen()


def _client(*, enabled: bool, clock: FrozenClock | None = None) -> TestClient:
    clock = clock or FrozenClock(epoch=1000.0)
    if enabled:
        os.environ["RATE_LIMIT_ENABLED"] = "true"
    else:
        os.environ.pop("RATE_LIMIT_ENABLED", None)
    get_settings.cache_clear()
    app = create_app()
    limiter = InMemoryRateLimiter(clock)
    app.dependency_overrides[get_rate_limiter] = lambda: limiter
    app.dependency_overrides[get_rate_limit_config] = lambda: _TEST_CONFIG
    app.dependency_overrides[get_query_use_case] = lambda: _FakeQuery()
    client = TestClient(app)
    client._clock = clock  # type: ignore[attr-defined]
    return client


@pytest.fixture()
def enabled() -> TestClient:
    client = _client(enabled=True)
    yield client
    os.environ.pop("RATE_LIMIT_ENABLED", None)
    get_settings.cache_clear()


# --- default tier: allow then 429 -----------------------------------------

def test_allows_up_to_limit_then_429(enabled: TestClient) -> None:
    r1 = enabled.get("/api/v1/observability/traces")
    r2 = enabled.get("/api/v1/observability/traces")
    r3 = enabled.get("/api/v1/observability/traces")
    assert r1.status_code == 200 and r2.status_code == 200
    assert r3.status_code == 429
    assert r3.json()["error"]["code"] == "rate_limited"
    assert int(r3.headers["Retry-After"]) > 0


def test_success_emits_ratelimit_headers(enabled: TestClient) -> None:
    r = enabled.get("/api/v1/observability/traces")
    assert r.headers["X-RateLimit-Limit"] == "2"
    assert r.headers["X-RateLimit-Remaining"] == "1"
    assert int(r.headers["X-RateLimit-Reset"]) == 1020  # (floor(1000/60)+1)*60


def test_window_reset_allows_again(enabled: TestClient) -> None:
    enabled.get("/api/v1/observability/traces")
    enabled.get("/api/v1/observability/traces")
    assert enabled.get("/api/v1/observability/traces").status_code == 429
    enabled._clock.advance(60)  # next window  # type: ignore[attr-defined]
    assert enabled.get("/api/v1/observability/traces").status_code == 200


def test_auth_and_anon_keyed_independently(enabled: TestClient) -> None:
    # Exhaust the anonymous (per-IP) bucket.
    enabled.get("/api/v1/observability/traces")
    enabled.get("/api/v1/observability/traces")
    assert enabled.get("/api/v1/observability/traces").status_code == 429
    # A valid token -> separate per-user bucket, unaffected by the anon exhaustion.
    token = JwtTokenService(
        secret="a-sufficiently-long-secret", algorithm="HS256",
        access_ttl_seconds=900, clock=MonotonicClock(),
    ).issue_access(uuid4())
    r = enabled.get("/api/v1/observability/traces", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.headers["X-RateLimit-Limit"] == "3"  # default_auth


# --- exempt ---------------------------------------------------------------

def test_health_is_never_throttled(enabled: TestClient) -> None:
    for _ in range(10):
        resp = enabled.get("/api/v1/health")
        assert resp.status_code in (200, 503)  # never 429
        assert "X-RateLimit-Limit" not in resp.headers


# --- streaming consumes quota exactly once --------------------------------

def test_query_stream_consumes_quota_once(enabled: TestClient) -> None:
    # query_anon limit is 1: one full stream request succeeds, emitting many SSE
    # events, and consumes exactly one unit of quota (the limiter runs once before
    # the stream begins) — so the very next request is blocked. If quota were
    # consumed per event/chunk, a single multi-event stream could not have
    # succeeded at limit 1.
    first = enabled.post("/api/v1/query/stream", json={"user_id": str(uuid4()), "query": "x"})
    assert first.status_code == 200
    assert first.text.count("event:") >= 3  # multiple SSE events in this one request
    second = enabled.post("/api/v1/query/stream", json={"user_id": str(uuid4()), "query": "x"})
    assert second.status_code == 429
    assert int(second.headers["Retry-After"]) > 0


def test_streaming_429_before_body(enabled: TestClient) -> None:
    # A blocked stream returns a clean 429 (JSON), not a partial event stream.
    enabled.post("/api/v1/query/stream", json={"user_id": str(uuid4()), "query": "x"})  # consume the 1
    blocked = enabled.post("/api/v1/query/stream", json={"user_id": str(uuid4()), "query": "x"})
    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "rate_limited"


# --- backward compatibility ----------------------------------------------

def test_disabled_never_throttles() -> None:
    client = _client(enabled=False)
    try:
        for _ in range(10):
            resp = client.get("/api/v1/observability/traces")
            assert resp.status_code == 200
            assert "X-RateLimit-Limit" not in resp.headers
    finally:
        get_settings.cache_clear()


# --- coverage guard -------------------------------------------------------

def _dependency_calls(dependant) -> list:
    calls = []
    for dep in dependant.dependencies:
        calls.append(dep.call)
        calls.extend(_dependency_calls(dep))
    return calls


def test_every_v1_route_is_rate_limit_covered() -> None:
    app = create_app()
    cfg = RateLimitConfig()
    uncovered = []
    for route in app.routes:
        path = getattr(route, "path", "")
        if not path.startswith("/api/v1"):
            continue
        if enforce_rate_limit not in _dependency_calls(route.dependant):
            uncovered.append(path)
    assert uncovered == [], f"routes missing rate-limit coverage: {uncovered}"
    # Exempt routes are explicitly declared (the dependency no-ops for them).
    assert "/api/v1/health" in cfg.exempt_prefixes
    assert "/api/v1/version" in cfg.exempt_prefixes

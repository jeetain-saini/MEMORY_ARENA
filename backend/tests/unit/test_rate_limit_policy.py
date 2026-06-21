"""Unit tests for rate-limit policy resolution (pure)."""

from __future__ import annotations

from app.application.services.ratelimit.config import RateLimitConfig
from app.application.services.ratelimit.policy import is_exempt, limit_for, resolve_policy

_CFG = RateLimitConfig()


def test_exempt_paths() -> None:
    assert is_exempt("/api/v1/health", _CFG) is True
    assert is_exempt("/api/v1/version", _CFG) is True
    assert is_exempt("/api/v1/memories", _CFG) is False
    assert is_exempt("/api/v1/query", _CFG) is False


def test_tier_resolution() -> None:
    assert resolve_policy("/api/v1/auth/login", _CFG).tier == "auth"
    assert resolve_policy("/api/v1/query", _CFG).tier == "query"
    assert resolve_policy("/api/v1/query/stream", _CFG).tier == "query"
    assert resolve_policy("/api/v1/ingest", _CFG).tier == "ingest"
    assert resolve_policy("/api/v1/memories", _CFG).tier == "default"


def test_auth_tier_uses_strict_anon_limit() -> None:
    policy = resolve_policy("/api/v1/auth/login", _CFG)
    assert policy.anon_limit == _CFG.auth_endpoints_anon  # 5
    assert policy.auth_limit == _CFG.default_auth


def test_query_tier_limits() -> None:
    policy = resolve_policy("/api/v1/query", _CFG)
    assert policy.auth_limit == _CFG.query_auth   # 20
    assert policy.anon_limit == _CFG.query_anon   # 5


def test_limit_for_selects_auth_or_anon() -> None:
    policy = resolve_policy("/api/v1/query", _CFG)
    assert limit_for(policy, authenticated=True) == _CFG.query_auth
    assert limit_for(policy, authenticated=False) == _CFG.query_anon

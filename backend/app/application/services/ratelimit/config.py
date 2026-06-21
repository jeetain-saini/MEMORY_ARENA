"""RateLimitConfig — the tunable limits + exemptions (framework-free).

Built from Settings at the composition root and passed to the pure policy
functions. Limits are requests-per-window; identity (auth vs anon) selects the
applicable number at the edge.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class RateLimitConfig:
    window_seconds: int = 60
    default_auth: int = 120
    default_anon: int = 30
    auth_endpoints_anon: int = 5
    query_auth: int = 20
    query_anon: int = 5
    ingest_auth: int = 30
    # Paths exempt from rate limiting (orchestrator probes, version).
    exempt_prefixes: tuple[str, ...] = ("/api/v1/health", "/api/v1/version")
    trust_forwarded_for: bool = False

    # Tier path prefixes (kept here so the coverage guard can introspect them).
    auth_prefix: str = "/api/v1/auth"
    query_prefix: str = "/api/v1/query"
    ingest_prefix: str = "/api/v1/ingest"
    api_prefix: str = "/api/v1"

"""Rate-limit policy resolution — pure functions over a path + config.

Maps a request path to its tier (and the auth/anon limits for that tier) and
decides exemption. No framework imports; the API dependency calls these.
"""

from __future__ import annotations

from app.application.dto.ratelimit_dto import RateLimitPolicy
from app.application.services.ratelimit.config import RateLimitConfig


def is_exempt(path: str, config: RateLimitConfig) -> bool:
    return any(path.startswith(prefix) for prefix in config.exempt_prefixes)


def resolve_policy(path: str, config: RateLimitConfig) -> RateLimitPolicy:
    """Return the tier policy for ``path`` (call only for non-exempt paths)."""
    window = config.window_seconds
    if path.startswith(config.auth_prefix):
        # Auth endpoints are anonymous (login/register): the anon limit is the
        # brute-force guard; an authenticated caller falls back to the generous default.
        return RateLimitPolicy("auth", config.default_auth, config.auth_endpoints_anon, window)
    if path.startswith(config.query_prefix):
        return RateLimitPolicy("query", config.query_auth, config.query_anon, window)
    if path.startswith(config.ingest_prefix):
        return RateLimitPolicy("ingest", config.ingest_auth, config.default_anon, window)
    return RateLimitPolicy("default", config.default_auth, config.default_anon, window)


def limit_for(policy: RateLimitPolicy, *, authenticated: bool) -> int:
    return policy.auth_limit if authenticated else policy.anon_limit

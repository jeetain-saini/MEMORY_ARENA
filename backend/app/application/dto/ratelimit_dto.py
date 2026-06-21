"""Rate-limiting DTOs (Stage 14 Phase 4).

Framework-free dataclasses: the decision a ``RateLimiter`` returns for one hit,
and the policy (limits + window) applied to a request tier. No Redis, no FastAPI.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RateLimitDecision:
    """Outcome of counting one request against a window."""

    allowed: bool
    limit: int
    remaining: int
    retry_after_seconds: int   # 0 when allowed
    reset_epoch: int           # wall-clock epoch second the window resets


@dataclass(frozen=True)
class RateLimitPolicy:
    """The limits for a request tier; the dependency picks auth vs anon."""

    tier: str
    auth_limit: int
    anon_limit: int
    window_seconds: int

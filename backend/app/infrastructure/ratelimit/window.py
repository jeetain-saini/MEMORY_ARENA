"""Shared fixed-window math so every adapter produces identical decisions.

A window is identified by ``bucket = floor(now_epoch / window)``; it resets at
``(bucket + 1) * window`` (the single source of truth for both ``reset_epoch``
and ``retry_after``). Keeping this here guarantees the in-memory and Redis
adapters satisfy the same contract.
"""

from __future__ import annotations

from app.application.dto.ratelimit_dto import RateLimitDecision


def current_bucket(now_epoch: float, window_seconds: int) -> int:
    return int(now_epoch // window_seconds)


def build_decision(
    *, count: int, limit: int, now_epoch: float, window_seconds: int
) -> RateLimitDecision:
    reset_epoch = (current_bucket(now_epoch, window_seconds) + 1) * window_seconds
    allowed = count <= limit
    remaining = max(0, limit - count)
    retry_after = 0 if allowed else max(0, int(reset_epoch - now_epoch))
    return RateLimitDecision(
        allowed=allowed,
        limit=limit,
        remaining=remaining,
        retry_after_seconds=retry_after,
        reset_epoch=int(reset_epoch),
    )

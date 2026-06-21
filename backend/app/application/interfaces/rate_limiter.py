"""RateLimiter port — counts requests against a limit/window.

Deliberately generic: it counts a *key* against a *limit* over a *window* and
returns a decision. Which key/limit/window applies to a given request is policy
(resolved at the API edge), not the limiter's concern — so a fixed-window
counter today can be swapped for token-bucket or sliding-window later behind the
same contract without touching callers.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.application.dto.ratelimit_dto import RateLimitDecision


class RateLimiter(ABC):
    @abstractmethod
    async def hit(self, key: str, *, limit: int, window_seconds: int) -> RateLimitDecision:
        """Atomically count one hit on ``key`` and return the resulting decision."""

"""RefreshTokenStore port — server-side state for rotating refresh tokens.

Refresh tokens are opaque; this store is the source of truth for their validity,
rotation status, and family revocation. The rotation step is exposed as a single
**atomic** operation, ``consume_for_rotation``, rather than a race-prone
get -> check -> mark sequence: it must, in one step, classify the token and (only
when VALID) mark it consumed. Adapters realize the atomicity differently
(in-memory: single-threaded mutation; Redis: a server-side script), but the
application consumes one contract.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.application.dto.auth_dto import RefreshRecord, RotationOutcome


class RefreshTokenStore(ABC):
    @abstractmethod
    async def save(self, record: RefreshRecord) -> None:
        """Persist a freshly issued, active refresh-token record."""

    @abstractmethod
    async def consume_for_rotation(self, token_id: str) -> RotationOutcome:
        """Atomically classify ``token_id`` and, if VALID, mark it rotated.

        Returns one of VALID / ROTATED / REVOKED / EXPIRED / NOT_FOUND. A ROTATED
        result means the token was already consumed — i.e. reuse/replay — and the
        caller should revoke the family.
        """

    @abstractmethod
    async def revoke_family(self, family_id: str) -> None:
        """Revoke every token in a family (logout, or reuse detected)."""

    @abstractmethod
    async def family_of(self, token_id: str) -> str | None:
        """Return the family id for a token, or None (used by logout)."""

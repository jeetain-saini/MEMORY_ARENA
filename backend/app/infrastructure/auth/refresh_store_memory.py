"""InMemoryRefreshTokenStore — deterministic, process-local refresh store.

Used in tests (and local dev). ``consume_for_rotation`` is atomic by virtue of
the single-threaded asyncio model: it performs no ``await`` between reading and
mutating the record, so no interleaving can occur. Expiry is evaluated against
the injected clock, so a ``FrozenClock`` makes expiry deterministic.
"""

from __future__ import annotations

from dataclasses import replace

from app.application.dto.auth_dto import (
    RefreshRecord,
    RotationOutcome,
    RotationState,
)
from app.application.interfaces.clock import Clock
from app.application.interfaces.refresh_token_store import RefreshTokenStore


class InMemoryRefreshTokenStore(RefreshTokenStore):
    def __init__(self, clock: Clock) -> None:
        self._clock = clock
        self._records: dict[str, RefreshRecord] = {}
        self._revoked_families: set[str] = set()

    async def save(self, record: RefreshRecord) -> None:
        self._records[record.token_id] = record

    async def consume_for_rotation(self, token_id: str) -> RotationOutcome:
        record = self._records.get(token_id)
        if record is None:
            return RotationOutcome(RotationState.NOT_FOUND)
        if record.family_id in self._revoked_families:
            return RotationOutcome(RotationState.REVOKED, family_id=record.family_id)
        if self._clock.now_epoch() >= record.expires_at:
            return RotationOutcome(RotationState.EXPIRED, family_id=record.family_id)
        if record.status == "rotated":
            # Already consumed -> reuse/replay.
            return RotationOutcome(
                RotationState.ROTATED, user_id=record.user_id, family_id=record.family_id
            )
        # Consume atomically (no await between the checks above and this write).
        self._records[token_id] = replace(record, status="rotated")
        return RotationOutcome(
            RotationState.VALID, user_id=record.user_id, family_id=record.family_id
        )

    async def revoke_family(self, family_id: str) -> None:
        self._revoked_families.add(family_id)

    async def family_of(self, token_id: str) -> str | None:
        record = self._records.get(token_id)
        return record.family_id if record is not None else None

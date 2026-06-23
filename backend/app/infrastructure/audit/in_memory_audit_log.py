"""InMemoryAuditLog — process-local audit trail (offline/dev default, tests).

Keeps a bounded, in-order list of entries per tenant. Process-local and not
durable — the Postgres adapter is the production system of record — but it
implements the same contract so the audit handler and any admin query behave
identically regardless of which adapter is wired in.
"""

from __future__ import annotations

from collections import defaultdict
from uuid import UUID

from app.application.dto.audit_dto import AuditEntry
from app.application.interfaces.audit_log import AuditLog


class InMemoryAuditLog(AuditLog):
    def __init__(self, *, cap_per_user: int = 1000) -> None:
        self._by_user: dict[UUID, list[AuditEntry]] = defaultdict(list)
        self._anonymous: list[AuditEntry] = []
        self._cap = cap_per_user

    async def record(self, entry: AuditEntry) -> None:
        bucket = self._anonymous if entry.user_id is None else self._by_user[entry.user_id]
        bucket.append(entry)
        if len(bucket) > self._cap:
            del bucket[0 : len(bucket) - self._cap]

    async def list_for_user(self, user_id: UUID, *, limit: int = 100) -> list[AuditEntry]:
        return list(reversed(self._by_user.get(user_id, [])))[:limit]

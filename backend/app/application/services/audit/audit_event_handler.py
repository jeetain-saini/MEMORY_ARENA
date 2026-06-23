"""AuditEventHandler — turns every domain event into an audit entry (Stage 19.3).

Registers a single catch-all handler on the base ``DomainEvent``: the dispatcher
walks each event's MRO, so one registration captures *every* memory write,
lifecycle transition (archived/forgotten/superseded/deleted), and intelligence
action (promoted/reinforced/decayed/conflict). The handler maps the event's
fields onto an :class:`AuditEntry` and appends it through the :class:`AuditLog`
port. Dispatcher handler failures are already isolated/logged, so a slow or
failing audit sink never breaks the audited operation.

Intelligence/auth actions that are not domain events (e.g. a manual
``/intelligence/promote`` endpoint call) can audit directly via the port; this
handler covers everything that flows through the event system.
"""

from __future__ import annotations

from uuid import UUID

from app.application.dto.audit_dto import AuditEntry
from app.application.interfaces.audit_log import AuditLog
from app.application.interfaces.event_dispatcher import EventDispatcher
from app.domain.events.memory_events import DomainEvent

# Event fields that identify the affected resource, in priority order.
_RESOURCE_KEYS = ("memory_id", "memory_id_a", "superseded_by_id")
# Fields that are not audit metadata (carried as dedicated columns or noise).
_SKIP_METADATA = {"event_id", "occurred_at", "user_id", *_RESOURCE_KEYS}


class AuditEventHandler:
    def __init__(self, audit_log: AuditLog) -> None:
        self._audit = audit_log

    def register(self, dispatcher: EventDispatcher) -> None:
        # One registration on the base type = catch-all (dispatcher walks the MRO).
        dispatcher.register(DomainEvent, self.on_event)

    async def on_event(self, event: DomainEvent) -> None:
        await self._audit.record(self._to_entry(event))

    @staticmethod
    def _to_entry(event: DomainEvent) -> AuditEntry:
        fields = vars(event)
        resource_id: UUID | None = next(
            (fields[k] for k in _RESOURCE_KEYS if fields.get(k) is not None), None
        )
        metadata = {
            k: (str(v) if isinstance(v, UUID) else v)
            for k, v in fields.items()
            if k not in _SKIP_METADATA and v is not None
        }
        return AuditEntry(
            action=type(event).__name__,
            resource_type="memory",
            user_id=fields.get("user_id"),
            resource_id=resource_id,
            metadata=metadata,
            occurred_at=event.occurred_at,
        )

"""Evidence Engine (Phase C) — append-only memory evidence & evolution.

Every inferred memory carries an *evidence record* that answers "why do I
believe this, since when, and how has it changed?". It lives inside the memory's
existing JSONB ``metadata`` under :data:`EVIDENCE_KEY` — so there is **no schema
migration** and existing memories degrade gracefully (absent == empty history).

Core rule: evidence is *append-only*. Reinforcement appends a new observation
and never overwrites prior confidence / importance / reason history.

Pure and framework-free (no DB, no LLM) → fully unit-testable.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

EVIDENCE_KEY = "evidence"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Evidence:
    first_seen: str
    last_seen: str
    created_from_message: str
    latest_message: str
    source_type: str  # "semantic" | "deterministic"
    evidence_count: int = 1
    reinforcement_count: int = 0
    conversation_ids: list[str] = field(default_factory=list)
    message_ids: list[str] = field(default_factory=list)
    confidence_history: list[float] = field(default_factory=list)
    importance_history: list[float] = field(default_factory=list)
    reason_history: list[str] = field(default_factory=list)
    topic_history: list[str] = field(default_factory=list)
    progression_history: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Evidence":
        fields = {f for f in cls.__dataclass_fields__}  # noqa: C416
        return cls(**{k: v for k, v in data.items() if k in fields})


def new_evidence(
    *,
    message: str,
    confidence: float,
    importance: float,
    reason: str,
    source_type: str,
    topic: str | None = None,
    progression_stage: str | None = None,
    conversation_id: str | None = None,
    message_id: str | None = None,
) -> dict[str, Any]:
    """Build the initial evidence record for a freshly inferred memory."""
    now = _now()
    ev = Evidence(
        first_seen=now,
        last_seen=now,
        created_from_message=message,
        latest_message=message,
        source_type=source_type,
        confidence_history=[round(float(confidence), 4)],
        importance_history=[round(float(importance), 4)],
        reason_history=[reason] if reason else [],
        topic_history=[topic] if topic else [],
        progression_history=[progression_stage] if progression_stage else [],
        conversation_ids=[conversation_id] if conversation_id else [],
        message_ids=[message_id] if message_id else [],
    )
    return ev.to_dict()


def append_evidence(
    existing: dict[str, Any] | None,
    *,
    message: str,
    confidence: float,
    importance: float,
    reason: str,
    source_type: str,
    topic: str | None = None,
    progression_stage: str | None = None,
    conversation_id: str | None = None,
    message_id: str | None = None,
) -> dict[str, Any]:
    """Append an observation to existing evidence (or create it). Append-only:
    prior history is never mutated or lost."""
    if not existing:
        return new_evidence(
            message=message, confidence=confidence, importance=importance, reason=reason,
            source_type=source_type, topic=topic, progression_stage=progression_stage,
            conversation_id=conversation_id, message_id=message_id,
        )
    ev = Evidence.from_dict(existing)
    ev.last_seen = _now()
    ev.latest_message = message
    ev.evidence_count += 1
    ev.reinforcement_count += 1
    ev.confidence_history.append(round(float(confidence), 4))
    ev.importance_history.append(round(float(importance), 4))
    if reason:
        ev.reason_history.append(reason)
    if topic:
        ev.topic_history.append(topic)
    if progression_stage and progression_stage not in ev.progression_history:
        ev.progression_history.append(progression_stage)
    if conversation_id and conversation_id not in ev.conversation_ids:
        ev.conversation_ids.append(conversation_id)
    if message_id and message_id not in ev.message_ids:
        ev.message_ids.append(message_id)
    return ev.to_dict()


# --- derived, read-only analytics (real stored data only) ------------------
def current_confidence(evidence: dict[str, Any]) -> float | None:
    hist = (evidence or {}).get("confidence_history") or []
    return float(hist[-1]) if hist else None


def timeline(evidence: dict[str, Any]) -> list[dict[str, Any]]:
    """Chronological events derived from the stored histories."""
    ev = evidence or {}
    events: list[dict[str, Any]] = []
    if ev.get("first_seen"):
        events.append({"at": ev["first_seen"], "event": "created", "detail": ev.get("created_from_message", "")})
    for stage in ev.get("progression_history", [])[1:]:
        events.append({"at": ev.get("last_seen"), "event": "progressed", "detail": stage})
    if (ev.get("reinforcement_count") or 0) > 0:
        events.append({"at": ev.get("last_seen"), "event": "reinforced",
                       "detail": f"{ev['reinforcement_count']} reinforcement(s)"})
    return events


def health(evidence: dict[str, Any]) -> dict[str, Any]:
    """Memory-health metrics computed purely from stored evidence."""
    ev = evidence or {}
    conf = current_confidence(ev) or 0.0
    imp_hist = ev.get("importance_history") or []
    reinforcements = int(ev.get("reinforcement_count") or 0)
    prog = ev.get("progression_history") or []
    days_since = _days_since(ev.get("last_seen"))
    return {
        "confidence": round(conf, 3),
        "importance": round(float(imp_hist[-1]) if imp_hist else 0.0, 3),
        # Stability: rises with reinforcement count (settled after ~5 mentions).
        "stability": round(min(1.0, reinforcements / 5.0), 3),
        # Freshness: 1.0 today, decaying ~1 month half-life.
        "freshness": round(max(0.0, 1.0 - (days_since / 30.0)) if days_since is not None else 0.0, 3),
        "activity": int(ev.get("evidence_count") or 0),
        "reinforcement_score": reinforcements,
        "evolution_stage": prog[-1] if prog else "initial",
    }


def _days_since(iso: str | None) -> float | None:
    if not iso:
        return None
    try:
        then = datetime.fromisoformat(iso)
        if then.tzinfo is None:
            then = then.replace(tzinfo=timezone.utc)
        return max(0.0, (datetime.now(timezone.utc) - then).total_seconds() / 86400.0)
    except ValueError:
        return None

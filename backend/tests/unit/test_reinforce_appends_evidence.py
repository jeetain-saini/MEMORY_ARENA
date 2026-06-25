"""Phase C.2: reinforcing a memory appends (never overwrites) evidence."""

from __future__ import annotations

import asyncio
import uuid

from app.application.services.inference.evidence import EVIDENCE_KEY, new_evidence
from app.application.services.memory_intelligence_service import MemoryIntelligenceService
from app.domain.entities.memory import Memory
from app.domain.value_objects.memory_type import MemoryType


class _FakeRepo:
    def __init__(self, memory: Memory):
        self._m = memory

    async def get_by_id(self, memory_id):
        return self._m

    async def update(self, memory):
        self._m = memory
        return memory


class _FakeUoW:
    def __init__(self, memory: Memory):
        self.memories = _FakeRepo(memory)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def commit(self):
        pass


class _FakeDispatcher:
    async def dispatch(self, events):
        pass


def _make_memory() -> Memory:
    m = Memory.create(
        user_id=uuid.uuid4(),
        content="Uses Rust",
        memory_type=MemoryType.SKILL,
        metadata={
            "inference_topic": "Rust",
            "progression_stage": "uses",
            EVIDENCE_KEY: new_evidence(
                message="I built a Rust API.", confidence=0.6, importance=0.5,
                reason="uses", source_type="semantic", topic="Rust", progression_stage="uses",
            ),
        },
    )
    return m


def test_reinforce_appends_evidence_append_only() -> None:
    memory = _make_memory()
    uow = _FakeUoW(memory)
    before = memory.metadata[EVIDENCE_KEY]
    first_seen = before["first_seen"]
    conf_len = len(before["confidence_history"])

    svc = MemoryIntelligenceService(uow=uow, dispatcher=_FakeDispatcher())
    asyncio.run(svc.reinforce_memory(memory.id))

    ev = uow.memories._m.metadata[EVIDENCE_KEY]
    # Appended, not overwritten.
    assert ev["first_seen"] == first_seen          # never modified
    assert ev["reinforcement_count"] == 1
    assert ev["evidence_count"] == 2
    assert len(ev["confidence_history"]) == conf_len + 1   # history grew
    assert ev["last_seen"] >= first_seen

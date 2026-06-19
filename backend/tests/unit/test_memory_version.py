"""Domain tests for MemoryVersion — snapshots and rollback."""

from __future__ import annotations

from uuid import uuid4

from app.domain.entities.memory import Memory
from app.domain.entities.memory_version import MemoryVersion
from app.domain.value_objects.memory_type import MemoryType


def _new_memory() -> Memory:
    return Memory.create(
        user_id=uuid4(),
        content="Original content.",
        memory_type=MemoryType.FACT,
    )


def test_capture_snapshots_current_state() -> None:
    memory = _new_memory()
    version = MemoryVersion.capture(memory, reason="pre-edit")
    assert version.memory_id == memory.id
    assert version.version_number == memory.version
    assert version.content == "Original content."
    assert version.reason == "pre-edit"


def test_snapshot_is_decoupled_from_later_edits() -> None:
    memory = _new_memory()
    version = MemoryVersion.capture(memory)
    memory.update_content("Edited content.")
    # The captured snapshot must not change when the memory does.
    assert version.content == "Original content."
    assert memory.content == "Edited content."


def test_rollback_restores_previous_state() -> None:
    memory = _new_memory()
    snapshot = MemoryVersion.capture(memory)
    memory.update_content("Edited content.")
    assert memory.content == "Edited content."

    memory.rollback_to(snapshot)
    assert memory.content == "Original content."
    # Rollback advances the version counter (it is itself a change).
    assert memory.version == 3


def test_metadata_snapshot_is_a_copy() -> None:
    memory = _new_memory()
    memory.metadata["k"] = "v1"
    version = MemoryVersion.capture(memory)
    memory.metadata["k"] = "v2"
    assert version.metadata["k"] == "v1"

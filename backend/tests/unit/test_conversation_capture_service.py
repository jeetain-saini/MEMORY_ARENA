"""Unit tests for ConversationCaptureService (Stage 15)."""

from __future__ import annotations

import asyncio
from uuid import uuid4

from app.application.interfaces.workflow_job_processor import WorkflowJob, WorkflowJobProcessor
from app.application.services.agent.conversation_capture_policy import ConversationCapturePolicy
from app.application.services.agent.conversation_capture_service import (
    ConversationCaptureService,
)


class _FakeProcessor(WorkflowJobProcessor):
    def __init__(self, raise_on_submit: bool = False) -> None:
        self.jobs: list[WorkflowJob] = []
        self._raise = raise_on_submit

    async def submit(self, job: WorkflowJob) -> None:
        if self._raise:
            raise RuntimeError("queue full")
        self.jobs.append(job)


def _svc(processor, enabled=True):
    return ConversationCaptureService(processor, ConversationCapturePolicy(), enabled=enabled)


def test_enabled_and_worthy_submits_job() -> None:
    proc = _FakeProcessor()
    uid = uuid4()
    out = asyncio.run(_svc(proc).maybe_capture(uid, "My name is Jeetain."))
    assert out is True
    assert len(proc.jobs) == 1
    assert proc.jobs[0].user_id == uid
    assert proc.jobs[0].raw_text == "My name is Jeetain."
    assert proc.jobs[0].metadata.get("source") == "conversation"


def test_disabled_does_not_submit() -> None:
    proc = _FakeProcessor()
    out = asyncio.run(_svc(proc, enabled=False).maybe_capture(uuid4(), "My name is Jeetain."))
    assert out is False
    assert proc.jobs == []


def test_policy_rejected_does_not_submit() -> None:
    # Policy-rejected AND non-inferrable (unknown topic) -> still dropped.
    proc = _FakeProcessor()
    out = asyncio.run(_svc(proc).maybe_capture(uuid4(), "What is the weather today?"))
    assert out is False
    assert proc.jobs == []


def test_inferrable_question_is_captured() -> None:
    # Phase A: a question about a known technology is captured via inference,
    # even though the capture policy alone would reject it as a question.
    proc = _FakeProcessor()
    out = asyncio.run(_svc(proc).maybe_capture(uuid4(), "What is FastAPI?"))
    assert out is True
    assert len(proc.jobs) == 1


def test_submit_failure_is_isolated() -> None:
    proc = _FakeProcessor(raise_on_submit=True)
    # Must not raise; returns False.
    out = asyncio.run(_svc(proc).maybe_capture(uuid4(), "I prefer dark mode."))
    assert out is False


def test_schedule_fire_and_forget_submits() -> None:
    proc = _FakeProcessor()
    uid = uuid4()

    async def scenario() -> None:
        _svc(proc).schedule(uid, "I am learning LangGraph.")
        # let the scheduled task run
        await asyncio.sleep(0)
        await asyncio.sleep(0)

    asyncio.run(scenario())
    assert len(proc.jobs) == 1
    assert proc.jobs[0].user_id == uid


def test_schedule_disabled_noop() -> None:
    proc = _FakeProcessor()

    async def scenario() -> None:
        _svc(proc, enabled=False).schedule(uuid4(), "I prefer dark mode.")
        await asyncio.sleep(0)

    asyncio.run(scenario())
    assert proc.jobs == []

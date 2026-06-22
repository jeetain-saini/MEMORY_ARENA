"""ConversationCaptureService — turn an agent conversation turn into a memory.

When enabled, a user's query is run through the lightweight capture policy and,
if it passes, submitted as a ``WorkflowJob`` to the existing ingestion processor
(the same one ``/ingest`` uses). Extraction, the single write path, embeddings,
graph sync, and consolidation then run off the request path — no new pipeline.

Failure-isolated: submission errors are logged and swallowed so conversational
capture can never break ``/query`` or ``/query/stream``. ``maybe_capture`` is for
the awaited (non-stream) path; ``schedule`` fire-and-forgets for the sync stream
path. Memory creation itself always happens asynchronously on the processor.
"""

from __future__ import annotations

import asyncio
import logging
from uuid import UUID, uuid4

from app.application.interfaces.workflow_job_processor import (
    WorkflowJob,
    WorkflowJobProcessor,
)
from app.application.services.agent.conversation_capture_policy import (
    ConversationCapturePolicy,
)

_logger = logging.getLogger("memoryarena.capture")


class ConversationCaptureService:
    def __init__(
        self,
        processor: WorkflowJobProcessor,
        policy: ConversationCapturePolicy,
        *,
        enabled: bool,
    ) -> None:
        self._processor = processor
        self._policy = policy
        self._enabled = enabled

    async def maybe_capture(self, user_id: UUID, text: str) -> bool:
        """Submit a capture job if enabled and the policy accepts the turn.

        Returns True iff a job was submitted. Never raises.
        """
        if not self._enabled or not self._policy.should_capture(text):
            return False
        try:
            await self._processor.submit(
                WorkflowJob(
                    job_id=uuid4(),
                    user_id=user_id,
                    raw_text=text,
                    metadata={"source": "conversation"},
                )
            )
            return True
        except Exception:  # noqa: BLE001 — capture must never break the response
            _logger.warning("capture.submit_failed", exc_info=True)
            return False

    def schedule(self, user_id: UUID, text: str) -> None:
        """Fire-and-forget capture for the synchronous stream path."""
        if not self._enabled:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return  # no running loop (e.g. outside a request) — skip silently
        loop.create_task(self.maybe_capture(user_id, text))

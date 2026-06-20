"""LLMContextCompressor — summarize memories into a budget-fitting context.

Implements the ``ContextCompressor`` port using an ``LLMProvider``. The flow:

    generate -> validate -> accept | fall back to heuristic

The LLM response is accepted only if it passes every check in
``compression_validation`` (parse, token budget, required sections,
contradiction preservation, goal preservation). On *any* failure — a raised
provider error, an empty/oversized response, a dropped contradiction or goal —
it delegates to the injected ``HeuristicContextCompressor`` fallback, so context
generation can never fail or exceed budget because of the LLM.

Provenance is preserved on the accepted path: the returned ``CompressionResult``
carries the original ``ContextMemory`` objects (with their ``memory_id`` and
``memory_type``); nothing is dropped, so removed is empty. Conflict and
consolidation records are produced upstream by the builder and are unaffected.
"""

from __future__ import annotations

import logging

from app.application.dto.context_dto import (
    CompressionResult,
    CompressionStats,
    ContextMemory,
)
from app.application.interfaces.context_compressor import ContextCompressor
from app.application.interfaces.llm_provider import LLMProvider
from app.application.interfaces.token_counter import TokenCounter
from app.infrastructure.llm.compressors.compression_prompts import (
    COMPRESSION_SYSTEM_PROMPT,
    build_compression_prompt,
)
from app.infrastructure.llm.compressors.compression_validation import (
    validate_llm_output,
)

logger = logging.getLogger(__name__)


class LLMContextCompressor(ContextCompressor):
    def __init__(
        self,
        provider: LLMProvider,
        token_counter: TokenCounter,
        fallback: ContextCompressor,
    ) -> None:
        self._provider = provider
        self._counter = token_counter
        self._fallback = fallback

    async def compress(
        self, memories: list[ContextMemory], max_tokens: int
    ) -> CompressionResult:
        if not memories:
            return CompressionResult(
                memories=[],
                context_text="",
                stats=CompressionStats(
                    original_tokens=0, compressed_tokens=0, ratio=1.0, removed_memories=0
                ),
                removed=[],
            )

        try:
            prompt = build_compression_prompt(memories, max_tokens)
            raw = await self._provider.generate(prompt, system=COMPRESSION_SYSTEM_PROMPT)
        except Exception:  # noqa: BLE001 — provider failure must never propagate
            logger.warning("LLM compression provider failed; using heuristic fallback", exc_info=True)
            return await self._fallback.compress(memories, max_tokens)

        context_text = (raw or "").strip()
        validation = validate_llm_output(memories, context_text, max_tokens, self._counter)
        if not validation.ok:
            logger.info("LLM compression rejected (%s); using heuristic fallback", validation.reason)
            return await self._fallback.compress(memories, max_tokens)

        compressed_tokens = self._counter.count(context_text)
        original_tokens = sum(m.tokens for m in memories)
        ratio = round(compressed_tokens / original_tokens, 4) if original_tokens else 1.0
        return CompressionResult(
            memories=list(memories),
            context_text=context_text,
            stats=CompressionStats(
                original_tokens=original_tokens,
                compressed_tokens=compressed_tokens,
                ratio=ratio,
                removed_memories=0,
            ),
            removed=[],
        )

"""Context compressor factory.

``CONTEXT_COMPRESSOR`` selects the context-assembly compressor:
  * ``heuristic`` -> HeuristicContextCompressor (offline default; dev/tests)
  * ``llm``       -> LLMContextCompressor (LLM summarization + validation;
                     falls back to the heuristic on any failure)

Cached as a process-wide singleton (mirrors the embedding/LLM provider
factories); call ``build_context_compressor.cache_clear()`` in tests that change
configuration.
"""

from __future__ import annotations

from functools import lru_cache

from app.application.interfaces.context_compressor import ContextCompressor
from app.application.services.context.compressor import HeuristicContextCompressor
from app.application.services.context.tokenization import HeuristicTokenCounter
from app.core.config import get_settings


@lru_cache(maxsize=1)
def build_context_compressor() -> ContextCompressor:
    settings = get_settings()
    counter = HeuristicTokenCounter()
    heuristic = HeuristicContextCompressor(counter)
    if settings.context_compressor.lower() == "llm":
        from app.infrastructure.llm.compressors.llm_compressor import LLMContextCompressor
        from app.infrastructure.llm.providers.factory import build_llm_provider

        return LLMContextCompressor(build_llm_provider(), counter, fallback=heuristic)
    return heuristic

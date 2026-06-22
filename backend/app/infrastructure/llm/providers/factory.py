"""LLM provider factories — answer generation vs memory extraction.

Two independent provider selections so the two concerns can be decoupled:

  * ``build_llm_provider``            — answer generation (``LLM_PROVIDER``)
  * ``build_extraction_llm_provider`` — memory extraction (``EXTRACTION_LLM_PROVIDER``)

Each accepts the same choices:
  * ``deterministic`` -> DeterministicLLMProvider (offline, rule-based; no cost)
  * ``openai``        -> OpenAIProvider
  * ``anthropic``     -> AnthropicProvider
  * ``nvidia``        -> NvidiaProvider (NVIDIA NIM via ChatNVIDIA)

Extraction defaults to ``deterministic`` so memory capture stays free and works
even when the answer provider's quota is exhausted. Both are cached singletons;
call ``build_*.cache_clear()`` in tests that change configuration.
"""

from __future__ import annotations

from functools import lru_cache

from app.application.interfaces.llm_provider import LLMProvider
from app.core.config import Settings, get_settings
from app.infrastructure.llm.providers.anthropic_provider import AnthropicProvider
from app.infrastructure.llm.providers.deterministic_provider import DeterministicLLMProvider
from app.infrastructure.llm.providers.nvidia_provider import NvidiaProvider
from app.infrastructure.llm.providers.openai_provider import OpenAIProvider


def _select_provider(choice: str, settings: Settings) -> LLMProvider:
    choice = choice.lower()
    if choice == "openai":
        return OpenAIProvider(api_key=settings.openai_api_key, model=settings.llm_model)
    if choice == "anthropic":
        return AnthropicProvider(api_key=settings.anthropic_api_key, model=settings.llm_model)
    if choice == "nvidia":
        return NvidiaProvider(api_key=settings.nvidia_api_key, model=settings.llm_model)
    return DeterministicLLMProvider()


@lru_cache(maxsize=1)
def build_llm_provider() -> LLMProvider:
    """Provider for answer generation (the query-time agent)."""
    settings = get_settings()
    return _select_provider(settings.llm_provider, settings)


@lru_cache(maxsize=1)
def build_extraction_llm_provider() -> LLMProvider:
    """Provider for memory extraction (ingestion + conversational capture).

    Defaults to the deterministic, rule-based provider so extraction is local,
    free, and unaffected by the answer provider's rate limits.
    """
    settings = get_settings()
    return _select_provider(settings.extraction_llm_provider, settings)

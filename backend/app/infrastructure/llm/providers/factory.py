"""LLM provider factory — selects the implementation from configuration.

``LLM_PROVIDER`` chooses the adapter:
  * ``deterministic`` -> DeterministicLLMProvider (offline default; dev/tests)
  * ``openai``        -> OpenAIProvider
  * ``anthropic``     -> AnthropicProvider
  * ``nvidia``        -> NvidiaProvider (NVIDIA NIM via ChatNVIDIA)

Cached as a process-wide singleton (mirrors the embedding provider factory).
Call ``build_llm_provider.cache_clear()`` in tests that change configuration.
"""

from __future__ import annotations

from functools import lru_cache

from app.application.interfaces.llm_provider import LLMProvider
from app.core.config import get_settings
from app.infrastructure.llm.providers.anthropic_provider import AnthropicProvider
from app.infrastructure.llm.providers.deterministic_provider import DeterministicLLMProvider
from app.infrastructure.llm.providers.nvidia_provider import NvidiaProvider
from app.infrastructure.llm.providers.openai_provider import OpenAIProvider


@lru_cache(maxsize=1)
def build_llm_provider() -> LLMProvider:
    settings = get_settings()
    choice = settings.llm_provider.lower()
    if choice == "openai":
        return OpenAIProvider(api_key=settings.openai_api_key, model=settings.llm_model)
    if choice == "anthropic":
        return AnthropicProvider(api_key=settings.anthropic_api_key, model=settings.llm_model)
    if choice == "nvidia":
        return NvidiaProvider(api_key=settings.nvidia_api_key, model=settings.llm_model)
    return DeterministicLLMProvider()

"""Workflow and consolidation engine factories.

``WORKFLOW_ENGINE`` chooses the extraction implementation:
  * ``sequential`` -> SequentialExtractionEngine (offline default; dev/tests)
  * ``langgraph``  -> LangGraphExtractionEngine (production; needs ``langgraph``)

``CONSOLIDATION_ENGINE`` chooses the consolidation implementation:
  * ``sequential`` -> SequentialConsolidationEngine (offline default; dev/tests)
  * ``langgraph``  -> LangGraphConsolidationEngine (production; needs ``langgraph``)

Both factories are cached as process-wide singletons; call
``build_*_engine.cache_clear()`` in tests that change configuration.
"""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING

from app.application.interfaces.consolidation_engine import ConsolidationEngine
from app.application.interfaces.workflow_engine import WorkflowEngine
from app.core.config import get_settings
from app.infrastructure.llm.graphs.sequential_consolidation_engine import (
    SequentialConsolidationEngine,
)
from app.infrastructure.llm.graphs.sequential_engine import SequentialExtractionEngine
from app.infrastructure.llm.providers.factory import build_extraction_llm_provider

if TYPE_CHECKING:
    from app.application.interfaces.agent_runtime import AgentRuntime
    from app.application.interfaces.clock import Clock
    from app.application.interfaces.llm_provider import LLMProvider
    from app.application.interfaces.token_counter import TokenCounter
    from app.application.services.agent.toolset import AgentToolSet


@lru_cache(maxsize=1)
def build_workflow_engine() -> WorkflowEngine:
    # Extraction uses the dedicated extraction provider (deterministic by
    # default), decoupled from the answer-generation provider.
    settings = get_settings()
    provider = build_extraction_llm_provider()
    if settings.workflow_engine.lower() == "langgraph":
        from app.infrastructure.llm.graphs.extraction_graph import LangGraphExtractionEngine

        return LangGraphExtractionEngine(provider)
    return SequentialExtractionEngine(provider)


@lru_cache(maxsize=1)
def build_consolidation_engine() -> ConsolidationEngine:
    # Consolidation is part of the memory pipeline (not answer generation), so it
    # also uses the extraction provider. The default sequential engine is lexical
    # (Jaccard) and makes no LLM calls, so behavior is unchanged.
    settings = get_settings()
    provider = build_extraction_llm_provider()
    if settings.consolidation_engine.lower() == "langgraph":
        from app.infrastructure.llm.graphs.consolidation_graph import LangGraphConsolidationEngine

        return LangGraphConsolidationEngine(provider)
    return SequentialConsolidationEngine(provider)


def build_agent_runtime(
    toolset: AgentToolSet,
    provider: LLMProvider,
    counter: TokenCounter,
    clock: Clock | None = None,
) -> AgentRuntime:
    """Select the query-time agent runtime by ``AGENT_RUNTIME``.

    Not cached: the toolset is assembled per request from the (singleton-backed)
    services. ``sequential`` is the offline default; ``langgraph`` lazily imports
    the package and is exercised by the skip-guarded agent suite. ``clock`` is the
    monotonic time source for stage-duration observability (Stage 13).
    """
    settings = get_settings()
    if settings.agent_runtime.lower() == "langgraph":
        from app.infrastructure.llm.graphs.agent_graph import LangGraphAgentRuntime

        return LangGraphAgentRuntime(toolset, provider, counter, clock)
    from app.infrastructure.llm.graphs.sequential_agent_runtime import SequentialAgentRuntime

    return SequentialAgentRuntime(toolset, provider, counter, clock)

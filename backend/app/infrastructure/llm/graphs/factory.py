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

from app.application.interfaces.consolidation_engine import ConsolidationEngine
from app.application.interfaces.workflow_engine import WorkflowEngine
from app.core.config import get_settings
from app.infrastructure.llm.graphs.sequential_consolidation_engine import (
    SequentialConsolidationEngine,
)
from app.infrastructure.llm.graphs.sequential_engine import SequentialExtractionEngine
from app.infrastructure.llm.providers.factory import build_llm_provider


@lru_cache(maxsize=1)
def build_workflow_engine() -> WorkflowEngine:
    settings = get_settings()
    provider = build_llm_provider()
    if settings.workflow_engine.lower() == "langgraph":
        from app.infrastructure.llm.graphs.extraction_graph import LangGraphExtractionEngine

        return LangGraphExtractionEngine(provider)
    return SequentialExtractionEngine(provider)


@lru_cache(maxsize=1)
def build_consolidation_engine() -> ConsolidationEngine:
    settings = get_settings()
    provider = build_llm_provider()
    if settings.consolidation_engine.lower() == "langgraph":
        from app.infrastructure.llm.graphs.consolidation_graph import LangGraphConsolidationEngine

        return LangGraphConsolidationEngine(provider)
    return SequentialConsolidationEngine(provider)

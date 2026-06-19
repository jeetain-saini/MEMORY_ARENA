"""Workflow engine factory — selects the extraction engine from configuration.

``WORKFLOW_ENGINE`` chooses the implementation:
  * ``sequential`` -> SequentialExtractionEngine (offline default; dev/tests)
  * ``langgraph``  -> LangGraphExtractionEngine (production; needs ``langgraph``)

The LLM provider is resolved from its own factory. Cached as a process-wide
singleton; call ``build_workflow_engine.cache_clear()`` in tests that change
configuration.
"""

from __future__ import annotations

from functools import lru_cache

from app.application.interfaces.workflow_engine import WorkflowEngine
from app.core.config import get_settings
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

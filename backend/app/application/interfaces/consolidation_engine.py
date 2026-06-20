"""ConsolidationEngine port — evaluate a new memory against existing candidates.

The application layer depends on this abstraction; infrastructure provides
SequentialConsolidationEngine (offline default) and LangGraphConsolidationEngine
(production).  No framework imports cross this boundary.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.application.dto.consolidation_dto import ConsolidationDecision, ConsolidationRequest


class ConsolidationEngine(ABC):
    @abstractmethod
    async def consolidate(self, request: ConsolidationRequest) -> list[ConsolidationDecision]:
        """Compare the new memory against candidates and return decisions."""

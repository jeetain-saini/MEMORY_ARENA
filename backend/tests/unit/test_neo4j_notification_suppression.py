"""Phase 1: the Neo4j driver is constructed with benign-notification suppression.

The knowledge graph is built incrementally, so queries reference relationship
types/labels that may not exist yet; Neo4j flags these with UNRECOGNIZED-class
warnings (GQL 01N51) that the driver logs as noise. We disable that class at the
driver so the server never emits them — without changing query behaviour.
"""

from __future__ import annotations

import asyncio
from unittest.mock import patch

from neo4j import NotificationDisabledClassification

from app.core.config import get_settings
from app.infrastructure.graph.neo4j import Neo4jManager


def test_driver_disables_unrecognized_notifications() -> None:
    async def scenario() -> None:
        captured: dict = {}

        class _FakeDriver:
            async def verify_connectivity(self) -> None:
                return None

            async def close(self) -> None:
                return None

        def _fake_driver(uri, **kwargs):
            captured["uri"] = uri
            captured["kwargs"] = kwargs
            return _FakeDriver()

        mgr = Neo4jManager()
        with patch(
            "app.infrastructure.graph.neo4j.AsyncGraphDatabase.driver",
            side_effect=_fake_driver,
        ):
            await mgr.connect(get_settings())

        disabled = captured["kwargs"].get("notifications_disabled_classifications")
        assert disabled is not None
        assert NotificationDisabledClassification.UNRECOGNIZED in disabled
        await mgr.disconnect()

    asyncio.run(scenario())

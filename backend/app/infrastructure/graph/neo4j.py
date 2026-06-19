"""Neo4j connection manager (async driver).

The Neo4j async driver maintains its own connection pool, so one driver instance
is the singleton. Created at startup (with connectivity verified), closed at
shutdown. Stage 1 only establishes connectivity and a health probe; graph
gateways and Cypher live in later stages.
"""

from __future__ import annotations

import logging

from neo4j import AsyncDriver, AsyncGraphDatabase

from app.core.config import Settings

_logger = logging.getLogger("memoryarena.neo4j")


class Neo4jManager:
    """Lifecycle owner for the async Neo4j driver."""

    def __init__(self) -> None:
        self._driver: AsyncDriver | None = None
        self._database: str = "neo4j"

    async def connect(self, settings: Settings) -> None:
        if self._driver is not None:
            return
        self._database = settings.neo4j_database
        self._driver = AsyncGraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_username, settings.neo4j_password),
            max_connection_pool_size=settings.neo4j_max_connection_pool_size,
        )
        # Fail fast if credentials/URI are wrong.
        await self._driver.verify_connectivity()
        _logger.info("neo4j.connected")

    async def disconnect(self) -> None:
        if self._driver is not None:
            await self._driver.close()
            self._driver = None
            _logger.info("neo4j.disconnected")

    @property
    def driver(self) -> AsyncDriver:
        if self._driver is None:
            raise RuntimeError("Neo4jManager is not connected; call connect() first.")
        return self._driver

    @property
    def database(self) -> str:
        """The configured Neo4j database name (defaults to ``neo4j``)."""
        return self._database

    async def health_check(self) -> bool:
        if self._driver is None:
            return False
        try:
            records, _, _ = await self._driver.execute_query(
                "RETURN 1 AS ok", database_=self._database
            )
            return bool(records and records[0]["ok"] == 1)
        except Exception:  # noqa: BLE001 - health probe must never raise
            _logger.warning("neo4j.health_check.failed", exc_info=True)
            return False


# Process-wide singleton.
neo4j_manager = Neo4jManager()

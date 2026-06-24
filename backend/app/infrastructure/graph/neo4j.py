"""Neo4j connection manager (async driver).

The Neo4j async driver maintains its own connection pool, so one driver instance
is the singleton. Created at startup (with connectivity verified), closed at
shutdown. Stage 1 only establishes connectivity and a health probe; graph
gateways and Cypher live in later stages.
"""

from __future__ import annotations

import asyncio
import logging

from neo4j import AsyncDriver, AsyncGraphDatabase, NotificationDisabledClassification

from app.core.config import Settings

_logger = logging.getLogger("memoryarena.neo4j")

# The knowledge graph is built incrementally, so queries legitimately reference
# relationship types / labels / property keys before any instance exists yet
# (e.g. ``find_neighbors`` filtering on ``CLUSTER_MEMBER`` on a fresh graph).
# Neo4j flags these with UNRECOGNIZED-class notifications (GQL 01N51, code
# ``Neo.ClientNotification.Statement.UnknownRelationshipTypeWarning``) which the
# driver logs at WARNING — pure noise here, since the absence is expected and the
# query is correct. Disabling the class at the driver tells the *server* not to
# emit them, so query results/behaviour are unchanged. Genuinely useful classes
# (PERFORMANCE, DEPRECATION, SECURITY, …) remain enabled.
_DISABLED_NOTIFICATION_CLASSIFICATIONS = [NotificationDisabledClassification.UNRECOGNIZED]


class Neo4jManager:
    """Lifecycle owner for the async Neo4j driver."""

    def __init__(self) -> None:
        self._driver: AsyncDriver | None = None
        self._database: str = "neo4j"
        self._health_timeout: float = 5.0

    async def connect(self, settings: Settings) -> None:
        if self._driver is not None:
            return
        self._database = settings.neo4j_database
        self._health_timeout = settings.health_check_timeout
        self._driver = AsyncGraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_username, settings.neo4j_password),
            max_connection_pool_size=settings.neo4j_max_connection_pool_size,
            # Fast-failure: cap Bolt connection establishment on outage.
            connection_timeout=settings.neo4j_connection_timeout,
            # Silence benign "X does not exist" notifications (see module note).
            notifications_disabled_classifications=_DISABLED_NOTIFICATION_CLASSIFICATIONS,
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
            async with asyncio.timeout(self._health_timeout):
                records, _, _ = await self._driver.execute_query(
                    "RETURN 1 AS ok", database_=self._database
                )
            return bool(records and records[0]["ok"] == 1)
        except (Exception, asyncio.TimeoutError):  # noqa: BLE001 - probe never raises
            _logger.warning("neo4j.health_check.failed", exc_info=True)
            return False


# Process-wide singleton.
neo4j_manager = Neo4jManager()

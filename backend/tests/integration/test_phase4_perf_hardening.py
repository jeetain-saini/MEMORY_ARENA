"""Performance/DoS hardening tests: request body-size limit + graph-overview cap."""

from __future__ import annotations

import asyncio
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.middleware.body_limit import BodySizeLimitMiddleware
from app.application.dto.graph_dto import GraphEdge, GraphEdgeType, GraphNode, NodeType
from app.infrastructure.graph.in_memory_graph_repository import InMemoryGraphRepository


# --- body size limit -------------------------------------------------------

def _app(max_bytes: int) -> FastAPI:
    app = FastAPI()
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=max_bytes)

    @app.post("/echo")
    async def echo(payload: dict) -> dict:  # noqa: ANN001
        return {"len": len(payload.get("data", ""))}

    return app


def test_oversized_body_rejected_413_via_content_length() -> None:
    client = TestClient(_app(max_bytes=100))
    resp = client.post("/echo", json={"data": "x" * 5000})
    assert resp.status_code == 413
    body = resp.json()
    assert body["error"]["code"] == "payload_too_large"


def test_within_limit_body_passes() -> None:
    client = TestClient(_app(max_bytes=10_000))
    resp = client.post("/echo", json={"data": "x" * 100})
    assert resp.status_code == 200
    assert resp.json()["len"] == 100


def test_oversized_chunked_body_rejected_without_content_length() -> None:
    client = TestClient(_app(max_bytes=100))

    def gen():  # streamed body -> no Content-Length header
        yield b'{"data":"' + b"x" * 5000 + b'"}'

    resp = client.post("/echo", content=gen())
    assert resp.status_code == 413


# --- graph overview node cap ----------------------------------------------

def test_get_subgraph_caps_nodes_and_returns_all_when_unbounded() -> None:
    async def scenario() -> None:
        repo = InMemoryGraphRepository()
        user = uuid4()
        ids = [str(uuid4()) for _ in range(50)]
        for nid in ids:
            await repo.upsert_node(GraphNode(node_id=nid, node_type=NodeType.MEMORY,
                                             label="m", properties={"user_id": str(user)}))
        # a couple of edges among the first few nodes
        await repo.create_edge(GraphEdge(source_id=ids[0], target_id=ids[1],
                                         edge_type=GraphEdgeType.RELATED_TO))

        capped = await repo.get_subgraph(user, limit=10)
        assert len(capped.nodes) == 10  # bounded
        # edges only among the capped node set
        capped_ids = {n.node_id for n in capped.nodes}
        assert all(e.source_id in capped_ids and e.target_id in capped_ids for e in capped.edges)

        full = await repo.get_subgraph(user)  # default None = unbounded (maintenance path)
        assert len(full.nodes) == 50

    asyncio.run(scenario())

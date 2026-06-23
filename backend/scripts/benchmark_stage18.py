"""CLI: Stage 18 large-tenant scalability benchmark.

    cd backend && PYTHONPATH=. python scripts/benchmark_stage18.py
    # optional: choose sizes and the brute-force cap
    ... python scripts/benchmark_stage18.py --sizes 10000,50000,100000 --bruteforce-cap 4000

Measures the two Stage 18 hotspots on synthetic tenants of 10k / 50k / 100k
memories and prints a timing report:

  * Clustering connected-components — the inverted-index path (Stage 18.2) vs the
    pre-18.2 exhaustive O(n^2) Jaccard scan. The exhaustive scan is only run up to
    ``--bruteforce-cap`` (it is quadratic and would take hours at 100k); the
    inverted-index path is run at every size.
  * GraphSnapshot (Stage 18.1) — building the batched adjacency index once and
    serving N degree lookups, vs the pre-18.1 per-memory linear edge scans.

Pure in-memory compute (no DB/graph servers), so it isolates the algorithmic
scaling. Synthetic content is grouped into topics so the token overlap — and the
resulting cluster structure — is realistic rather than degenerate.
"""

from __future__ import annotations

import argparse
import random
import time
from dataclasses import dataclass
from uuid import UUID, uuid4

from app.application.dto.graph_dto import GraphEdge, GraphEdgeType, GraphNode, GraphOverview, NodeType
from app.application.services.context._text import jaccard
from app.application.services.intelligence.clustering_engine import (
    ClusterConfig,
    ClusteringEngine,
    _sig,
)
from app.application.services.intelligence.graph_snapshot import GraphSnapshot

_SEED = 1234


@dataclass
class _Mem:
    """Minimal duck-typed stand-in for Memory (clustering only reads id/content)."""

    id: UUID
    content: str


def _gen_memories(n: int, *, topics: int, tokens_per_topic: int = 10,
                  content_tokens: int = 5) -> list[_Mem]:
    rng = random.Random(_SEED)
    vocab = {t: [f"t{t}w{i}" for i in range(tokens_per_topic)] for t in range(topics)}
    out: list[_Mem] = []
    for _ in range(n):
        t = rng.randrange(topics)
        toks = rng.sample(vocab[t], min(content_tokens, tokens_per_topic))
        out.append(_Mem(id=uuid4(), content=" ".join(toks)))
    return out


def _bruteforce_components(memories: list[_Mem], sigs: dict[UUID, set[str]],
                           min_overlap: float) -> int:
    parent: dict[UUID, UUID] = {m.id: m.id for m in memories}

    def find(x: UUID) -> UUID:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i, a in enumerate(memories):
        for b in memories[i + 1:]:
            if sigs[a.id] and sigs[b.id] and jaccard(sigs[a.id], sigs[b.id]) >= min_overlap:
                parent[find(a.id)] = find(b.id)
    return len({find(m.id) for m in memories})


def _bench_clustering(sizes: list[int], bruteforce_cap: int) -> list[dict]:
    engine = ClusteringEngine(lambda: None, None, ClusterConfig(min_overlap=0.2))  # type: ignore[arg-type]
    rows: list[dict] = []
    for n in sizes:
        topics = max(2, n // 50)  # ~50 memories per topic
        memories = _gen_memories(n, topics=topics)
        sigs = {m.id: _sig(m.content) for m in memories}

        t0 = time.perf_counter()
        components = engine._connected_components(memories, sigs)  # noqa: SLF001
        idx_ms = (time.perf_counter() - t0) * 1000

        bf_ms: float | None = None
        if n <= bruteforce_cap:
            t0 = time.perf_counter()
            _bruteforce_components(memories, sigs, 0.2)
            bf_ms = (time.perf_counter() - t0) * 1000

        rows.append({
            "n": n, "topics": topics, "clusters": len(components),
            "inverted_ms": idx_ms, "bruteforce_ms": bf_ms,
        })
    return rows


def _bench_snapshot(sizes: list[int], naive_cap: int) -> list[dict]:
    rng = random.Random(_SEED)
    rows: list[dict] = []
    user = uuid4()
    for n in sizes:
        node_ids = [str(uuid4()) for _ in range(n)]
        nodes = [GraphNode(node_id=i, node_type=NodeType.MEMORY, label="m",
                           properties={"user_id": str(user)}) for i in node_ids]
        # ~1.5 edges per node, random endpoints — a realistic sparse knowledge graph.
        edges = []
        for _ in range(int(n * 1.5)):
            a, b = rng.randrange(n), rng.randrange(n)
            if a != b:
                edges.append(GraphEdge(source_id=node_ids[a], target_id=node_ids[b],
                                       edge_type=GraphEdgeType.RELATED_TO))
        overview = GraphOverview(nodes=nodes, edges=edges)

        # Batched (Stage 18.1): build the index once, then N degree lookups.
        t0 = time.perf_counter()
        snap = GraphSnapshot.from_overview(overview)
        for nid in node_ids:
            snap.degree(nid)
        batched_ms = (time.perf_counter() - t0) * 1000

        # Pre-18.1 shape: each memory linearly scans the full edge list (what a
        # per-memory get_edges devolves to without an index). This is O(N*E) and
        # is only run up to ``naive_cap``.
        permem_ms: float | None = None
        if n <= naive_cap:
            t0 = time.perf_counter()
            for nid in node_ids:
                _ = sum(1 for e in edges if e.source_id == nid or e.target_id == nid)
            permem_ms = (time.perf_counter() - t0) * 1000

        rows.append({"n": n, "edges": len(edges),
                     "batched_ms": batched_ms, "per_memory_ms": permem_ms})
    return rows


def _fmt_ms(v: float | None) -> str:
    return "n/a (capped)" if v is None else f"{v:,.1f} ms"


def _speedup(slow: float | None, fast: float) -> str:
    return "n/a" if not slow or fast <= 0 else f"{slow / fast:,.1f}x"


def main() -> None:
    parser = argparse.ArgumentParser(description="Stage 18 scalability benchmark")
    parser.add_argument("--sizes", default="10000,50000,100000")
    parser.add_argument("--bruteforce-cap", type=int, default=4000,
                        help="max N at which to also run the O(n^2) reference")
    args = parser.parse_args()
    sizes = [int(s) for s in args.sizes.split(",") if s.strip()]

    print("=" * 78)
    print("STAGE 18 LARGE-TENANT BENCHMARK")
    print(f"sizes={sizes}  bruteforce_cap={args.bruteforce_cap}  seed={_SEED}")
    print("=" * 78)

    print("\n[18.2] Clustering connected-components")
    print(f"{'N':>9} {'topics':>7} {'clusters':>9} {'inverted':>14} "
          f"{'bruteforce(O n^2)':>18} {'speedup':>9}")
    for r in _bench_clustering(sizes, args.bruteforce_cap):
        print(f"{r['n']:>9,} {r['topics']:>7,} {r['clusters']:>9,} "
              f"{_fmt_ms(r['inverted_ms']):>14} {_fmt_ms(r['bruteforce_ms']):>18} "
              f"{_speedup(r['bruteforce_ms'], r['inverted_ms']):>9}")

    print("\n[18.1] GraphSnapshot batched degree lookups")
    print(f"{'N':>9} {'edges':>9} {'batched':>14} {'per-memory scan':>16} {'speedup':>9}")
    for r in _bench_snapshot(sizes, args.bruteforce_cap):
        print(f"{r['n']:>9,} {r['edges']:>9,} {_fmt_ms(r['batched_ms']):>14} "
              f"{_fmt_ms(r['per_memory_ms']):>16} "
              f"{_speedup(r['per_memory_ms'], r['batched_ms']):>9}")
    print("\nDone.")


if __name__ == "__main__":
    main()

# Full-Stack Validation (Phase 5)

Real end-to-end validation against the **live Docker stack** (PostgreSQL + Redis +
Neo4j), driving the actual FastAPI app and gathering direct evidence from each
datastore.

Run:

```bash
cd backend
PYTHONPATH=. python scripts/validate_full_stack.py
```

The script boots the real app (lifespan connects all three datastores), creates an
isolated validation user, and exercises every required flow, then asserts evidence
from PostgreSQL, Neo4j, and Redis. Exits non-zero on any failed check.

## Result — 17/17 checks passed

```
[PASS] health endpoint 200
[PASS] create memories (201, real PG write)        - 4 memories created
[PASS] retrieval: list by user                     - 5 listed
[PASS] retrieval: search                           - 4 hits
[PASS] PostgreSQL evidence: rows persisted         - 5 rows for user
[PASS] graph overview (Neo4j-backed)               - 6 nodes in tenant subgraph
[PASS] Neo4j evidence: nodes exist                 - 40 nodes total
[PASS] clustering action                           - HTTP 200: cluster_count=1
[PASS] promotion action                            - HTTP 200
[PASS] forgetting action                           - HTTP 200
[PASS] contradiction resolution                    - archived
[PASS] restore archived memory                     - status 200
[PASS] Redis evidence: cache active                - 2 keys in Redis
[PASS] Prometheus exposition                       - text exposition served
[PASS] backup export from live PostgreSQL          - 38 memories exported
[PASS] restore-recovery into fresh DB matches      - 38 recovered (== 38 exported)
[PASS] benchmark: maintenance cycle                - 79 ms
=== RESULT: 17/17 checks passed ===
```

## Evidence by datastore

- **API** — every flow exercised over HTTP through the real app (create, search,
  list, graph overview, intelligence promote/cluster/forget, contradiction
  resolve, restore, Prometheus).
- **PostgreSQL** — direct `SELECT count(*)` confirms created memories persisted;
  Alembic migrated live DB `0007 → 0008 (role) → 0009 (audit_log)` cleanly
  (head `0009_audit_log`).
- **Neo4j** — the off-request graph-sync pipeline created the tenant's nodes;
  `MATCH (n) RETURN count(n)` confirms nodes exist.
- **Redis** — the cached analytics path populated keys; `DBSIZE` confirms.
- **Backup/recovery** — the live PostgreSQL was logically exported and recovered
  into a throwaway database with an exact memory-count match (regenerable
  embeddings excluded), without touching live data.

## Benchmark

A full per-tenant intelligence maintenance cycle (cluster → promote → forget)
over the validation tenant completed in **~79 ms** through the live stack. The
large-tenant algorithmic benchmarks (10k/50k/100k) are in
[benchmarks/stage18.md](benchmarks/stage18.md).

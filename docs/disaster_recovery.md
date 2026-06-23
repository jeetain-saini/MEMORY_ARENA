# Disaster Recovery Runbook (Phase 3)

MemoryArena has two complementary recovery tiers:

| Tier | Tool | Use for | Verified by |
|---|---|---|---|
| **Physical** | `pg_dump`/`pg_restore`, `neo4j-admin database dump/load` | routine, byte-exact, fast production backups | manual drills (live infra) |
| **Logical** | `DatabaseBackup` / `GraphBackup` (portable JSON) | portability, cross-version migration, recovery verification | `test_phase3_dr_*` (offline round-trip) |

## PostgreSQL

```bash
cd backend
# Backup (custom-format, compressed, self-verified):
POSTGRES_PASSWORD=*** scripts/dr/backup_postgres.sh ./backups
# Restore into a recovery host (destructive; verifies core tables afterwards):
POSTGRES_PASSWORD=*** scripts/dr/restore_postgres.sh ./backups/memoryarena_*.dump memoryarena
```

`backup_postgres.sh` runs `pg_dump --format=custom --no-owner --no-privileges` and
then `pg_restore --list` to prove the dump is readable before trusting it.
`restore_postgres.sh` loads with `--clean --if-exists` and verifies the
`users`/`memories`/`audit_log` tables exist after recovery (3.5).

## Neo4j

```bash
# In the neo4j container (offline dump/load):
docker compose exec neo4j bash scripts/dr/backup_neo4j.sh /backups
docker compose exec neo4j bash scripts/dr/restore_neo4j.sh /backups/neo4j_*.dump neo4j
```

Uses `neo4j-admin database dump/load`. The offline dump needs the database
stoppable; on Enterprise use `neo4j-admin database backup` for hot backups (same
file contract). After restore, verify with `MATCH (n) RETURN count(n)`.

## Logical snapshot (portable, both stores in one file)

```bash
cd backend
PYTHONPATH=. python scripts/dr/logical_snapshot.py export snapshot.json
PYTHONPATH=. python scripts/dr/logical_snapshot.py restore snapshot.json --yes
```

Exports every database table plus the full knowledge graph to one JSON file and
restores both. Backend-agnostic — the same code path is exercised on SQLite +
the in-memory graph by the test suite, so the round-trip is continuously
verified in CI, not just during a drill.

## Recovery verification (3.5)

A restore is only trusted once the data is confirmed readable:

- **Automated (CI):** `test_phase3_dr_database.py` and `test_phase3_dr_graph.py`
  seed data, export, restore into a *fresh* database/graph, and assert the
  recovered rows/nodes/edges (including the audit trail and edge properties)
  match the source exactly, and that restore is idempotent.
- **Operational drill:** after a physical restore, the restore scripts assert the
  core tables are present; follow with an app smoke test (create → retrieve a
  memory) against the recovered stores.

## Schedule & retention (recommendation)

- Physical PostgreSQL dump nightly; Neo4j dump nightly; retain 7 daily + 4 weekly.
- Logical snapshot weekly (portability/audit), retained with each release tag.
- Store backups off-host (object storage); test a full restore monthly.

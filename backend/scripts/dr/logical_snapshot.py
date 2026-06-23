"""CLI: portable logical backup/restore of the database + knowledge graph.

    cd backend && PYTHONPATH=. python scripts/dr/logical_snapshot.py export snapshot.json
    cd backend && PYTHONPATH=. python scripts/dr/logical_snapshot.py restore snapshot.json

The application-level disaster-recovery tool (Phase 3): exports every database
table (DatabaseBackup) and the full knowledge graph (GraphBackup) into one
portable JSON file, and restores both from it. Backend-agnostic and verified by
the offline round-trip suites (test_phase3_dr_*). Use the physical pg_dump /
neo4j-admin scripts for byte-exact production backups; use this for portability,
cross-version migration, and recovery verification.

Restore is DESTRUCTIVE (clears existing rows / upserts the graph); pass
--yes to skip the confirmation.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path


async def _connect():
    from app.core.config import get_settings
    from app.infrastructure.database import models as _models  # noqa: F401 - register tables
    from app.infrastructure.database.postgres import postgres_manager
    from app.infrastructure.graph.factory import build_graph_repository

    settings = get_settings()
    await postgres_manager.connect(settings)
    return postgres_manager, build_graph_repository()


async def _all_user_ids(postgres_manager) -> list:
    from sqlalchemy import select

    from app.infrastructure.database.models.user import UserModel

    async with postgres_manager.sessionmaker() as session:
        rows = (await session.execute(select(UserModel.id))).scalars().all()
    return list(rows)


async def _export(path: str) -> None:
    from app.infrastructure.backup.database_backup import DatabaseBackup
    from app.infrastructure.backup.graph_backup import GraphBackup

    postgres_manager, graph = await _connect()
    try:
        db_snapshot = await DatabaseBackup(postgres_manager.engine).export()
        user_ids = await _all_user_ids(postgres_manager)
        graph_snapshot = await GraphBackup(graph).export(user_ids)
    finally:
        await postgres_manager.disconnect()

    Path(path).write_text(
        json.dumps({"database": db_snapshot, "graph": graph_snapshot}, indent=2),
        encoding="utf-8",
    )
    print(
        f"[logical_snapshot] exported {db_snapshot['row_counts'].get('memories', 0)} memories, "
        f"{graph_snapshot['counts']['nodes']} nodes, {graph_snapshot['counts']['edges']} edges "
        f"-> {path}"
    )


async def _restore(path: str, assume_yes: bool) -> None:
    from app.infrastructure.backup.database_backup import DatabaseBackup
    from app.infrastructure.backup.graph_backup import GraphBackup

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not assume_yes:
        ans = input(f"Restore {path} into the configured DB + graph (DESTRUCTIVE). Type 'restore': ")
        if ans.strip() != "restore":
            print("aborted.")
            return

    postgres_manager, graph = await _connect()
    try:
        db_restored = await DatabaseBackup(postgres_manager.engine).restore(payload["database"])
        graph_restored = await GraphBackup(graph).restore(payload["graph"])
    finally:
        await postgres_manager.disconnect()
    print(f"[logical_snapshot] restored db={db_restored} graph={graph_restored}")


def main() -> None:
    args = sys.argv[1:]
    if len(args) < 2 or args[0] not in {"export", "restore"}:
        print(__doc__)
        sys.exit(2)
    command, path = args[0], args[1]
    assume_yes = "--yes" in args[2:]
    if command == "export":
        asyncio.run(_export(path))
    else:
        asyncio.run(_restore(path, assume_yes))


if __name__ == "__main__":
    main()

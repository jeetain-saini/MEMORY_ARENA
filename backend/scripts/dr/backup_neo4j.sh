#!/usr/bin/env bash
# Physical Neo4j backup (Phase 3.3) via neo4j-admin database dump.
#
#   ./backup_neo4j.sh [OUTPUT_DIR]
#
# Env: NEO4J_DATABASE (default neo4j). neo4j-admin must be on PATH (or set
# NEO4J_ADMIN to its full path). For Docker: run inside the neo4j container, e.g.
#   docker compose exec neo4j /scripts/backup_neo4j.sh /backups
# The offline `database dump` requires the DB to be stoppable; for hot backups on
# Enterprise use `neo4j-admin database backup` instead (same output contract).
set -euo pipefail

OUT_DIR="${1:-./backups}"
DB="${NEO4J_DATABASE:-neo4j}"
ADMIN="${NEO4J_ADMIN:-neo4j-admin}"

mkdir -p "${OUT_DIR}"
STAMP="$(date +%Y%m%d_%H%M%S)"

echo "[backup_neo4j] dumping database '${DB}' -> ${OUT_DIR} (${STAMP})"
"${ADMIN}" database dump "${DB}" --to-path="${OUT_DIR}" --overwrite-destination=true

DUMP_FILE="${OUT_DIR}/${DB}.dump"
[ -f "${DUMP_FILE}" ] || { echo "[backup_neo4j] expected ${DUMP_FILE} not found" >&2; exit 1; }
# Keep a timestamped copy alongside the latest.
cp "${DUMP_FILE}" "${OUT_DIR}/${DB}_${STAMP}.dump"
echo "[backup_neo4j] OK ($(du -h "${DUMP_FILE}" | cut -f1)) — ${OUT_DIR}/${DB}_${STAMP}.dump"

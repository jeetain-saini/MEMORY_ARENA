#!/usr/bin/env bash
# Physical Neo4j restore (Phase 3.4) via neo4j-admin database load.
#
#   ./restore_neo4j.sh DUMP_FILE [TARGET_DB]
#
# Destructive: --overwrite-destination replaces the target database. The database
# must be stopped (offline load). Set DR_ASSUME_YES=1 to skip the confirmation.
set -euo pipefail

DUMP_FILE="${1:?usage: restore_neo4j.sh DUMP_FILE [TARGET_DB]}"
DB="${2:-${NEO4J_DATABASE:-neo4j}}"
ADMIN="${NEO4J_ADMIN:-neo4j-admin}"

[ -f "${DUMP_FILE}" ] || { echo "[restore_neo4j] no such file: ${DUMP_FILE}" >&2; exit 1; }

if [ "${DR_ASSUME_YES:-}" != "1" ]; then
  read -r -p "Restore ${DUMP_FILE} INTO Neo4j database '${DB}' (DESTRUCTIVE). Type 'restore' to proceed: " ans
  [ "${ans}" = "restore" ] || { echo "aborted."; exit 1; }
fi

# neo4j-admin loads from a directory containing <db>.dump; stage the file there.
SRC_DIR="$(cd "$(dirname "${DUMP_FILE}")" && pwd)"
STAGED="${SRC_DIR}/${DB}.dump"
[ "${DUMP_FILE}" -ef "${STAGED}" ] || cp "${DUMP_FILE}" "${STAGED}"

echo "[restore_neo4j] loading ${DUMP_FILE} -> database '${DB}'"
"${ADMIN}" database load "${DB}" --from-path="${SRC_DIR}" --overwrite-destination=true
echo "[restore_neo4j] OK — start the database and verify with: MATCH (n) RETURN count(n)"

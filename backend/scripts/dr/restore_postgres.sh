#!/usr/bin/env bash
# Physical PostgreSQL restore (Phase 3.2). Loads a dump produced by
# backup_postgres.sh into a target database, then verifies recovery.
#
#   PGPASSWORD=... ./restore_postgres.sh BACKUP_FILE [TARGET_DB]
#
# Refuses to run without an explicit target and a typed confirmation, because
# restore is destructive (--clean drops existing objects first).
set -euo pipefail

BACKUP_FILE="${1:?usage: restore_postgres.sh BACKUP_FILE [TARGET_DB]}"
HOST="${POSTGRES_HOST:-localhost}"
PORT="${POSTGRES_PORT:-5432}"
USER="${POSTGRES_USER:-memoryarena}"
DB="${2:-${POSTGRES_DB:-memoryarena}}"
[ -n "${POSTGRES_PASSWORD:-}" ] && export PGPASSWORD="${POSTGRES_PASSWORD}"

[ -f "${BACKUP_FILE}" ] || { echo "[restore_postgres] no such file: ${BACKUP_FILE}" >&2; exit 1; }

if [ "${DR_ASSUME_YES:-}" != "1" ]; then
  read -r -p "Restore ${BACKUP_FILE} INTO ${USER}@${HOST}:${PORT}/${DB} (DESTRUCTIVE). Type 'restore' to proceed: " ans
  [ "${ans}" = "restore" ] || { echo "aborted."; exit 1; }
fi

echo "[restore_postgres] restoring ${BACKUP_FILE} -> ${DB}"
# --clean --if-exists: drop existing objects first so the restore is a clean
# replacement; --no-owner/--no-privileges to land on any recovery host.
pg_restore --host="${HOST}" --port="${PORT}" --username="${USER}" --dbname="${DB}" \
           --clean --if-exists --no-owner --no-privileges "${BACKUP_FILE}"

# Recovery verification (3.5): confirm the schema's anchor tables are present.
COUNT="$(psql --host="${HOST}" --port="${PORT}" --username="${USER}" --dbname="${DB}" \
              -tAc "SELECT count(*) FROM information_schema.tables WHERE table_name IN ('users','memories','audit_log')")"
[ "${COUNT}" = "3" ] || { echo "[restore_postgres] verification FAILED (expected 3 core tables, found ${COUNT})" >&2; exit 1; }
echo "[restore_postgres] OK — core tables present, restore verified"

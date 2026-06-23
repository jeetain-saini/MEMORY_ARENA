#!/usr/bin/env bash
# Physical PostgreSQL backup (Phase 3.1). Produces a compressed custom-format
# dump that restore_postgres.sh can load with pg_restore.
#
#   PGPASSWORD=... ./backup_postgres.sh [OUTPUT_DIR]
#
# Connection comes from the standard libpq env vars (or these app-specific ones):
#   POSTGRES_HOST (default localhost)  POSTGRES_PORT (default 5432)
#   POSTGRES_USER (default memoryarena) POSTGRES_DB (default memoryarena)
#   POSTGRES_PASSWORD -> exported as PGPASSWORD if set
set -euo pipefail

OUT_DIR="${1:-./backups}"
HOST="${POSTGRES_HOST:-localhost}"
PORT="${POSTGRES_PORT:-5432}"
USER="${POSTGRES_USER:-memoryarena}"
DB="${POSTGRES_DB:-memoryarena}"
[ -n "${POSTGRES_PASSWORD:-}" ] && export PGPASSWORD="${POSTGRES_PASSWORD}"

mkdir -p "${OUT_DIR}"
STAMP="$(date +%Y%m%d_%H%M%S)"
OUT_FILE="${OUT_DIR}/memoryarena_${DB}_${STAMP}.dump"

echo "[backup_postgres] dumping ${USER}@${HOST}:${PORT}/${DB} -> ${OUT_FILE}"
# --format=custom: compressed, selectively restorable; --no-owner/--no-privileges
# so the dump restores cleanly onto a recovery host with different roles.
pg_dump --host="${HOST}" --port="${PORT}" --username="${USER}" --dbname="${DB}" \
        --format=custom --no-owner --no-privileges --file="${OUT_FILE}"

# Verify the dump is readable and non-empty (fail fast on a corrupt backup).
pg_restore --list "${OUT_FILE}" >/dev/null
echo "[backup_postgres] OK ($(du -h "${OUT_FILE}" | cut -f1)) — ${OUT_FILE}"
echo "${OUT_FILE}"

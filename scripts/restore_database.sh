#!/usr/bin/env bash
set -euo pipefail

backup_dir="${1:-}"
if [[ -z "${backup_dir}" || ! -d "${backup_dir}" ]]; then
  echo "Usage: RESTORE_DATABASE_URL=... $0 backups/ferminator-TIMESTAMP" >&2
  exit 2
fi
if [[ -z "${RESTORE_DATABASE_URL:-}" ]]; then
  echo "RESTORE_DATABASE_URL is required" >&2
  exit 2
fi
if [[ -n "${DATABASE_URL:-}" && "${RESTORE_DATABASE_URL}" == "${DATABASE_URL}" ]]; then
  echo "Refusing to restore into the source database" >&2
  exit 3
fi

for required in roles.sql schema.sql data.sql SHA256SUMS; do
  if [[ ! -f "${backup_dir}/${required}" ]]; then
    echo "Backup component ${required} is missing" >&2
    exit 3
  fi
done
if command -v shasum >/dev/null 2>&1; then
  (cd "${backup_dir}" && shasum -a 256 -c SHA256SUMS)
else
  (cd "${backup_dir}" && sha256sum -c SHA256SUMS)
fi

python_command="${PYTHON:-python3}"
RESTORE_DATABASE_URL="${RESTORE_DATABASE_URL}" \
  "${python_command}" scripts/assert_restore_target_empty.py

restore_url="${POSTGRES_DOCKER_RESTORE_URL:-${RESTORE_DATABASE_URL}}"
if command -v psql >/dev/null 2>&1; then
  psql --single-transaction --variable ON_ERROR_STOP=1 \
    --file "${backup_dir}/roles.sql" \
    --file "${backup_dir}/schema.sql" \
    --command "SET session_replication_role = replica" \
    --file "${backup_dir}/data.sql" \
    --dbname "${RESTORE_DATABASE_URL}"
elif command -v docker >/dev/null 2>&1; then
  absolute_dir="$(cd "${backup_dir}" && pwd)"
  docker run --rm -v "${absolute_dir}:/backup:ro" \
    "${POSTGRES_TOOLS_IMAGE:-public.ecr.aws/supabase/postgres:17.6.1.143}" \
    psql --single-transaction --variable ON_ERROR_STOP=1 \
      --file /backup/roles.sql \
      --file /backup/schema.sql \
      --command "SET session_replication_role = replica" \
      --file /backup/data.sql \
      --dbname "${restore_url}"
else
  echo "psql or Docker is required" >&2
  exit 4
fi

RESTORE_DATABASE_URL="${RESTORE_DATABASE_URL}" \
  "${python_command}" scripts/verify_restore.py

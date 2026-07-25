#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${DATABASE_URL:-}" ]]; then
  echo "DATABASE_URL is required" >&2
  exit 2
fi
if ! command -v supabase >/dev/null 2>&1; then
  echo "Supabase CLI is required" >&2
  exit 3
fi

backup_root="${1:-backups}"
case "${backup_root}" in
  .|./|backups|./backups) ;;
  *) echo "Use the dedicated backups directory for recovery artifacts" >&2; exit 2 ;;
esac

mkdir -p "${backup_root}"
chmod 700 "${backup_root}"
umask 077

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
backup_dir="${backup_root}/ferminator-${stamp}"
mkdir -p "${backup_dir}"

supabase db dump --db-url "${DATABASE_URL}" \
  --file "${backup_dir}/roles.sql" --role-only
supabase db dump --db-url "${DATABASE_URL}" \
  --file "${backup_dir}/schema.sql"
supabase db dump --db-url "${DATABASE_URL}" \
  --file "${backup_dir}/data.sql" --use-copy --data-only \
  -x "storage.buckets_vectors" -x "storage.vector_indexes"

for required in roles.sql schema.sql data.sql; do
  if [[ ! -s "${backup_dir}/${required}" ]]; then
    echo "Backup component ${required} is empty" >&2
    exit 4
  fi
done

if command -v shasum >/dev/null 2>&1; then
  (cd "${backup_dir}" && shasum -a 256 roles.sql schema.sql data.sql > SHA256SUMS)
else
  (cd "${backup_dir}" && sha256sum roles.sql schema.sql data.sql > SHA256SUMS)
fi

echo "Backup created: ${backup_dir}"
echo "Checksum manifest: ${backup_dir}/SHA256SUMS"

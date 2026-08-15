#!/bin/bash
set -euo pipefail

# ローカル開発 DB（docker-compose.yml で起動する localhost:5432）の手動バックアップ
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

if [ -f "$REPO_ROOT/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  source "$REPO_ROOT/.env"
  set +a
fi

BACKUP_DIR="${SCRIPT_DIR}/data"
PGHOST="${PGHOST:-localhost}"
PGPORT="${POSTGRES_PORT:-5432}"
PGUSER="${POSTGRES_USER:-furlong}"
PGPASSWORD="${POSTGRES_PASSWORD:-furlong}"
PGDATABASE="${POSTGRES_DB:-furlong}"

mkdir -p "$BACKUP_DIR"

TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
OUTPUT_FILE="$BACKUP_DIR/${PGDATABASE}_${TIMESTAMP}.sql.gz"

export PGPASSWORD

pg_dump \
  -h "$PGHOST" \
  -p "$PGPORT" \
  -U "$PGUSER" \
  "$PGDATABASE" \
  | gzip > "$OUTPUT_FILE"

echo "Backup saved: $OUTPUT_FILE"

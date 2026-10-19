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

if command -v pg_dump >/dev/null 2>&1; then
  pg_dump \
    -h "$PGHOST" \
    -p "$PGPORT" \
    -U "$PGUSER" \
    "$PGDATABASE" \
    | gzip > "$OUTPUT_FILE"
else
  # ホストに pg_dump が無い場合は db コンテナ内の pg_dump を使う
  (cd "$REPO_ROOT" && docker compose exec -T db pg_dump -U "$PGUSER" "$PGDATABASE") \
    | gzip > "$OUTPUT_FILE"
fi

echo "Backup saved: $OUTPUT_FILE"

# 新しいバックアップが正常なら、自動バックアップ（${PGDATABASE}_YYYYMMDD_HHMMSS.sql.gz）を
# 最新 RETENTION_COUNT 件だけ残す。手動の furlong_manual_* や sync.sh の
# furlong_<host>_* は名前のパターンが違うので消さない。
"$SCRIPT_DIR/prune.sh" "$OUTPUT_FILE" "${PGDATABASE}_[0-9]*.sql.gz" "${RETENTION_COUNT:-3}"

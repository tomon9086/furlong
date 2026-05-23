#!/bin/bash
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/backup}"
PGHOST="${PGHOST:-db}"
PGPORT="${PGPORT:-5432}"
PGUSER="${POSTGRES_USER:?POSTGRES_USER is required}"
PGPASSWORD="${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}"
PGDATABASE="${POSTGRES_DB:?POSTGRES_DB is required}"
RETENTION_DAYS="${RETENTION_DAYS:-7}"
RETENTION_COUNT="${RETENTION_COUNT:-3}"

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


# --- 保持ロジック ---
# RETENTION_DAYS より古いファイルを新しい順に並べ、RETENTION_COUNT 個を超えたものを削除する
OLD_FILES=$(find "$BACKUP_DIR" -name "*.sql.gz" -mtime +"$RETENTION_DAYS" | sort -r)

if [ -z "$OLD_FILES" ]; then
  echo "No old backups to delete (older than ${RETENTION_DAYS} days)"
else
  TO_DELETE=$(echo "$OLD_FILES" | tail -n +"$((RETENTION_COUNT + 1))")
  if [ -n "$TO_DELETE" ]; then
    echo "$TO_DELETE" | xargs rm -f
    echo "Deleted old backups (kept ${RETENTION_COUNT} newest files older than ${RETENTION_DAYS} days)"
  else
    echo "No old backups to delete (${RETENTION_COUNT} or fewer files older than ${RETENTION_DAYS} days)"
  fi
fi

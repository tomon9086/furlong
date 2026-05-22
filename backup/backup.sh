#!/bin/sh
set -eu

BACKUP_DIR="${BACKUP_DIR:-/backup}"
PGHOST="${PGHOST:-db}"
PGPORT="${PGPORT:-5432}"
PGUSER="${POSTGRES_USER:?POSTGRES_USER is required}"
PGPASSWORD="${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}"
PGDATABASE="${POSTGRES_DB:?POSTGRES_DB is required}"
RETENTION_DAYS="${RETENTION_DAYS:-7}"

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

find "$BACKUP_DIR" -name "*.sql.gz" -mtime +"$RETENTION_DAYS" -delete
echo "Deleted backups older than ${RETENTION_DAYS} days"

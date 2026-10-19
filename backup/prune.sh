#!/bin/bash
set -euo pipefail

# 新しく取ったバックアップが正常なときだけ、古いバックアップを消して最新 N 件を残す。
#
# 使い方:
#   backup/prune.sh <新しいバックアップ> <名前のパターン> [残す件数] [--dry-run]
#
# - <新しいバックアップ> が gzip として壊れている、または MIN_BACKUP_BYTES（既定 1MB）
#   より小さい場合は何も消さずにエラー終了する（失敗したダンプで正常な
#   バックアップを押し出さないため）。
# - <名前のパターン> は find -name の形式。<新しいバックアップ> と同じディレクトリで、
#   パターンに合うファイルを名前の降順（= タイムスタンプの新しい順）に並べ、
#   [残す件数]（既定 3）より後ろを消す。
#   例: "furlong_[0-9]*.sql.gz" は furlong_manual_* や furlong_golem_* には合わない。

NEW_FILE=${1:?新しいバックアップのパスを指定してください}
PATTERN=${2:?名前のパターンを指定してください}
KEEP=${3:-3}
DRY_RUN=false
if [ "${4:-}" = "--dry-run" ] || [ "${3:-}" = "--dry-run" ]; then
  DRY_RUN=true
  [ "${3:-}" = "--dry-run" ] && KEEP=3
fi
MIN_BACKUP_BYTES=${MIN_BACKUP_BYTES:-1048576}

SIZE=$(wc -c < "$NEW_FILE" | tr -d ' ')
if [ "$SIZE" -lt "$MIN_BACKUP_BYTES" ]; then
  echo "Error: $NEW_FILE が ${SIZE} バイトしかないため、古いバックアップは消しません" >&2
  exit 1
fi
if ! gzip -t "$NEW_FILE"; then
  echo "Error: $NEW_FILE が gzip として壊れているため、古いバックアップは消しません" >&2
  exit 1
fi

DIR=$(dirname "$NEW_FILE")
INDEX=0
find "$DIR" -maxdepth 1 -type f -name "$PATTERN" | sort -r | while IFS= read -r FILE; do
  INDEX=$((INDEX + 1))
  if [ "$INDEX" -le "$KEEP" ]; then
    continue
  fi
  if [ "$DRY_RUN" = true ]; then
    echo "(dry-run) 削除予定: $FILE"
  else
    rm -f "$FILE"
    echo "Deleted old backup: $FILE"
  fi
done

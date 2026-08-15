#!/bin/bash
set -euo pipefail

# 任意のホストで稼働している PostgreSQL コンテナから直接 pg_dump し、
# ローカルの backup/data/ に保存 → ローカル DB へ復元する。
#
# 使い方:
#   backup/sync.sh <host> [options]
#
# 引数:
#   <host>                 リモートホスト（~/.ssh/config の Host エイリアス、または user@hostname）
#
# オプション:
#   --container NAME       リモートの Postgres コンテナ名（省略時は image=postgres:16-alpine で自動検出）
#   --remote-db NAME       リモート DB 名（省略時はローカル .env の POSTGRES_DB / 既定値 furlong）
#   --remote-user NAME     リモート DB ユーザー（省略時はローカル .env の POSTGRES_USER / 既定値 furlong）
#   --no-restore           ダンプの取得のみ行い、ローカル DB への復元は行わない
#   -y, --yes              復元前の確認プロンプトをスキップする
#   -h, --help             このヘルプを表示する
#
# 例:
#   backup/sync.sh myhost                  # myhost から取得してローカル DB を上書き
#   backup/sync.sh myhost --no-restore     # 取得のみ（backup/data/ に保存して終了）

usage() {
  sed -n '3,24p' "$0" | sed 's/^# \{0,1\}//'
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
BACKUP_DATA_DIR="$SCRIPT_DIR/data"

HOST=""
REMOTE_CONTAINER=""
REMOTE_DB=""
REMOTE_USER=""
RESTORE=true
SKIP_CONFIRM=false

while [ $# -gt 0 ]; do
  case "$1" in
    --container)
      REMOTE_CONTAINER="$2"; shift 2 ;;
    --remote-db)
      REMOTE_DB="$2"; shift 2 ;;
    --remote-user)
      REMOTE_USER="$2"; shift 2 ;;
    --no-restore)
      RESTORE=false; shift ;;
    -y|--yes)
      SKIP_CONFIRM=true; shift ;;
    -h|--help)
      usage; exit 0 ;;
    -*)
      echo "Unknown option: $1" >&2; usage; exit 1 ;;
    *)
      if [ -z "$HOST" ]; then
        HOST="$1"; shift
      else
        echo "Unexpected argument: $1" >&2; usage; exit 1
      fi
      ;;
  esac
done

if [ -z "$HOST" ]; then
  echo "Error: <host> is required" >&2
  usage
  exit 1
fi

# ローカルの .env をデフォルト値として読み込む（存在すれば）
if [ -f "$REPO_ROOT/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  source "$REPO_ROOT/.env"
  set +a
fi

REMOTE_DB="${REMOTE_DB:-${POSTGRES_DB:-furlong}}"
REMOTE_USER="${REMOTE_USER:-${POSTGRES_USER:-furlong}}"

LOCAL_DB="${POSTGRES_DB:-furlong}"
LOCAL_USER="${POSTGRES_USER:-furlong}"
LOCAL_PASSWORD="${POSTGRES_PASSWORD:-furlong}"
LOCAL_PORT="${POSTGRES_PORT:-5432}"

if [ -z "$REMOTE_CONTAINER" ]; then
  echo "==> Detecting Postgres container on '$HOST'..."
  REMOTE_CONTAINER=$(ssh "$HOST" "docker ps --filter ancestor=postgres:16-alpine --format '{{.Names}}'" | head -n1)
  if [ -z "$REMOTE_CONTAINER" ]; then
    echo "Error: could not auto-detect a postgres:16-alpine container on '$HOST'. Pass --container explicitly." >&2
    exit 1
  fi
  echo "    -> using container '$REMOTE_CONTAINER'"
fi

mkdir -p "$BACKUP_DATA_DIR"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
OUTPUT_FILE="$BACKUP_DATA_DIR/${REMOTE_DB}_${HOST}_${TIMESTAMP}.sql.gz"

echo "==> Dumping '$REMOTE_DB' from '$HOST' (container: $REMOTE_CONTAINER)..."
ssh "$HOST" "docker exec ${REMOTE_CONTAINER} pg_dump -U ${REMOTE_USER} --clean --if-exists ${REMOTE_DB}" | gzip > "$OUTPUT_FILE"
echo "==> Saved: $OUTPUT_FILE"

if [ "$RESTORE" != true ]; then
  exit 0
fi

if [ "$SKIP_CONFIRM" != true ]; then
  read -r -p "This will overwrite the local database '${LOCAL_DB}' (localhost:${LOCAL_PORT}). Continue? [y/N] " ANSWER
  case "$ANSWER" in
    [Yy]*) ;;
    *) echo "Aborted (dump kept at $OUTPUT_FILE)"; exit 0 ;;
  esac
fi

echo "==> Restoring into local DB '${LOCAL_DB}' (localhost:${LOCAL_PORT})..."
gunzip -c "$OUTPUT_FILE" | PGPASSWORD="$LOCAL_PASSWORD" psql -h localhost -p "$LOCAL_PORT" -U "$LOCAL_USER" -d "$LOCAL_DB"
echo "==> Done"

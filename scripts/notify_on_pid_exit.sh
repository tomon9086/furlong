#!/bin/bash
# 指定PIDのプロセス終了を待ち、ntfy.shに通知を送る。
# Usage: notify_on_pid_exit.sh <PID> <LOGFILE> <完了判定文字列> <通知メッセージ>
set -euo pipefail

PID=$1
LOGFILE=$2
DONE_MARKER=$3
LABEL=$4

cd "$(dirname "$0")/.."
set -a
source .env
set +a

if [ -z "${NTFY_TOPIC_URL:-}" ]; then
  echo "NTFY_TOPIC_URL が .env に設定されていません" >&2
  exit 1
fi

while kill -0 "$PID" 2>/dev/null; do
  sleep 300
done

if grep -qF "$DONE_MARKER" "$LOGFILE"; then
  MSG="[$LABEL] 完了: $(grep -F "$DONE_MARKER" "$LOGFILE" | tail -1)"
else
  MSG="[$LABEL] プロセス終了(完了ログなし・要確認): $LOGFILE"
fi

curl -s -H "Title: furlong scraper" -d "$MSG" "$NTFY_TOPIC_URL" > /dev/null

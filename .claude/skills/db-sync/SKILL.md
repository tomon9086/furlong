# DB 同期

任意のリモートホストで稼働している PostgreSQL コンテナから直接 `pg_dump` し、
ローカルの `backup/data/` に保存した上でローカル DB へ復元する。

本番 DB はポートを外部公開していないため、SSH でホストに入り
`docker exec <container> pg_dump ...` をリモート実行してストリームで受け取る方式を取る
（`docs/plan/db-backup.md` の本番バックアップ方式と同じ発想）。

## 実行コマンド

```sh
backup/sync.sh <host>
```

- `<host>` は `~/.ssh/config` の `Host` エイリアス、または `user@hostname`。
- Postgres コンテナ（`postgres:16-alpine`）はリモート上で自動検出する。複数稼働していて
  自動検出が失敗する場合は `--container <name>` で明示する。
- 既定ではダンプ取得後にローカル DB（`docker compose up -d` で起動しているもの）を
  **上書き復元**する。復元前に確認プロンプトが出る。
- ダンプの取得だけ行いたい場合は `--no-restore` を付ける。
- 確認プロンプトを省略したい場合は `-y` / `--yes` を付ける。

詳細なオプションは `backup/sync.sh --help` を参照。

## 使用例

```sh
# myhost（本番ホスト）から取得してローカル DB を同期する
backup/sync.sh myhost

# 取得のみ（backup/data/ に保存して終了、ローカル DB は変更しない）
backup/sync.sh myhost --no-restore
```

## 前提

- 対象ホストへ SSH でログインできること（`ssh <host>` が通ること）
- ローカルの PostgreSQL が `docker compose up -d` で起動していること
- ローカル接続情報は `.env`（`POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` / `POSTGRES_PORT`）から読み込む

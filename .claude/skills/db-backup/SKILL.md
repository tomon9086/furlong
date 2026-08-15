---
name: db-backup
description: ローカル開発DBのバックアップを取る。マイグレーションや破壊的なDB操作の前に実行する。
---

# DB バックアップ（ローカル）

ローカル開発 DB（`docker-compose.yml` で起動する `localhost:5432`）を `pg_dump` でバックアップする。

```sh
./backup/backup-local.sh
```

- 保存先: `backup/data/`（gitignore 対象）
- ファイル名: `furlong_YYYYMMDD_HHMMSS.sql.gz`
- 接続情報はリポジトリルートの `.env`（`POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` / `POSTGRES_PORT`）を読む。未設定時は `db-access` skill と同じデフォルト（`furlong` / `furlong` / `furlong` / `5432`）を使う。

## リストア

```sh
gunzip -c backup/data/<ファイル名>.sql.gz | PGPASSWORD=furlong psql -h localhost -d furlong -U furlong
```

## 本番 DB のバックアップ

本番は `docker-compose.prod.yml` の `backup` サービスが毎日3:00に自動実行する。手動実行は
[docs/development.md](../../../docs/development.md) の「バックアップ」節を参照。

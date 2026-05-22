# 開発手順

## ドキュメント管理ルール

本プロジェクトでは以下のドキュメント体系で管理する。

| ファイル | 用途 |
|---|---|
| `docs/development.md` | 開発に必要な手順・コマンド・環境構築などをまとめる |
| `docs/plan.md` | 実装計画を対話しながら検討・整理するときのメモ |
| `docs/spec.md` | `plan.md` をもとに確定した仕様をまとめる |
| `docs/todo.md` | TODO リスト |
| `docs/knowledge.md` | プロジェクト固有ではない汎用ナレッジの蓄積 |

### 各ドキュメントの運用ルール

- **plan.md** は探索・議論の場。決定前のアイデアや選択肢を自由に書く。
- **spec.md** は決定事項のみを記録する。`plan.md` での議論を経て確定したものに限る。
- **todo.md** は実装タスクを管理する。完了したタスクは削除せずチェックを付ける。
- **knowledge.md** は他プロジェクトにも流用できる汎用的な知見を記録する。プロジェクト固有の情報は書かない。
- **development.md**（本ファイル）は開発者が実際に手を動かす際に参照する手順書。コマンドや環境構築手順を中心に記述する。

---

## 環境構築

### 前提

- Docker / Docker Compose
- Python 3.11+
- [uv](https://docs.astral.sh/uv/) — Python パッケージ・プロジェクト管理ツール

```bash
# uv のインストール（未インストールの場合）
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 手順

```bash
# 1. 環境変数ファイルを作成
cp .env.example .env

# 2. PostgreSQL を起動
docker compose up -d

# 3. 全パッケージの依存をインストール（ルートで実行）
uv sync

# dev 依存も含める場合（全パッケージの extras を含む）
uv sync --all-extras
```

本プロジェクトは uv ワークスペース構成（`pyproject.toml` 参照）。
`.venv` はルートに一つ作成され、全パッケージが共有する。

## 開発サーバー起動

### PostgreSQL

```bash
# 起動
docker compose up -d

# 停止
docker compose down

# ログ確認
docker compose logs -f db

# psql で接続
docker compose exec db psql -U furlong -d furlong
```

## プログラム実行

```bash
# scraper
uv run --package furlong-scraper python -m scraper.main

# predictor: モデル学習
uv run --package furlong-predictor python -m predictor.main train

# predictor: 指定レースの予測
uv run --package furlong-predictor python -m predictor.main predict <race_id>
```

## バックアップ

```bash
# 手動バックアップ（本番環境で実行）
docker compose -f docker-compose.prod.yml run --rm backup /backup.sh
```

バックアップファイルは `./backup/` ディレクトリに `furlong_YYYYMMDD_HHMMSS.sql.gz` の形式で保存される。
定期実行は毎日深夜3:00（crond による自動実行）。

## テスト

```bash
# scraper
uv run --package furlong-scraper pytest

# predictor
uv run --package furlong-predictor pytest

# repository（統合テストあり。Docker が起動している必要がある）
uv run --package furlong-repository pytest
```

## ビルド・デプロイ

> TODO: ビルド・デプロイ手順をここに記載する

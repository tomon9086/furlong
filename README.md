# furlong

競馬予想 AI

## 構成

```
furlong/
├── docker-compose.yml   # PostgreSQL 起動設定
├── db/
│   └── schema.sql       # テーブル定義（psqldef で管理）
├── scraper/             # netkeiba スクレイパー (Python)
└── predictor/           # 予想プログラム (Python・LightGBM)
```

## セットアップ

### 前提

- Docker / Docker Compose
- Python 3.11+
- [uv](https://docs.astral.sh/uv/)

### 手順

```bash
# 環境変数ファイルを作成
cp .env.example .env

# PostgreSQL を起動
docker compose up -d

# 依存パッケージをインストール
uv sync
```

## 実行

```bash
# スクレイパー
uv run --package furlong-scraper python -m scraper.main

# 予想
uv run --package furlong-predictor python -m predictor.main
```

## ドキュメント

| ファイル | 内容 |
|---|---|
| [docs/spec.md](docs/spec.md) | 仕様書 |
| [docs/development.md](docs/development.md) | 開発手順・コマンド集 |
| [docs/plan.md](docs/plan.md) | 実装計画メモ |
| [docs/todo.md](docs/todo.md) | TODO リスト |

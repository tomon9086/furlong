# 本番デプロイ構成 `docker-compose.prod.yml`（検討中）

> このファイルは探索・議論の場です。決定前のアイデアや選択肢を自由に書いてください。
> 確定した仕様は `spec.md` に移してください。

---

## 背景・目的

predictor HTTP API・scraper デーモン・DB を本番環境でコンテナとして常時稼働させる。
開発用 `docker-compose.yml` とは別に `docker-compose.prod.yml` を用意して本番設定を定義する。

## サービス構成

| サービス | 内容 | restart ポリシー |
|---|---|---|
| `db` | PostgreSQL 16 | `always` |
| `api` | predictor FastAPI サーバー | `always` |
| `scraper` | APScheduler を使った定期スクレイピングデーモン | `always` |

## 開発用との主な差分

| 設定 | 開発用 (`docker-compose.yml`) | 本番用 (`docker-compose.prod.yml`) |
|---|---|---|
| db ポート公開 | ○（ホスト直接接続のため） | ✗（コンテナ内部のみ） |
| restart | `unless-stopped` | `always` |
| api サービス | なし | あり（port 8000） |
| scraper サービス | なし | あり（デーモン） |

## 未解決の論点

- [ ] api の Dockerfile 作成（`predictor/Dockerfile` を新設）
- [ ] scraper デーモン（APScheduler）の Dockerfile 作成（`scraper/Dockerfile` を新設）
- [ ] 環境変数の管理方法（本番では `.env` ファイルではなくシークレット管理ツールが望ましい）
- [ ] HTTPS 対応（リバースプロキシ / Nginx 等の前段配置）
- [ ] モデルファイルをどう渡すか（ボリュームマウント or イメージに埋め込み）

## 決定事項

- `docker-compose.prod.yml` を新設し、本番構成のみを定義する
- db のポートはホストに公開しない（コンテナ内ネットワークのみ）
- 全サービスの restart ポリシーを `always` に設定
- db の healthcheck を定義し、api/scraper は `service_healthy` を待ってから起動する
- モデルファイルは `predictor/models/` をボリュームマウントして渡す

## 実装ステップ

1. `docker-compose.prod.yml` を作成（db・api・scraper の骨格）← **完了**
2. `predictor/Dockerfile` を作成（FastAPI + uvicorn で起動）
3. `scraper/Dockerfile` を作成（APScheduler デーモンとして起動）
4. `predictor/predictor/api.py` を実装（「predictor HTTP API」セクション参照）
5. `scraper/scraper/scheduler.py` を実装（「scraper 定期実行機能」セクション参照）

# TODO

> 完了したタスクは削除せず、チェックを付けてください。
> セクション内のタスクがすべて完了したら、セクションごと削除してください。

## scraper 定期実行機能

- [ ] `scrape_incremental()` 関数を `scraper/main.py` に追加（手動実行もできるよう開始日を引数でオーバーライド可能に）
- [ ] `scrape_shutuba_upcoming()` 関数を `scraper/main.py` に追加（翌日の未取得出馬表を検索して保存）
- [ ] APScheduler で2つのバッチを 14:00 / 22:00 に呼び出す `scraper/scraper/scheduler.py` を実装
- [ ] `docker-compose.yml` に scraper デーモンサービスを追加
- [ ] 騎手・調教師パーサーを実装して補完フローに組み込む（後回し可）

## predictor HTTP API

- [ ] `furlong-predictor` の `pyproject.toml` に `uvicorn` / `fastapi` 依存を追加
- [ ] `predictor/predictor/api.py` を実装（`GET /health`・`GET /predict/{race_id}` エンドポイント）
- [ ] サーバ起動時にモデルを1回だけロードする仕組みを `api.py` に実装
- [ ] `docker-compose.yml` に api サービス（port 8000）を追加

## 本番デプロイ構成

- [x] `docker-compose.prod.yml` を作成（db・api・scraper の骨格）
- [ ] `predictor/Dockerfile` を作成（FastAPI + uvicorn で起動）
- [ ] `scraper/Dockerfile` を作成（APScheduler デーモンとして起動）


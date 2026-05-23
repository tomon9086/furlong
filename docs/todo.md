# TODO

> 完了したタスクは削除せず、チェックを付けてください。
> セクション内のタスクがすべて完了したら、セクションごと削除してください。

## predictor HTTP API

- [x] `furlong-predictor` の `pyproject.toml` に `uvicorn` / `fastapi` 依存を追加
- [ ] `predictor/predictor/api.py` を実装（`GET /health`・`GET /predict/{race_id}` エンドポイント）
- [ ] サーバ起動時にモデルを1回だけロードする仕組みを `api.py` に実装
- [ ] `docker-compose.yml` に api サービス（port 8000）を追加

## 本番デプロイ構成

- [x] `docker-compose.prod.yml` を作成（db・api・scraper の骨格）
- [x] `predictor/Dockerfile` を作成（FastAPI + uvicorn で起動）
- [x] `scraper/Dockerfile` を作成（APScheduler デーモンとして起動）


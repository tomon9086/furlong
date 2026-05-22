# TODO

> 完了したタスクは削除せず、チェックを付けてください。
> セクション内のタスクがすべて完了したら、セクションごと削除してください。

## 予測精度改善

### フェーズ1: leaky feature の除外とベースライン計測（必須）

- [x] `get_feature_columns()` から `finish_time_sec` / `first_corner_pos` / `odds` / `popularity` を除外する
- [x] 除外後にモデルを再学習し、回収率・的中率・logloss のベースラインを計測・記録する

### フェーズ2: 先行指数フィーチャーの追加（実装難度：低）

- [x] `compute_recent_stats()` に `first_corner_pos`（通過順の先頭コーナー順位）の直近3走・5走平均を追加
- [x] 予測時クエリ `_RECENT_STATS_QUERY` に先行指数集計を追加
- [x] `get_feature_columns()` に先行指数フィーチャー（`avg_corner_last3` 等）を追加
- [x] 再学習して回収率の改善を計測

### フェーズ4: 重賞フラグ補完（実装難度：低）

- [x] `preprocess()` で `race_name` から `(GI)` / `(GII)` / `(GIII)` / `(L)` を抽出し `grade` カラムを補完するロジックを追加
- [x] 再学習して重賞での予測精度を検証

---

## scraper 定期実行機能

- [x] `scrape_incremental()` 関数を `scraper/main.py` に追加（手動実行もできるよう開始日を引数でオーバーライド可能に）
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

## DB バックアップ

- [ ] `backup/backup.sh` を作成（`pg_dump | gzip` → `/backup/` に保存、7日以上古いファイルを削除）
- [ ] `backup/crontab` を作成（`0 3 * * * /backup.sh`）
- [ ] `backup/Dockerfile` を作成（`postgres:16-alpine` ベース、crontab を組み込む）
- [ ] `docker-compose.prod.yml` に `backup` サービスを追加


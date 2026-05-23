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
- [x] `scrape_shutuba_upcoming()` 関数を `scraper/main.py` に追加（翌日の未取得出馬表を検索して保存）
- [x] APScheduler で2つのバッチを 14:00 / 22:00 に呼び出す `scraper/scraper/scheduler.py` を実装
- [x] `docker-compose.yml` に scraper デーモンサービスを追加
- [x] 騎手・調教師パーサーを実装して補完フローに組み込む（後回し可）

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

- [x] `backup/backup.sh` を作成（`pg_dump | gzip` → `/backup/` に保存、7日以上古いファイルを削除）
- [x] `backup/crontab` を作成（`0 3 * * * /backup.sh`）
- [x] `backup/Dockerfile` を作成（`postgres:16-alpine` ベース、crontab を組み込む）
- [x] `docker-compose.prod.yml` に `backup` サービスを追加

## 馬データ欠損の修正（scrape_race / scrape_backfill）

### コード修正（再発防止）

- [x] `repository/database.py` に `get_existing_horse_ids(horse_ids)` メソッドを追加
- [x] `scraper/main.py` に `_supplement_horses(rows, db, client)` ヘルパーを実装
- [x] `scrape_race` から `_supplement_horses` を呼び出すよう修正
- [x] `scrape_backfill` から `_supplement_horses` を呼び出すよう修正

### 遡及修正（既存データの補完）

- [x] `race_results` に存在するが `horses` テーブルに未登録の `horse_id` を洗い出す SQL を確認
- [x] 未登録馬を1頭ずつスクレイプして補完する遡及スクリプトを実装・実行する

---

## DB 欠損チェックスクリプト

### 事前決定事項（実装前に判断）

- [x] チェック4（レース結果欠落）で「今日より前の日付に限定」する条件を付けるか判断する → **付ける**（`TO_DATE(r.date, 'YYYY/MM/DD') < CURRENT_DATE`）
- [x] DB 接続方法を決定する（`repository` パッケージの `Database` クラス vs `psycopg` 直接利用） → **`psycopg` 直接利用**

### 実装

- [x] `tools/` ディレクトリを作成する
- [x] `tools/check_missing.py` を実装する（DB接続・各クエリ実行・結果フォーマット出力）
  - チェック1: `race_results.horse_id` が `horses` に存在しないケース
  - チェック2: `race_results.jockey_id` が `jockeys` に存在しないケース
  - チェック3: `race_results.trainer_id` が `trainers` に存在しないケース
  - チェック4: 結果確定レースで `race_results` が存在しないケース
  - チェック5: 結果確定レースで `payoffs` が存在しないケース
  - 件数・サンプル10件・サマリの出力形式を実装
- [x] 動作確認する（`uv run python tools/check_missing.py`）


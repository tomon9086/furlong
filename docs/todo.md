# TODO

> 完了したタスクは削除せず、チェックを付けてください。
> セクション内のタスクがすべて完了したら、セクションごと削除してください。

## 回収率改善（目標110%）

> 計画: [plan/prediction-accuracy-followup.md](./plan/prediction-accuracy-followup.md)
> 目的は精度でなく回収率。「割安な対象（EV > 1）を選んで買う」ベット選択が中核。

### フェーズ1: 事前オッズ取得 → 真の回収率を測定（最優先）

- [x] 事前オッズの保存先を設計する（確定オッズ `race_results.odds` と分離し、**学習には渡さない**方針を spec.md に記録）
- [x] `scraper`: 締切前（前日／当日朝）オッズページのパーサを追加（`scraper/scraper/parsers/` に odds パーサ）
- [x] `scraper`: 事前オッズ取得コマンドを `scraper/scraper/main.py` に追加（例 `python -m scraper odds <race_id>`）し、`repository` に保存メソッドを追加
- [x] `db/schema.sql` に事前オッズ用のカラム／テーブルを追加
- [x] `predictor`: `load_predict_data`（`preprocessing.py`）で事前オッズを join し、predict 経路へ渡す
- [x] 対象レースで `predict` を実行し、`output.py` の `ev` が NaN でなくなり単勝推奨が出ることを確認
- [x] バックテスト（`train_mode` の `ev_filter_analysis`）が確定オッズで稼働していることを確認し、回収率測定の基準とする

### フェーズ2: 確率較正の可視化（Brier / calibration curve）

- [ ] `evaluation.py` に Brier score を追加（win / place 両モデル）
- [ ] `evaluation.py` に calibration curve（予測確率ビン別の実測勝率）を算出する関数を追加
- [ ] `main.py` の `train_mode` 出力に Brier・calibration を組み込む
- [ ] 較正のズレ（過信／過小評価）を確認し、必要なら確率較正（Isotonic / Platt）の導入を検討タスク化

### フェーズ3: EVフィルタ × 券種 × 人気帯のグリッドで回収率最適化

- [ ] `ev_filter_analysis`（`evaluation.py`）を「EV閾値 × 人気帯」の2軸グリッドに拡張
- [ ] 回収率の bootstrap 信頼区間を算出する関数を追加（110% が誤差でないかを判定。数千ベット規模が前提）
- [ ] 単勝以外の券種（複勝・馬連・三連複など）の回収率評価を追加（`payoffs` テーブルを活用）
- [ ] walk-forward（rolling）検証を実装（`split_by_date` を単一分割から複数期間へ）
- [ ] 最適な「閾値 × 人気帯 × 券種」の組み合わせを実測し [experiments.md](./experiments.md) に記録

### フェーズ4: lambdarank 化／特徴量追加で確率の質を底上げ

- [ ] `model.py` をレース内順位学習（lambdarank, group=レース単位）へ変更する検討・実装（[improvement_plan.md](./improvement_plan.md) B-4）
- [ ] 特徴量追加: 距離変化（前走距離との差）を `preprocessing.py` に実装し `get_feature_columns` に追加
- [ ] 特徴量追加: コース替わり（前走 `course_type` からの変更フラグ）
- [ ] 特徴量追加: 馬体重のレース内相対値（`horse_weight` をレース内で正規化）
- [ ] 特徴量追加: 騎手乗り替わりフラグ（前走と騎手が異なるか）
- [ ] 特徴量追加: 枠順 × 距離の有利不利（距離帯ごとの枠番別平均着順の交互作用）
- [ ] 再学習し、回収率（フェーズ3の指標）への効果を測定

## predictor HTTP API

- [x] `furlong-predictor` の `pyproject.toml` に `uvicorn` / `fastapi` 依存を追加
- [ ] `predictor/predictor/api.py` を実装（`GET /health`・`GET /predict/{race_id}` エンドポイント）
- [ ] サーバ起動時にモデルを1回だけロードする仕組みを `api.py` に実装
- [ ] `docker-compose.yml` に api サービス（port 8000）を追加

## 本番デプロイ構成

- [x] `docker-compose.prod.yml` を作成（db・api・scraper の骨格）
- [x] `predictor/Dockerfile` を作成（FastAPI + uvicorn で起動）
- [x] `scraper/Dockerfile` を作成（APScheduler デーモンとして起動）


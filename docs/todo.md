# TODO

> 完了したタスクは削除せず、チェックを付けてください。
> セクション内のタスクがすべて完了したら、セクションごと削除してください。

## 回収率改善（目標110%）

> 計画: [plan/prediction-accuracy-followup.md](./plan/prediction-accuracy-followup.md)
> 目的は精度でなく回収率。「割安な対象（EV > 1）を選んで買う」ベット選択が中核。

### フェーズ4: lambdarank 化／特徴量追加で確率の質を底上げ

- [ ] `model.py` をレース内順位学習（lambdarank, group=レース単位）へ変更する検討・実装（[improvement_plan.md](./improvement_plan.md) B-4）
- [ ] 特徴量追加: 距離変化（前走距離との差）を `preprocessing.py` に実装し `get_feature_columns` に追加
- [ ] 特徴量追加: コース替わり（前走 `course_type` からの変更フラグ）
- [ ] 特徴量追加: 馬体重のレース内相対値（`horse_weight` をレース内で正規化）
- [ ] 特徴量追加: 騎手乗り替わりフラグ（前走と騎手が異なるか）
- [ ] 特徴量追加: 枠順 × 距離の有利不利（距離帯ごとの枠番別平均着順の交互作用）
- [ ] 再学習し、回収率（フェーズ3の指標）への効果を測定

## モンテカルロ着順シミュレーション

> 計画: [plan/ensemble-montecarlo.md](./plan/ensemble-montecarlo.md)
> 方針: 薄く実装して「ベースモデルにエッジがあるか」を当たり判定 → 結果次第で組合せ馬券へ展開する。MC はエッジを **増幅** するだけで、無いエッジは生み出さない点に注意。

### フェーズ1: 薄い MC 実装（当たり判定のための最小実装）

- [ ] `predictor/predictor/simulation.py` を新設し、各馬の能力分布から着順をサンプリングする MC コア関数 `simulate_finishing_orders(win_probs, n_iter, rng)` を実装する（入力: レース内の `win_prob` ベクトル、出力: 着順サンプル列）
- [ ] サンプリング方式を決め、spec.md に記録する（候補: ① Plackett-Luce（`win_prob` を強度パラメータとみなし無置換抽選）／② 各馬に能力スコア + ガンベルノイズで argsort）
- [ ] MC サンプル列から馬券種ごとの確率を集計する関数群を実装（単勝・複勝の確率算出。組合せ系はフェーズ3）
- [ ] `n_iter`（試行回数）のデフォルト値と再現性のための乱数シード方針を spec.md に記録する

### フェーズ2: MC 単勝確率の妥当性検証（当たり判定）

- [ ] バックテスト用に「MC 単勝確率」を算出するパイプラインを `evaluation.py` に追加（既存 `win_prob` をそのまま MC 入力に流し、サンプリング後の単勝確率と比較）
- [ ] MC 単勝確率 vs 直接の `win_prob` の差分を可視化（同一であるべきだが、サンプリング方式により乖離する場合があるためサニティチェック）
- [ ] MC 単勝確率と確定オッズ（`race_results.odds`）で EV を算出し、`ev_filter_analysis` 相当の回収率を計測
- [ ] **判定**: 単勝 EV ベットで回収率 > 100% に乗るかを [experiments.md](./experiments.md) に記録（→ 乗ればフェーズ3へ進む。乗らなければ MC 拡張は保留し、アンサンブル／特徴量改善（フェーズ4）に注力する）

### フェーズ3: 組合せ馬券（馬連・ワイド・三連複・三連単）への展開

> フェーズ2の判定で「単勝 EV > 100%」を確認できた場合のみ着手する。

- [ ] 馬券種ごとの確率算出関数を `simulation.py` に追加（馬連=1-2着の組合せ、ワイド=3着以内の任意2頭、三連複=1-2-3着の組合せ、三連単=1-2-3着の順列）
- [ ] `payoffs` テーブルから券種別の払戻を結合し、組合せ単位の EV を計算するユーティリティを `evaluation.py` に追加
- [ ] 組合せ馬券の EV 評価をバックテストに組み込み、券種 × EV閾値 × 人気帯のグリッドで回収率を測定（回収率改善フェーズ3 の `ev_filter_analysis` 拡張に MC 確率を入力として接続する）
- [ ] 三連単など組合せ爆発が起きる券種は、EV 上位 N 点で打ち切る方針と N の調整方法を spec.md に記録する
- [ ] 最良の券種・閾値の組合せを [experiments.md](./experiments.md) に記録

### フェーズ4: predict 経路への組み込み

> フェーズ3 までで MC の価値が確認できた場合のみ着手する。

- [ ] `predictor/predictor/output.py` の推奨買い目算出を MC ベースに置き換える／追加する（事前オッズ × MC 確率で組合せ馬券の EV を計算）
- [ ] CSV 出力スキーマに券種別の推奨買い目カラムを追加し、spec.md「出力」を更新

## predictor HTTP API

- [x] `furlong-predictor` の `pyproject.toml` に `uvicorn` / `fastapi` 依存を追加
- [ ] `predictor/predictor/api.py` を実装（`GET /health`・`GET /predict/{race_id}` エンドポイント）
- [ ] サーバ起動時にモデルを1回だけロードする仕組みを `api.py` に実装
- [ ] `docker-compose.yml` に api サービス（port 8000）を追加

## 本番デプロイ構成

- [x] `docker-compose.prod.yml` を作成（db・api・scraper の骨格）
- [x] `predictor/Dockerfile` を作成（FastAPI + uvicorn で起動）
- [x] `scraper/Dockerfile` を作成（APScheduler デーモンとして起動）


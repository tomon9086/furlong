# TODO

> 完了したタスクは削除せず、チェックを付けてください。
> セクション内のタスクがすべて完了したら、セクションごと削除してください。

## 回収率改善（目標110%）

> 計画: [plan/prediction-accuracy-followup.md](./plan/prediction-accuracy-followup.md)
> 目的は精度でなく回収率。「割安な対象（EV > 1）を選んで買う」ベット選択が中核。

- [x] 較正を out-of-sample に修正: `split_by_date` を train/val/test 3分割にし、val で `calibrate_models`、test で評価する構成に変更する
- [x] Bootstrap CI 算出: `evaluation.py` に bootstrap 信頼区間関数を追加し、「EV≥2.0 × 7番人気以下 × 馬連」の 95% CI 下限が 100% を超えるか確認する
- [ ] Walk-forward での馬連戦略安定性確認: walk-forward の各フォールドで「EV≥1.5 × 7番人気以下 × 馬連」回収率を測定し、全フォールドで安定しているか確認する
- [x] Optuna によるハイパーパラメータ最適化: `num_leaves`, `learning_rate`, `min_child_samples`, `feature_fraction`, `half_life_days` を探索。評価指標は walk-forward 平均回収率 → n_trials=10 で実施。最良パラメータは walk-forward では baseline を上回ったが、標準split + bootstrap CI では逆に悪化し汎化しなかった（[experiments.md](./experiments.md) 参照）。n_trials を増やした再探索は今後の課題

## モンテカルロ着順シミュレーション

> 計画: [plan/ensemble-montecarlo.md](./plan/ensemble-montecarlo.md)
> 方針: 薄く実装して「ベースモデルにエッジがあるか」を当たり判定 → 結果次第で組合せ馬券へ展開する。MC はエッジを **増幅** するだけで、無いエッジは生み出さない点に注意。

### フェーズ3: 組合せ馬券（馬連・ワイド・三連複・三連単）への展開

> フェーズ2の判定で「単勝 EV > 100%」を確認できた場合のみ着手する。

- [ ] 馬券種ごとの確率算出関数を `simulation.py` に追加（馬連=1-2着の組合せ、ワイド=3着以内の任意2頭、三連複=1-2-3着の組合せ、三連単=1-2-3着の順列）
- [ ] `payoffs` テーブルから券種別の払戻を結合し、組合せ単位の EV を計算するユーティリティを `evaluation.py` に追加
- [ ] 組合せ馬券の EV 評価をバックテストに組み込み、券種 × EV閾値 × 人気帯のグリッドで回収率を測定（回収率改善フェーズ3 の `ev_filter_analysis` 拡張に MC 確率を入力として接続する）
- [ ] 三連単など組合せ爆発が起きる券種は、EV 上位 N 点で打ち切る方針と N の調整方法を spec.md に記録する
- [ ] 最良の券種・閾値の組合せを [experiments.md](./experiments.md) に記録

## 血統データの遡及補完

> 発端: `dam`（母馬）特徴量の重要度を walk-forward フォールド別に見たところ、2000〜2016年の
> フォールドでは 0%（一度も使われていない）で、2016年以降のフォールドで急に上位（1〜3位）に
> 跳ね上がるという不自然な階段状の変化があった。原因を調査したところ `horses.sire`/`dam`/
> `broodmare_sire` が2016年以前の馬でほぼ空だったことが判明。
>
> 原因は2つあった。(1) netkeiba が血統テーブルを馬詳細ページから専用ページ
> （`/horse/ped/{horse_id}/`）に分離しており、スクレイパーが追従できず新馬でも血統が
> 欠落し続けていた → **修正済み**（`scraper/scraper/client.py` の `get_horse_pedigree`・
> `parsers/horse.py` の `parse_pedigree`／`_parse_blood_table`）。(2) 1995〜2006年の馬
> （約87,000頭）はプロフィールページ自体が未取得のまま → 未着手（下記）。

- [ ] 1995〜2006年の馬（`race_results.horse_id` にはあるが `horses` に存在しない約87,000頭）を `scraper.backfill_missing --horses-only` で遡及スクレイピングする。件数が多く対netkeibaリクエストが長時間・大量になるため、実行タイミング（負荷・レート制限への配慮）を検討してから着手する
- [ ] 遡及補完後、sire/dam/broodmare_sire の feature importance が古い期間の walk-forward フォールドでも安定するか再確認する

## predictor HTTP API

- [x] `furlong-predictor` の `pyproject.toml` に `uvicorn` / `fastapi` 依存を追加
- [ ] `predictor/predictor/api.py` を実装（`GET /health`・`GET /predict/{race_id}` エンドポイント）
- [ ] サーバ起動時にモデルを1回だけロードする仕組みを `api.py` に実装
- [ ] `docker-compose.yml` に api サービス（port 8000）を追加



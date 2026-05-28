# TODO

> 完了したタスクは削除せず、チェックを付けてください。
> セクション内のタスクがすべて完了したら、セクションごと削除してください。

## 回収率改善（目標110%）

> 計画: [plan/prediction-accuracy-followup.md](./plan/prediction-accuracy-followup.md)
> 目的は精度でなく回収率。「割安な対象（EV > 1）を選んで買う」ベット選択が中核。

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

## predictor HTTP API

- [x] `furlong-predictor` の `pyproject.toml` に `uvicorn` / `fastapi` 依存を追加
- [ ] `predictor/predictor/api.py` を実装（`GET /health`・`GET /predict/{race_id}` エンドポイント）
- [ ] サーバ起動時にモデルを1回だけロードする仕組みを `api.py` に実装
- [ ] `docker-compose.yml` に api サービス（port 8000）を追加



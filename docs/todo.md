# TODO

> 完了したタスクは削除せず、チェックを付けてください。
> セクション内のタスクがすべて完了したら、セクションごと削除してください。

## 学習・推論改善（ベースライン評価フォローアップ）

### #1 未使用特徴量の追加

- [x] `preprocessing.py` の `get_feature_columns()` に `finish_time_sec` を追加
- [x] `preprocessing.py` の `get_feature_columns()` に `first_corner_pos` を追加
- [x] 追加後に `uv run python -m predictor.main train` で再学習・評価指標を比較
  - win_accuracy: 0.3487 / recovery_rate: **1.0848** / win_logloss: 0.2028 / place_logloss: 0.3773

### #2 win_prob のレース内正規化

- [x] `model.py` の `predict()` 内でレース単位に `win_prob` を正規化（`win_prob / win_prob.groupby(race_id).transform('sum')`）
- [x] 正規化前後で評価指標を比較して効果確認
  - win_accuracy: 0.3473 / recovery_rate: **1.1007** / win_logloss: 0.1984 / place_logloss: 0.3777
  - recovery_rate +0.0159、win_logloss -0.0044 改善

### #4 期待値ベースの買い目絞り込み

- [ ] `evaluation.py` に期待値フィルタ付き回収率を計算する関数を追加（`ev_filter_analysis(test_df, pred_df, thresholds)`）
  - `win_prob × odds > threshold` で絞り込んだ場合の的中率・回収率・カバレッジを複数閾値で算出
- [ ] `main.py` の評価フローで結果を出力し、最適閾値を確認



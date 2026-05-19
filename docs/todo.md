# TODO

> 完了したタスクは削除せず、チェックを付けてください。
> セクション内のタスクがすべて完了したら、セクションごと削除してください。

## 学習・推論改善（ベースライン評価フォローアップ）

### #1 未使用特徴量の追加

- [ ] `preprocessing.py` の `get_feature_columns()` に `finish_time_sec` を追加
- [ ] `preprocessing.py` の `get_feature_columns()` に `first_corner_pos` を追加
- [ ] 追加後に `uv run python -m predictor.main train` で再学習・評価指標を比較

### #2 win_prob のレース内正規化

- [ ] `model.py` の `predict()` 内でレース単位に `win_prob` を正規化（`win_prob / win_prob.groupby(race_id).transform('sum')`）
- [ ] 正規化前後で評価指標を比較して効果確認

### #3 人気別・オッズ帯別の評価指標追加

- [ ] `evaluation.py` に `evaluate_by_popularity(test_df, pred_df)` 関数を追加
  - 人気帯別（1番人気 / 2-3番 / 4-6番 / 7番以下）の推奨頻度・的中率・回収率を集計
  - オッズ帯別（〜1.9倍 / 2-4倍 / 5-9倍 / 10倍以上）の推奨頻度・的中率・回収率を集計
- [ ] `main.py` の評価フローで `evaluate_by_popularity()` を呼び出して出力

### #4 期待値ベースの買い目絞り込み

- [ ] `evaluation.py` に期待値フィルタ付き回収率を計算する関数を追加（`ev_filter_analysis(test_df, pred_df, thresholds)`）
  - `win_prob × odds > threshold` で絞り込んだ場合の的中率・回収率・カバレッジを複数閾値で算出
- [ ] `main.py` の評価フローで結果を出力し、最適閾値を確認



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

### #5 期待値しきい値 1.5 の適用

- [ ] `predict_mode` の出力で EV < 1.5 の馬を除外し、買い目を絞り込む
  - `win_prob × odds > 1.5` を満たす馬のみ推奨として出力する
- [ ] しきい値適用後の予測出力を確認


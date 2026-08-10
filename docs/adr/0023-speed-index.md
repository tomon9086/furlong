# ADR-0023: タイム偏差値（スピード指数、avg_speed_index_last3/5）フィーチャーを追加

- Status: Accepted
- Date: 2026-08-03

## Context

`finish_time` をレース内でz-score化した `race_time_zscore` を作り、直近3走・5走平均を特徴量化できないか検証した。既存の `avg_finish_last3`（着順ベース）は同着順でも僅差か大差かを区別できないが、本特徴量はタイム差（マージン）を連続値で捉える。当初は「コース・距離・馬場状態での正規化」が難しいと想定していたが、「レース内z-score」方式（他馬という一番厳密な比較対象を使う）で正規化問題を回避した。比較対象は[ADR-0021](./0021-in-race-pace-features.md)採用後のbaseline。

## Decision

`avg_speed_index_last3`, `avg_speed_index_last5` を採用する。

## Consequences

- 標準splitで4指標すべてが明確に改善（win_accuracy +0.47pt, recovery_rate +1.02pt, win_logloss -0.0015, place_logloss -0.0017）。この時点で最大の改善幅。
- Walk-forwardでも4指標全てが改善または横ばいで、悪化した指標なし。実装コストが高いと当初想定していたが、設計変更により効果・実装コストの両面で成功。
- 同コース種別・同距離条件版（`_cond`）への拡張は未着手のまま残る。

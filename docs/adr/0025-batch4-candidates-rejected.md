# ADR-0025: 新規候補4案（厩舎複数出走数・頭数正規化近走成績・斤量自己比較・騎手直近30走勝率）は追加しない

- Status: Rejected
- Date: 2026-08-03

## Context

「全部乗せ」診断（[ADR-0024](./0024-days-since-last-race-accepted.md) Context 参照）の結果が混在していたため、新規4案を1つずつ個別に検証した。比較対象は[ADR-0024](./0024-days-since-last-race-accepted.md)採用後のbaseline。

- 厩舎の複数出走頭数（`trainer_multi_entry_count`）
- 頭数正規化した近走成績（`avg_finish_pct_last3/5`）
- 斤量の自己比較（`weight_carried_vs_avg3`）
- 騎手の直近30走勝率（`jockey_win_rate_last30`）

## Decision

4案とも不採用とする（walk-forward検証には進めない）。

## Consequences

- 4案とも同じパターン: Log Lossの変化はノイズレベル（±0.0001〜0.0004、この時点で「明確な信号」とみなす閾値0.0007を下回る）で、win_accuracy・recovery_rateは軒並み悪化。
- いずれも既存特徴量（`avg_finish_last3`, `weight_carried_relative`, `jockey_win_rate_venue_cond`/`jockey_prior_win_rate` 等）と情報が重複しやすい設計だったことが共通点。

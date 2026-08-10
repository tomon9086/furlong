# ADR-0005: 騎手×コース勝率・調教師直近30走勝率フィーチャーを追加

- Status: Accepted
- Date: 2026-05-21

## Context

[ADR-0004](./0004-grade-backfill.md) の状態に対し、`jockey_course_win_rate`（騎手×競馬場×コース種別の累積勝率）と `trainer_win_rate_last30`（調教師の直近30走勝率）を追加できないか検証した。

## Decision

両フィーチャーを採用する。

## Consequences

- win_accuracy +0.17pp、win_logloss -0.0007、place_logloss -0.0017 と確率推定は改善。recovery_rate は -1.58pp とやや後退。
- GI の回収率が 27.14% と突出して低下（騎手・調教師の実績が GI 級の実力を過大評価している可能性）。GII・GIII は 88〜90% と高水準を維持。
- 7番人気以下の回収率が 84.07% → 78.51% に低下し、[ADR-0004](./0004-grade-backfill.md) で改善していた穴馬選択がやや後退した。総合判断として採用。

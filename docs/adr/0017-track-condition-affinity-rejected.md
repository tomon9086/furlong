# ADR-0017: 馬場状態別の適性統計（*_trackcond）は追加しない

- Status: Rejected
- Date: 2026-08-03

## Context

既存の `course_type`×`distance` 条件別成績（`*_cond`）と同じ枠組みで、`track_condition`（良／稍重／重／不良）別の直近3走・5走成績（`avg_finish`, `best_finish`, `avg_last3f`）を6カラム追加できないか検証した。比較対象は[ADR-0014](./0014-owner-lifetime-win-rate.md)時点のbaseline。

## Decision

不採用とする。

## Consequences

- Log Lossは単勝・複勝ともほぼ横ばい、win_accuracy -0.20pt、recovery_rate -1.26ptと悪化。採用基準を満たさず。
- `track_condition` は4カテゴリしかなく大半が「良」に偏っているため、稍重／重／不良の集計値はサンプル数が少なくノイズが大きい。既存の `avg_finish_last3`/`avg_finish_last3_cond` と情報が重複しつつノイズだけ増やした可能性。

# ADR-0022: 重賞実績フラグ（graded_win_prior_flag / graded_placed_prior_flag）は追加しない

- Status: Rejected
- Date: 2026-08-03

## Context

過去にG1/G2/G3で勝利・連対（3着以内）した経験の有無をフラグ化できないか検証した。`races.grade` は常にNULL（スクレイパー未収集）のため、[ADR-0004](./0004-grade-backfill.md) と同じ `race_name` の正規表現抽出をSQL側でも再現して判定した。比較対象は[ADR-0021](./0021-in-race-pace-features.md)採用後のbaseline。

## Decision

不採用とする。

## Consequences

- 改善した指標が一つもなく、win_accuracy -0.26pt、recovery_rate -1.21pt、place_logloss +0.0008と悪化。
- 既存の `avg_finish_last3` 等の近走成績や `class_level`（[ADR-0018](./0018-class-level-change.md)）とかなり重複する情報であり、二値フラグ化したことで既存の連続値特徴量より粗い情報になりノイズとして働いた可能性。

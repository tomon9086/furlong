# ADR-0020: 騎手×馬の組み合わせ成績（jockey_horse_prior_*）は追加しない

- Status: Rejected
- Date: 2026-08-03

## Context

特定の馬とその騎手のペア実績（`jockey_horse_prior_win_rate`, `jockey_horse_prior_mounts`）を、既存の全期間累積勝率フィーチャーと同じ方式で追加できないか検証した。比較対象は[ADR-0018](./0018-class-level-change.md)採用後のbaseline。

## Decision

不採用とする。

## Consequences

- 標準splitで全指標が横ばい〜悪化（win_accuracy -0.24pt, recovery_rate -0.62pt, win_logloss +0.0003）。改善した指標が一つもなく、walk-forward検証には進めなかった。
- 同一馬×同一騎手の再騎乗自体が稀で、組み合わせの大半が1〜数回しか出現せず、サンプル数不足で学習ノイズになった可能性。

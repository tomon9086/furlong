# ADR-0008: MC（Plackett-Luce）による単勝EV戦略の拡張を保留

- Status: Rejected
- Date: 2026-05-27

## Context

Plackett-Luce（Gumbel max trick）モンテカルロサンプリングで単勝勝率を再計算し、直接の win_prob と比較した。サニティチェックでは両者はほぼ一致（correlation 0.998565）。この上で単勝EVフィルタ戦略が回収率100%を超えるかを検証した。

## Decision

単勝EVベット戦略のMC拡張には進まない。アンサンブル／特徴量改善（[ADR-0007](./0007-distance-course-weight-jockey-change-features.md) 以降）に注力する。

## Consequences

- 最良閾値（EV≥1.0）でも単勝回収率は65.9%止まりで、MCを挟んでも直接win_probとの差は±0.5pp以内。MCが単勝に新たな情報を追加しないことを確認。
- 組合せ馬券へのMC展開（フェーズ3）は着手しない。

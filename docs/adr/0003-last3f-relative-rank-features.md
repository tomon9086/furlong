# ADR-0003: 上がり3ハロン相対順位フィーチャー（avg_last3f_rank_last3/5, _cond）を追加

- Status: Accepted
- Date: 2026-05-20

## Context

[ADR-0002](./0002-leading-position-index-features.md) の状態に対し、レース内の上がり3ハロン（ラスト600m）相対順位の直近3走・5走平均を追加できないか検証した。上がりの絶対値（`avg_last3f_last3` 等）は既に特徴量にあり、相対順位の追加効果は限定的と予想された。

## Decision

`avg_last3f_rank_last3/5` および `_cond` 版を採用する。

## Consequences

- win_accuracy +0.18pp、win_logloss -0.0010pp と小さいが一貫した改善。recovery_rate はほぼ横ばい（-0.01pp）。
- 想定通り効果は小さいが、悪化した指標がないため採用。

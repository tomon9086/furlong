# ADR-0007: 距離変化・コース替わり・馬体重相対値・騎手乗り替わり・枠順×距離フィーチャーを追加

- Status: Accepted
- Date: 2026-05-27

## Context

[ADR-0005](./0005-jockey-trainer-recent-features.md) の状態に対し、`distance_change`（前走からの距離変化）・`course_type_change`（芝/ダート変更）・`horse_weight_relative`（レース内馬体重z-score）・`jockey_change`（騎手乗り替わり）・`bracket_distance_avg_finish`（枠番×距離カテゴリの平均着順）の5特徴量を追加できないか検証した。

## Decision

5特徴量すべてを採用する。

## Consequences

- win_brier -0.0002、place_brier -0.0019 と確率推定の質が改善。
- 単一splitのEVグリッドで「EV≥1.0〜2.0 × 7番人気以下 × 馬連（132〜137%）」等の高回収率が見つかったが、この戦略化は後日 walk-forward pooled bootstrap CI で再現せず不採用（[ADR-0009](./0009-longshot-quinella-trio-strategy-rejected.md)）。
- Walk-forward 平均回収率は [ADR-0005](./0005-jockey-trainer-recent-features.md) 時点の82.9%から81.6%へ微減、直近フォールドが74.2%とやや悪化しており、以降のフェーズでの改善余地として残った。

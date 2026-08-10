# ADR-0006: 確率較正に Isotonic Regression を採用

- Status: Accepted
- Date: 2026-05-26

## Context

モデルの生の予測確率と実際の的中率の間にズレ（中高確率帯での過剰予測、複勝低確率帯での過小評価）が確認された。sklearn の `IsotonicRegression`（`out_of_bounds="clip"`）による後段較正の効果を検証した。

## Decision

Isotonic Regression による確率較正を採用する（`predictor/calibration.py`）。较正は保留セット（val split）に対してフィットし、テストデータへのリークを避ける。

## Consequences

- Brier score が単勝 -0.0011、複勝 -0.0022 改善。
- 単勝の中高確率帯（0.2〜0.8）での過剰予測、複勝低確率帯での過小評価がいずれも較正後に縮小。
- 較正後高確率ビンはサンプル数が数件〜十数件と少なく統計的に不安定な点は残る。

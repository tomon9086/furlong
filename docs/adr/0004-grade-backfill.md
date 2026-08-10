# ADR-0004: race_name からの重賞グレード補完

- Status: Accepted
- Date: 2026-05-20

## Context

`grade` カラムが NULL の行が多く存在した。`race_name` に含まれる `(GI)/(GII)/(GIII)/(L)` 表記を正規表現で抽出すれば補完できると考え検証した。

## Decision

`race_name` からの正規表現抽出による `grade` 補完ロジックを採用する（後に `races.grade` 自体が常に NULL であることが判明し、predict 時の SQL 側にも同じ抽出ロジックを移植している。[ADR-0022](./0022-graded-race-prior-flag-rejected.md) 参照）。

## Consequences

- recovery_rate 77.32% → 79.87%（+2.55pp）、win_accuracy +0.33pp、place_logloss -0.0017 と全指標が改善。
- 7番人気以下の回収率 81.25% → 84.07% に上昇。重賞・リステッド戦の特性をモデルが学習できるようになった。

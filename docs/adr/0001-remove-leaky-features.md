# ADR-0001: leaky feature（finish_time_sec / odds / popularity）を特徴量から除外

- Status: Accepted
- Date: 2026-05-20

## Context

初期モデルは `finish_time_sec`・`odds`・`popularity` を特徴量に含めていたが、これらは予測時点（レース確定前）には得られない情報であり、モデルの実力を過大評価していた（win_accuracy 30.06%, recovery_rate 80.04%）。

## Decision

`get_feature_columns()` からこの3カラムを除外し、これを以降のフェーズの真のベースラインとする。

## Consequences

- win_accuracy 30.06% → 18.57%、recovery_rate 80.04% → 74.04% に低下。数値としては悪化だが、予測時に利用不可能な情報への依存を取り除いた「本来の実力値」であり、以降の全フェーズはこの値を基準に改善を測る。

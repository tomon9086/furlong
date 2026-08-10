# ADR-0030: `dam`（母馬名）フィーチャーを除外する

- Status: Accepted
- Date: 2026-08-10

## Context

血統フィーチャー（`sire`/`dam`/`broodmare_sire`）の遡及補完後の安定性を walk-forward の
feature importance（gain降順rank）で確認したところ、`dam` は複勝モデルで常にrank 1位に
見えた。しかし rank の目視比較は検定になっていないため、`evaluation.pedigree_permutation_importance_ci`
（シャッフルによる log-loss 悪化幅の95% bootstrap CI、CI下限>0で有意）で再検証したところ、
`dam` は複勝モデルで全5フォールドとも非有意、単勝モデルでも5フォールド中2フォールドで非有意
だった。高カーディナリティな個体名 categorical は gain が訓練データへの過適合を過大評価しやすい
（held-outでの寄与としては裏付けられない）と判断し、`dam` を特徴量から除外した場合の影響を
`evaluation.paired_bootstrap_model_comparison`（レース単位ペアードbootstrap、95%CI、n=10,000）
で標準split・walk-forward双方で検証した。

## Decision

`dam` を特徴量から除外する（`preprocessing.get_feature_columns` から削除）。`sire`・
`broodmare_sire` は引き続き使用する。

## Consequences

- 標準split: 除外後、win_logloss -0.000807（CI [-0.001086, -0.000537], 有意）・
  place_logloss -0.001147（CI [-0.001754, -0.000472], 有意）・win_accuracy +0.66pt
  （CI [+0.17pt, +1.13pt], 有意）といずれも改善。recovery_rate は -0.53pt だが
  CI [-3.22pt, +2.02pt] で有意差なし（悪化の証拠ではない）。
- walk-forward（5フォールドプール）: win_logloss -0.000902（CI [-0.001018, -0.000785], 有意）・
  place_logloss -0.003402（CI [-0.003635, -0.003159], 有意）・win_accuracy +0.51pt
  （CI [+0.25pt, +0.76pt], 有意）と改善が標準splitより明確化。recovery_rate は +0.82pt
  （CI [-0.98pt, +2.59pt]）で有意差なしだが、標準splitと違い符号は改善方向。
- 特徴量を1つ減らしてモデルを単純化しつつ、精度指標が有意に改善するという「不採用ではなく削除」
  の判断。今後、高カーディナリティな個体名系categoricalを追加する際はgain rankだけで採否判断
  せず、必ず permutation importance のCI検定を通すこと。

# ADR-0032: 複勝較正をsigmoid（Platt scaling）に変更する案を不採用

- Status: Rejected
- Date: 2026-09-20

## Context

[ADR-0006](./0006-isotonic-calibration.md) で採用した Isotonic Regression はステップ関数のため、複数馬の生スコアが同一の較正区間（プール）に入ると `place_prob` が完全一致するtieが発生する（過去57レース中54レースで発生を確認）。tieの根本解消策として、連続関数である sigmoid（Platt scaling, `predictor/calibration.py` の `method="sigmoid"`）へ変更する案を検証した。

## Decision

複勝モデルの較正方式を sigmoid に変更しない。isotonic を維持する。

過去テストセット（157,477行、11,367レース）でのペアードbootstrap検証（race-level resampling, n_boot=10,000）の結果:

- 複勝3頭ベット戦略の回収率: isotonic較正 81.1% → sigmoid較正 80.7%（点推定 -0.36pt、95%CI [-1.02pt, +0.22pt]、有意差なし）
- 複勝 log-loss: 0.4580 → 0.4643（+0.0063、95%CI [+0.0056, +0.0069]、**有意に悪化**）
- 単勝 log-loss: 0.2297 → 0.2294（-0.0003、有意だが実務上無視できる差）
- 単勝的中率（1位予想の的中率）: 23.64% → 23.96%（+0.33pt、有意だが微小）

複勝の較正精度（log-loss）が統計的に有意に悪化し、回収率にも有意な改善は見られなかったため、sigmoidへの変更は正当化できない。

## Consequences

- 複勝較正はisotonicを維持（[ADR-0006](./0006-isotonic-calibration.md)の決定を継続）。
- tie（較正の縮退）自体は残る。実害（推奨頭数の意図しない増加）は [ADR-0031](./0031-place-recommendation-exact-top3-selection.md) の選出ロジック修正で対処済み。
- 単勝側にはsigmoidでわずかな改善傾向が見られたが、複勝との整合性（同一较正方式を維持する運用のシンプルさ）を優先し、今回は見送る。単勝のみ較正方式を変える提案が出た場合は別途ADRを起こす。

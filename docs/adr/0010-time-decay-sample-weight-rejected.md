# ADR-0010: 時間減衰サンプルウェイト（half_life_days）は現時点で非推奨

- Status: Rejected
- Date: 2026-07-30

## Context

`compute_time_decay_weight` によるサンプルウェイトを学習に適用し、`half_life_days ∈ {365, 1095, 1825, 3650, None}` を単一 train/val/test split で比較した。非定常性への対処として直近データを重視すれば精度が上がるという仮説を検証した。

その後 Optuna（n_trials=10）で他パラメータと同時探索したところ `half_life_days=1095` が walk-forward平均回収率で最良（84.08%）となったが、標準split + bootstrap CI で baseline と再比較すると win_accuracy・recovery_rate ともに悪化し汎化しなかった（[ADR-0012](./0012-optuna-winlogloss-hyperparameters.md) で採用したパラメータとは別の探索）。

## Decision

`half_life_days` のデフォルトは無効（`None`、重みなし）を維持する。実装（`compute_time_decay_weight`, `model.train(half_life_days=...)`, CLIフラグ）は非破壊的に残し、`half_life_days=None` なら既存挙動と完全互換とする。

## Consequences

- 単独比較では半減期を短くするほど win_accuracy・logloss が単調に悪化（重みなしが最良）。回収率は非単調（10年が最高、3年が最低）で分散が大きくノイズと区別できない。
- n_trials=10 の小さい探索予算での「最良パラメータ」は特定fold構成のノイズにフィットしただけで、標準splitのbootstrap CIでは baseline に劣った（過学習の典型パターン）。
- より大きな探索予算（n_trials=50〜100）での再検証の余地は残す。

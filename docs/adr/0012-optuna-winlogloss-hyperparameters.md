# ADR-0012: win_logloss最適化によるLightGBMハイパーパラメータ・half_life_daysをデフォルト採用

- Status: Accepted
- Date: 2026-08-01

## Context

[ADR-0010](./0010-time-decay-sample-weight-rejected.md) で回収率を目的関数にした Optuna 探索が標準splitへ汎化しなかったことを受け、目的関数を分散の大きい回収率から `win_logloss`（walk-forward平均、最小化）に変更して `tune --n-trials 30` を再実行した。

## Decision

trial #23 のパラメータ（`num_leaves=127, learning_rate=0.012807, min_child_samples=41, feature_fraction=0.5597`）と `half_life_days=1095` をデフォルトとして `model.py` の `_PARAMS`/`_RANK_PARAMS` に採用する。旧デフォルト（`num_leaves=63, learning_rate=0.05, min_child_samples=20, feature_fraction=0.8`, `half_life_days=None`）はCLIから明示的に上書き可能なまま残す。

## Consequences

- 標準splitで win_accuracy +0.90pt、win_logloss -0.0030、place_logloss -0.0071 と改善。recovery_rateは73.06%→72.92%とほぼ横ばい（誤差範囲、悪化ではない）。
- [ADR-0010](./0010-time-decay-sample-weight-rejected.md) とは異なり標準splitへの汎化に成功。目的関数を分散の小さいwin_loglossに変更した設計変更が機能した。
- 回収率自体は動いていないため、「儲かるようになった」ことの確認ではなく「確率推定精度が上がった」ことの確認である点に注意。

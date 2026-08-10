# ADR-0014: 馬主の全期間累積勝率フィーチャーを追加

- Status: Accepted
- Date: 2026-08-01

## Context

[ADR-0013](./0013-trainer-jockey-lifetime-win-rate.md) に続き、ノートブック分析軸14（馬主15.3pt差、循環性チェック済み）を特徴量化できないか検証した。エンティティキーは `horses.owner_id` ではなく入力率99.9%の `race_results.owner` 文字列を使用。ロジック・リーク防止方式は調教師・騎手と同一。

## Decision

`owner_prior_win_rate`, `owner_prior_mounts` の2カラムを採用する。

## Consequences

- 標準split・walk-forwardの両方でwin_logloss・place_loglossが改善。recovery_rateは誤差範囲の変動。
- Feature importanceで `owner_prior_win_rate` が全55特徴量中17位。懸念していた調教師との多重共線性による潰れ合いは発生せず、両方とも独立に寄与を保持。
- これで調教師・騎手・馬主の3エンティティの通算勝率が出揃った。bootstrap CIでの有意差検証は引き続き未実施。

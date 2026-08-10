# ADR-0013: 調教師・騎手の全期間累積勝率フィーチャーを追加

- Status: Accepted
- Date: 2026-08-01

## Context

ノートブック分析（`03_recovery_rate_by_condition.ipynb` 軸10・12）で調教師24.3pt差・騎手16.6pt差の歪みが見つかった（循環性チェック済み）。既存の `trainer_win_rate_last30`（直近30走）・`jockey_win_rate_venue_cond`（venue×course_type限定）とは別軸として、デビューからそのレース直前までの全期間累積勝率を追加できないか検証した。

## Decision

`trainer_prior_win_rate`, `trainer_prior_mounts`, `jockey_prior_win_rate`, `jockey_prior_mounts` の4カラムを既存フィーチャーと併存させる形で採用する。

## Consequences

- 標準splitでwin_logloss・place_loglossが改善。walk-forwardではrecovery_rateも+0.76pt改善（悪化した指標なし）。
- Feature importanceで `jockey_prior_win_rate` が全53特徴量中9位（既存の `jockey_win_rate_venue_cond` の10位を上回る）、`trainer_prior_win_rate` は22位（既存の `trainer_win_rate_last30` の43位を大きく上回る）。「全期間累積」が「直近30走」より有用な情報を持つことを示唆。
- bootstrap CIでの有意差検証は未実施のまま残る。

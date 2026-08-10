# モデル実験記録（索引）

特徴量・ハイパーパラメータ・戦略の採否判断は [ADR](./adr/) に記録している。本ファイルは時系列索引のみ。詳細な数値・生データは各 ADR、または `git log -p docs/experiments.md` で過去版を参照。

次フェーズの改善施策は [improvement_plan.md](./improvement_plan.md) を参照。

| 日付 | タイトル | 結果 | ADR |
|---|---|---|---|
| 2026-05-20 | leaky feature（finish_time_sec/odds/popularity）を除外 | Accepted | [ADR-0001](./adr/0001-remove-leaky-features.md) |
| 2026-05-20 | 先行指数フィーチャー追加 | Accepted | [ADR-0002](./adr/0002-leading-position-index-features.md) |
| 2026-05-20 | 上がり3ハロン相対順位フィーチャー追加 | Accepted | [ADR-0003](./adr/0003-last3f-relative-rank-features.md) |
| 2026-05-20 | 重賞グレード補完 | Accepted | [ADR-0004](./adr/0004-grade-backfill.md) |
| 2026-05-21 | 騎手×コース勝率・調教師直近30走勝率フィーチャー追加 | Accepted | [ADR-0005](./adr/0005-jockey-trainer-recent-features.md) |
| 2026-05-26 | 確率較正にIsotonic Regressionを採用 | Accepted | [ADR-0006](./adr/0006-isotonic-calibration.md) |
| 2026-05-27 | 距離変化・コース替わり・馬体重相対値・騎手乗り替わり・枠順×距離フィーチャー追加 | Accepted | [ADR-0007](./adr/0007-distance-course-weight-jockey-change-features.md) |
| 2026-05-27 | MC（Plackett-Luce）による単勝EV戦略拡張 | Rejected | [ADR-0008](./adr/0008-mc-win-prob-extension-deferred.md) |
| 2026-05-26〜08-02 | 7番人気以下タイの馬連・三連複・ワイドEV戦略 | Rejected | [ADR-0009](./adr/0009-longshot-quinella-trio-strategy-rejected.md) |
| 2026-07-30 | 時間減衰サンプルウェイト（half_life_days） | Rejected | [ADR-0010](./adr/0010-time-decay-sample-weight-rejected.md) |
| 2026-07-31 | Embeddingハイブリッド特徴量 | Rejected | [ADR-0011](./adr/0011-embedding-hybrid-rejected.md) |
| 2026-08-01 | win_logloss最適化によるLightGBMハイパーパラメータ・half_life_days採用 | Accepted | [ADR-0012](./adr/0012-optuna-winlogloss-hyperparameters.md) |
| 2026-08-01 | 調教師・騎手の全期間累積勝率フィーチャー追加 | Accepted | [ADR-0013](./adr/0013-trainer-jockey-lifetime-win-rate.md) |
| 2026-08-01 | 馬主の全期間累積勝率フィーチャー追加 | Accepted | [ADR-0014](./adr/0014-owner-lifetime-win-rate.md) |
| 2026-08-02 | 穴馬（7番人気以下）専用モデルへの分離 | Rejected | [ADR-0015](./adr/0015-longshot-specialized-model-rejected.md) |
| 2026-08-03 | 出走間隔フィーチャー追加（初回検証） | Superseded by ADR-0024 | [ADR-0016](./adr/0016-days-since-last-race-initial-rejected.md) |
| 2026-08-03 | 馬場状態別の適性統計（*_trackcond） | Rejected | [ADR-0017](./adr/0017-track-condition-affinity-rejected.md) |
| 2026-08-03 | クラス（格）変化フィーチャー追加 | Accepted | [ADR-0018](./adr/0018-class-level-change.md) |
| 2026-08-03 | 累積獲得賞金フィーチャー追加 | Rejected | [ADR-0019](./adr/0019-prior-earnings-rejected.md) |
| 2026-08-03 | 騎手×馬の組み合わせ成績フィーチャー追加 | Rejected | [ADR-0020](./adr/0020-jockey-horse-combo-rejected.md) |
| 2026-08-03 | レース内ペース予想フィーチャー追加 | Accepted | [ADR-0021](./adr/0021-in-race-pace-features.md) |
| 2026-08-03 | 重賞実績フラグフィーチャー追加 | Rejected | [ADR-0022](./adr/0022-graded-race-prior-flag-rejected.md) |
| 2026-08-03 | タイム偏差値（スピード指数）フィーチャー追加 | Accepted | [ADR-0023](./adr/0023-speed-index.md) |
| 2026-08-03 | 出走間隔フィーチャー追加（再検証） | Accepted, Supersedes ADR-0016 | [ADR-0024](./adr/0024-days-since-last-race-accepted.md) |
| 2026-08-03 | 新規候補4案（厩舎複数出走数・頭数正規化近走成績・斤量自己比較・騎手直近30走勝率） | Rejected | [ADR-0025](./adr/0025-batch4-candidates-rejected.md) |
| 2026-08-03 | 通算出走数フィーチャー追加 | Rejected | [ADR-0026](./adr/0026-career-starts-rejected.md) |
| 2026-08-09 | 血統適性統計（単勝勝率ベース） | Superseded by ADR-0028 | [ADR-0027](./adr/0027-pedigree-affinity-win-rate-rejected.md) |
| 2026-08-10 | 血統適性統計（複勝率＋縮小推定＋スピード指数、再設計） | Accepted, Supersedes ADR-0027 | [ADR-0028](./adr/0028-pedigree-affinity-place-rate-shrinkage-accepted.md) |
| 2026-08-10 | MC組合せ馬券展開のフェーズ2ゲート再検証（現行モデルでも単勝EV回収率100%未達） | Rejected | [ADR-0029](./adr/0029-mc-win-ev-gate-recheck-2026-08-rejected.md) |
| 2026-08-10 | `dam`フィーチャー除外（permutation importance検定で有意な寄与なしと判明） | Accepted | [ADR-0030](./adr/0030-dam-feature-removed.md) |

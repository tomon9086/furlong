# ADR-0024: 出走間隔（days_since_last_race）フィーチャーを採用（再検証）

- Status: Accepted, Supersedes ADR-0016
- Date: 2026-08-03

## Context

[ADR-0016](./0016-days-since-last-race-initial-rejected.md) の初回検証（朝実施、他特徴量採用前）は標準splitの回収率悪化のみで不採用と判定していたが、ユーザーから「Log Lossが悪化していないなら残してもいいのでは」との指摘を受け、`class_change`・レース内ペース予想・スピード指数（[ADR-0018](./0018-class-level-change.md)〜[ADR-0023](./0023-speed-index.md)）を採用した**現在の特徴量セットの上で**再検証した。同時に行った「不採用5案の全部乗せ」診断（[ADR-0017](./0017-track-condition-affinity-rejected.md)等5案を同時追加）では相互作用による改善は見られなかったため、本ADRは出走間隔1つだけを切り出して正式検証したもの。

## Decision

`days_since_last_race` を採用する（[ADR-0016](./0016-days-since-last-race-initial-rejected.md) の不採用判定を上書き）。

## Consequences

- 標準splitでの回収率差が朝の-1.81ptからほぼ誤差レベル（-0.10pt）まで縮小。既存特徴量セットが変わったことで本特徴量の限界的な寄与が変化したとみられる。
- Walk-forwardでは4指標すべてが改善（win_accuracy +0.40pt, recovery_rate +0.35pt, win_logloss・place_logloss改善）。
- 教訓: 特徴量の価値は既存の特徴量セットに依存して変わりうる。単独検証だけで不採用と判断するのは早計な場合がある。

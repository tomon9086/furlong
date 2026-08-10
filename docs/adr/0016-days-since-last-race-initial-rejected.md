# ADR-0016: 出走間隔（days_since_last_race）フィーチャー追加（初回検証）

- Status: Superseded by ADR-0024
- Date: 2026-08-03

## Context

「特徴量は多いほどいい」という提案を受け、既存の `distance_change`/`course_type_change`/`jockey_change`（前走比較）の枠組みに前走からの経過日数（休養明け・連闘の代理指標）を追加できないか検証した。比較対象は [ADR-0014](./0014-owner-lifetime-win-rate.md) 時点のbaseline。

## Decision

この時点では不採用とする（walk-forward検証には進めない）。

## Consequences

- 標準splitでLog Lossはごくわずかに改善したが、win_accuracy -0.16pt、recovery_rate -1.81ptと悪化。採用基準（Log Loss改善**かつ**回収率改善）を満たさず。
- 後日、`class_change`・レース内ペース予想・スピード指数（[ADR-0018](./0018-class-level-change.md)〜[ADR-0023](./0023-speed-index.md)）を採用した状態で再検証したところ結果が逆転し、[ADR-0024](./0024-days-since-last-race-accepted.md) で採用に切り替えた。特徴量の価値は既存の特徴量セットに依存して変わりうるという教訓。

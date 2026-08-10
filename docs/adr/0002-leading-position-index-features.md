# ADR-0002: 先行指数フィーチャー（avg_corner_last3/5, _cond）を追加

- Status: Accepted
- Date: 2026-05-20

## Context

[ADR-0001](./0001-remove-leaky-features.md) のベースラインに対し、先頭コーナー通過順位の直近3走・5走平均（先行指数）を追加できないか検証した。

## Decision

`avg_corner_last3/5` および `_cond`（同コース種別・同距離条件）版を採用する。

## Consequences

- recovery_rate 74.04% → 77.33%（+3.29pp）。win_accuracy・logloss はほぼ横ばいで、確率精度そのものよりも「推奨馬の選択」が改善した。
- 7番人気以下の回収率が 52.47% → 82.09% と大幅改善し、穴馬発見への寄与が大きかった。

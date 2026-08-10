# ADR-0021: レース内ペース予想（corner_style_race_rank / race_leader_count）フィーチャーを追加

- Status: Accepted
- Date: 2026-08-03

## Context

既存の `avg_corner_last3`（先行指数、shift(1)ベースでリーク対策済み）をレース単位で二次集計し、(1) `corner_style_race_rank`（レース内での先行タイプ順位）、(2) `race_leader_count`（レース内の先行馬密度）を追加できないか検証した。比較対象は[ADR-0018](./0018-class-level-change.md)採用後のbaseline。

## Decision

両フィーチャーを採用する。

## Consequences

- 標準splitでwin_logloss +0.0002とわずかに悪化する一方、place_logloss -0.0014と明確に改善という混在した結果だったためwalk-forwardで正式検証した。
- Walk-forwardでもplace_logloss -0.0011と改善が方向・大きさともに一貫（単発のノイズではなく再現性のある効果と判断）。win_accuracyも両方で改善、win_logloss・recovery_rateは実質横ばい。

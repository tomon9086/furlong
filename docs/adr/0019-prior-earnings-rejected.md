# ADR-0019: 累積獲得賞金（horse_prior_earnings）は追加しない

- Status: Rejected
- Date: 2026-08-03

## Context

`race_results.prize_money` をパースし、当該レースより前の全獲得賞金合計を追加できないか検証した。比較対象は[ADR-0018](./0018-class-level-change.md)採用後のbaseline。

## Decision

不採用とする。

## Consequences

- 標準splitではrecovery_rate +1.01ptと有望に見えたが、walk-forwardでは-1.15ptと逆転し再現しなかった。他指標も実質横ばい。
- 標準splitの改善は単一splitのノイズと判断（[ADR-0016](./0016-days-since-last-race-initial-rejected.md)と対照的に、こちらは複数フォールドで見ても効果なし）。
- 近走成績・調教師/騎手/馬主の勝率系フィーチャーと相関が強く（強い馬ほど賞金を稼ぐ）、既存特徴量で説明できる情報の言い換えだった可能性。

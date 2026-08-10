# ADR-0018: クラス（格）変化（class_level / class_change）フィーチャーを追加

- Status: Accepted
- Date: 2026-08-03

## Context

`races.race_condition`（レース条件の自由文）から正規表現でクラスレベル（0=新馬〜5=オープン、JRAの2019年呼称変更の新旧表記に対応）を抽出し、現在のクラス `class_level` と前走からの変化 `class_change` を追加できないか検証した。比較対象は[ADR-0014](./0014-owner-lifetime-win-rate.md)時点のbaseline。JRAレースの99.8%で抽出可能。

## Decision

`class_level`, `class_change` を採用する。

## Consequences

- 標準splitでwin_accuracy +0.26pt、win_logloss -0.0007、place_logloss -0.0026と明確に改善（[ADR-0016](./0016-days-since-last-race-initial-rejected.md)/[ADR-0017](./0017-track-condition-affinity-rejected.md)のノイズレベル±0.0001〜0.0003より明確に大きい）。recovery_rateは-2.38ptと悪化したが、Log Loss改善が明確なため不採用にはせずwalk-forwardへ進んだ。
- Walk-forwardではwin_accuracy +0.37pt、win_logloss -0.0009、place_logloss -0.0027と一貫して改善。recovery_rateの悪化(-0.70pt)はフォールド間変動幅（70〜84%）より小さく誤差範囲と判断。

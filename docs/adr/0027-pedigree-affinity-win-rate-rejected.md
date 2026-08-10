# ADR-0027: 血統適性統計（父馬・母父馬×コース種別の単勝勝率ベース）は追加しない

- Status: Superseded by ADR-0028
- Date: 2026-08-09

## Context

血統データ遡及補完完了（`horses.sire`/`dam`/`broodmare_sire` 全132,856頭で充足）を受け、父馬・母父馬のコース種別（×距離帯）別産駒単勝勝率を3パターン実装して検証した（`dam` は産駒数不足のため対象外）。

- パターンA: `sire_win_rate_cond`（父馬×コース種別）
- パターンB: `bms_win_rate_cond`（母父馬×コース種別）
- パターンC: `sire_win_rate_distance_cond`（父馬×コース種別×距離帯）

実装時、同一父馬の産駒（きょうだい）が同一レースに複数出走するケースで情報リークが発生することを発見し、`owner_prior_win_rate`（[ADR-0014](./0014-owner-lifetime-win-rate.md)）と同じ「日付単位で集計してから1日分ずらす」方式に修正して対応した。

## Decision

パターンA・B・Cいずれも不採用とする。

## Consequences

- 単体では win_accuracy・recovery_rate・win_logloss が改善して見えたが、place_loglossはA・Bで悪化。最も安全だったパターンCをwalk-forwardで正式検証したところ、win_logloss・place_loglossの変化が±0.00002とノイズレベルまで縮小し、recovery_rateの伸びも半分以下（+1.77pt→+0.76pt）に縮小。
- ペアード・ブートストラップ有意差検定（95%CI、10,000回）でwin_logloss・place_logloss・win_accuracyいずれも0を跨ぎ有意差なし（証拠不在であり、悪化の証明ではない）。
- 教訓: 単勝は稀事象で父馬あたりのサンプルが薄いと高分散になる。同一父馬の産駒が同一レースに複数出走する場合のリーク対策（日付単位集計）は今後この軸を再検討する際に活かせる。この診断が[ADR-0028](./0028-pedigree-affinity-place-rate-shrinkage-accepted.md)の再設計の出発点になった。

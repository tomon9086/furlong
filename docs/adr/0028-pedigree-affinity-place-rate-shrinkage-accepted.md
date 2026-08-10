# ADR-0028: 血統適性統計を複勝率＋縮小推定＋スピード指数で再設計し採用

- Status: Accepted, Supersedes ADR-0027
- Date: 2026-08-10

## Context

[ADR-0027](./0027-pedigree-affinity-win-rate-rejected.md)（単勝勝率ベース）不採用の診断「単勝は稀事象で父馬あたりのサンプルが薄いと高分散になる」を受け、(1) 発生率の高い複勝率への変更、(2) 少サンプルの極端値を抑える縮小推定（shrinkage: `(実測合計 + K×事前平均) / (件数 + K)`）、(3) 連続値であるスピード指数（[ADR-0023](./0023-speed-index.md)と同じ設計思想）ベースの適性指標、の3方向で再設計し、4候補（D+E: 父馬×コース種別複勝率, F: 父馬×コース種別スピード指数, G: 母父馬×馬場状態複勝率, D+E+F併用）を検証した。

## Decision

`sire_place_rate_cond`, `sire_progeny_mounts_cond`（D+E）と `sire_avg_speed_index_cond`（F）の組み合わせを採用する。母父馬×馬場状態版（G）は不採用。

## Consequences

- 標準split・walk-forwardともLog Lossが一貫して改善（[ADR-0027](./0027-pedigree-affinity-win-rate-rejected.md)の「単一splitでは良く見えたがwalk-forwardで消える」パターンとは異なる）。
- ペアード・ブートストラップ有意差検定（95%CI）でwin_logloss・place_logloss・win_accuracyすべて有意な改善を確認（D+E+F vs baseline）。
- 構成要素別の個別検定では `sire_avg_speed_index_cond`（F）単体のみ3指標とも有意、`sire_place_rate_cond`（D+E）単体は有意差なし。ただしF単体とD+E+Fの直接比較でD+E追加がwin_logloss・place_loglossを統計的に有意に上乗せ改善することを確認しており、D+Eは単体では無効だがFと組み合わせた際に相補的に効く（過学習ではなく本物の相互作用）と判断し、D+E+Fの組み合わせを維持する。
- 実際のレース（202610020811 小倉記念）で `predict` がエラーなく動作し、値が父馬ごとに妥当なばらつきを持つことを確認済み。`spec.md` に反映済み。
- 追試（2026-08-10）: [ADR-0027](./0027-pedigree-affinity-win-rate-rejected.md)で不採用にした単勝勝率ベース（ABC、縮小推定なし）をDEFに追加しても相乗効果はなく、むしろplace_loglossが統計的に有意に悪化した（ペアード・ブートストラップ, 95%CI [+0.000168, +0.001084]）。ABCはDEFの複勝率側と同じ「父馬×コース種別」軸の冗長な情報であり、D+E+Fで見られた「勝敗ベース×連続値スピード指数」という異なる情報次元の組み合わせとは性質が異なる。ABCの再導入は見送り、DEF単体の採用を維持する。

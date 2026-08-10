# TODO

> 完了したタスクは削除せず、チェックを付けてください。
> セクション内のタスクがすべて完了したら、セクションごと削除してください。

## 回収率改善（目標110%）

> 計画: [plan/prediction-accuracy-followup.md](./plan/prediction-accuracy-followup.md)
> 目的は精度でなく回収率。「割安な対象（EV > 1）を選んで買う」ベット選択が中核。

- [x] 較正を out-of-sample に修正: `split_by_date` を train/val/test 3分割にし、val で `calibrate_models`、test で評価する構成に変更する
- [x] Bootstrap CI 算出: `evaluation.py` に bootstrap 信頼区間関数を追加し、「EV≥2.0 × 7番人気以下 × 馬連」の 95% CI 下限が 100% を超えるか確認する
- [x] Walk-forward での馬連戦略安定性確認: 「堅実・大穴戦略の軸重複解消」セクションの再検証（walk-forward 5フォールドのプール bootstrap CI、EV閾値1.0〜2.5全域）で馬連48.7〜54.0%・CI上限最大83.9%と判明済み。全フォールド合算でも100%に届かないため、フォールド別の安定性を追加確認する意味はないと判断しクローズ（[ADR-0009](./adr/0009-longshot-quinella-trio-strategy-rejected.md) 参照）
- [x] Optuna によるハイパーパラメータ最適化: `num_leaves`, `learning_rate`, `min_child_samples`, `feature_fraction`, `half_life_days` を探索。評価指標は walk-forward 平均回収率 → n_trials=10 で実施。最良パラメータは walk-forward では baseline を上回ったが、標準split + bootstrap CI では逆に悪化し汎化しなかった（[experiments.md](./experiments.md) 参照）。n_trials を増やした再探索は今後の課題

## モンテカルロ着順シミュレーション

> 計画: [plan/ensemble-montecarlo.md](./plan/ensemble-montecarlo.md)
> 方針: 薄く実装して「ベースモデルにエッジがあるか」を当たり判定 → 結果次第で組合せ馬券へ展開する。MC はエッジを **増幅** するだけで、無いエッジは生み出さない点に注意。

### フェーズ3: 組合せ馬券（馬連・ワイド・三連複・三連単）への展開

> フェーズ2の判定で「単勝 EV > 100%」を確認できた場合のみ着手する。
> 2026-08-10、特徴量拡張後の現行モデルで再判定したが引き続き未達（[ADR-0029](./adr/0029-mc-win-ev-gate-recheck-2026-08-rejected.md)）。以下は着手しない。

- [ ] 馬券種ごとの確率算出関数を `simulation.py` に追加（馬連=1-2着の組合せ、ワイド=3着以内の任意2頭、三連複=1-2-3着の組合せ、三連単=1-2-3着の順列）
- [ ] `payoffs` テーブルから券種別の払戻を結合し、組合せ単位の EV を計算するユーティリティを `evaluation.py` に追加
- [ ] 組合せ馬券の EV 評価をバックテストに組み込み、券種 × EV閾値 × 人気帯のグリッドで回収率を測定（回収率改善フェーズ3 の `ev_filter_analysis` 拡張に MC 確率を入力として接続する）
- [ ] 三連単など組合せ爆発が起きる券種は、EV 上位 N 点で打ち切る方針と N の調整方法を spec.md に記録する
- [ ] 最良の券種・閾値の組合せを [experiments.md](./experiments.md) に記録

## 血統データの遡及補完

> 発端: `dam`（母馬）特徴量の重要度を walk-forward フォールド別に見たところ、2000〜2016年の
> フォールドでは 0%（一度も使われていない）で、2016年以降のフォールドで急に上位（1〜3位）に
> 跳ね上がるという不自然な階段状の変化があった。原因を調査したところ `horses.sire`/`dam`/
> `broodmare_sire` が2016年以前の馬でほぼ空だったことが判明。
>
> 原因は2つあった。(1) netkeiba が血統テーブルを馬詳細ページから専用ページ
> （`/horse/ped/{horse_id}/`）に分離しており、スクレイパーが追従できず新馬でも血統が
> 欠落し続けていた → **修正済み**（`scraper/scraper/client.py` の `get_horse_pedigree`・
> `parsers/horse.py` の `parse_pedigree`／`_parse_blood_table`）。(2) 1995〜2006年の馬
> （約87,000頭）はプロフィールページ自体が未取得のまま → 未着手（下記）。

- [x] 1995〜2006年の馬（`race_results.horse_id` にはあるが `horses` に存在しない約87,000頭）を `scraper.backfill_missing --horses-only` で遡及スクレイピングする。件数が多く対netkeibaリクエストが長時間・大量になるため、実行タイミング（負荷・レート制限への配慮）を検討してから着手する — 2026-08-09完了。`horses.sire`/`dam`/`broodmare_sire` 全132,856頭で充足確認済み（[[project_pedigree_backfill_status]]）
- [x] 遡及補完後、sire/dam/broodmare_sire の feature importance が古い期間の walk-forward フォールドでも安定するか再確認する — 2026-08-10、`evaluation.pedigree_permutation_importance_ci`（シャッフルによる log-loss 悪化幅の95% bootstrap CI検定、n_repeats=20）で再検証。当初のgain降順rankだけの目視比較は検定になっていなかったため置き換えた。結果: `sire`・`sire_place_rate_cond`・`sire_progeny_mounts_cond`・`sire_avg_speed_index_cond` は全5フォールド（フォールド1=2000〜2006年含む）・単勝/複勝モデル双方で常に有意（CI下限>0）。`broodmare_sire` も概ね有意（10セル中9セルで有意、複勝モデルのフォールド2のみ非有意）。当初問題だった「古いフォールドで重要度0%」の階段状変化は解消済みと確認。一方 `dam` は複勝モデルで全5フォールドとも非有意、単勝モデルでも5フォールド中2フォールド（3, 5）で非有意 — gain rankでは複勝モデル常に1位に見えていたが、held-outでの有意な予測寄与としては裏付けられなかった（高カーディナリティ categorical の gain 過大評価の可能性）
- [x] `dam` フィーチャーの要否を検証する: `evaluation.paired_bootstrap_model_comparison`（レース単位ペアードbootstrap、95%CI）を新規実装し、標準split・walk-forward双方で baseline と `dam` 除外モデルを比較。win_logloss・place_logloss・win_accuracyが両検証とも有意に改善、recovery_rateは有意差なし（悪化ではない）だったため除外を採用し `preprocessing.get_feature_columns` から削除。2026-08-10、詳細は [ADR-0030](./adr/0030-dam-feature-removed.md) 参照

## 堅実・大穴戦略の軸重複解消

> 発端: 2026-08-02 クイーンS予測で、`race.betting`（単勝・複勝・馬連・ワイド・三連複の軸、人気帯フィルタなしの純粋 top1）と「大穴」戦略が同一馬（馬番13）に収束した。
> 検証済み: 穴馬専用モデルで解消を試みたが baseline に精度で負けた（[experiments.md](./experiments.md) 参照）ため、原因は学習不足ではなく `output.py` の戦略選択ロジック（両戦略ともレース内 top1 を人気帯で振り分けているだけ）にあると判明。

- [x] 対応方針を決定: `race.betting` の単勝・馬連・ワイド・三連複（複勝を除く）に人気帯フィルタを追加し、top1 が7番人気以下の日は軸推奨を出さない（`_mark_recommended` の `top1_is_longshot` ガード）。「大穴」の選定基準を変える案（top1 以外の穴馬候補）は未検証の新戦略になり再バックテストが必要なため見送り。[spec.md](./spec.md) に確定仕様として反映済み
- [x] 7番人気以下×馬連・三連複を大穴の代替にできないか再検証: フェーズ4（2026-05-27）の単一splitグリッドで見えた高回収率（馬連132〜137%、三連複178%）は、現行モデルでの walk-forward プール bootstrap CI では再現せず（馬連48.7〜54.0%、三連複47.2〜54.1%、ワイド62.0〜70.1%、全閾値・全券種で CI上限100%未達）。単一splitの点推定が信用できない典型例だった。「大穴」は現状の単勝・EVフィルタなし設計のまま維持する。詳細は [experiments.md](./experiments.md) 参照
- [x] `race.betting`（軸）が top1 の人気帯フィルタで抑制される頻度を過去データで定量化する（top1 が7番人気以下になるレースの割合）— 2026-08-10、標準splitテスト期間（11,068レース）で `evaluate_by_popularity` を集計したところ、top1 が7番人気以下になるのは822レース（7.4%）。頻度は低く、ガードによる軸推奨の抑制は限定的と判断
- [x] `race.betting`（軸）を spec.md 上で「参考・未検証」として明示（実行時出力への反映は見送り。理由: betting.toml自体への反映はoutput.py修正が必要で、spec.mdだけの修正は開発側の保険に留まり実運用の見え方は変わらない点を確認した上で、今回はspec.mdのみで良いと判断）

## 特徴量拡張（バッチ検証）

> 計画: [plan/feature-expansion-2026-08.md](./plan/feature-expansion-2026-08.md)
> 各案は `train --no-walkforward` で baseline と比較 → 有望なものだけ walk-forward bootstrap CI で正式検証、というバッチ運用。

- [x] バッチ1-1: 出走間隔（`days_since_last_race`）— 初回不採用だったが、他特徴量採用後に再検証し採用に切り替え（walk-forwardで4指標全て改善。`spec.md` 反映済み）
- [x] バッチ1-2: 馬場状態別の適性統計（`*_trackcond`）— 検証済み・不採用（回収率悪化、Log Loss横ばい）
- [x] バッチ1-3: クラス（格）変化（`class_level`/`class_change`）— 検証済み・採用（`spec.md` 反映済み）
- [x] バッチ2-1: 累積獲得賞金（`horse_prior_earnings`）— 検証済み・不採用（walk-forwardで回収率悪化、標準splitの改善は再現せず）
- [x] バッチ2-2: 騎手×馬の組み合わせ成績（`jockey_horse_prior_win_rate`）— 検証済み・不採用（全指標が横ばい〜悪化、サンプル不足の疑い）
- [x] バッチ2-3: 血統の適性統計化 — 単勝勝率ベースの初回検証は不採用（ペアード・ブートストラップで有意差なし）。複勝率＋縮小推定＋スピード指数に再設計して再検証したところ、walk-forward・正式有意差検定（95%CI）とも win_logloss・place_logloss・win_accuracy すべてで有意な改善を確認し採用（`sire_place_rate_cond`/`sire_progeny_mounts_cond`/`sire_avg_speed_index_cond`）。`spec.md` 反映済み。詳細は [experiments.md](./experiments.md) 参照
- [x] バッチ3-1: レース内ペース予想（`corner_style_race_rank`/`race_leader_count`）— 検証済み・採用（`spec.md` 反映済み）
- [x] バッチ3-2: タイム偏差値（スピード指数、`avg_speed_index_last3`）— 検証済み・採用（標準split・walk-forwardとも4指標全て改善、本日最大の効果）
- [x] バッチ3-3: 重賞実績フラグ（`graded_win_prior_flag`）— 検証済み・不採用（全指標横ばい〜悪化、近走成績・クラス変化と重複の疑い）
- [x] バッチ4: 新規4案（厩舎複数出走・頭数正規化近走成績・斤量自己比較・騎手直近30走勝率）— 検証済み・全て不採用（Log Lossの変化はノイズレベル、accuracy・recoveryは軒並み悪化。詳細は [experiments.md](./experiments.md) 参照）
- [x] 通算出走数（`career_starts_prior`）— 検証済み・不採用（同上のパターン）

## predictor HTTP API

- [x] `furlong-predictor` の `pyproject.toml` に `uvicorn` / `fastapi` 依存を追加
- [ ] `predictor/predictor/api.py` を実装（`GET /health`・`GET /predict/{race_id}` エンドポイント）
- [ ] サーバ起動時にモデルを1回だけロードする仕組みを `api.py` に実装
- [ ] `docker-compose.yml` に api サービス（port 8000）を追加



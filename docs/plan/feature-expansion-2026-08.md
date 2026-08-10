# 特徴量拡張の検討（2026-08-03）

> このファイルは探索・議論の場です。決定前のアイデアや選択肢を自由に書いてください。
> 確定した仕様は `spec.md` に移してください。

---

## 背景

「特徴量は多いほどいい」という提案を受けたが、[[project_recovery_rate_goal]] の通り評価軸は回収率であり、本プロジェクトの過去実験（Embeddingハイブリッド、Optuna過学習）では特徴量・複雑さの追加が必ずしも改善に繋がらないことが繰り返し確認されている（`docs/experiments.md`）。そのため、候補は全部洗い出すが実装はバッチ単位で行い、都度 `train --no-walkforward` で baseline との差分を確認 → 効果が見えたものだけ walk-forward pooled bootstrap CI で正式検証 → `spec.md` へ昇格、という運用にする。

## 候補一覧（優先度順）

### バッチ1（実装優先度: 高、コスト: 低）

1. ~~**出走間隔（`days_since_last_race`）+ 休養明け/連闘フラグ**~~ — **再検証の結果、採用**（2026-08-03）。初回検証（他特徴量採用前）では標準splitの回収率悪化のみで不採用としたが、`class_change`・レース内ペース予想・スピード指数を採用した状態で再検証したところ、単一splitでの悪化はほぼ消え、walk-forwardでは4指標全てが改善。特徴量の価値は既存セットに依存するという教訓。詳細は [experiments.md](../experiments.md) 参照。`spec.md` に反映済み。
2. ~~**馬場状態別の適性統計**~~ — **検証済み・不採用**（2026-08-03）。標準splitで回収率が-1.26pt悪化、Log Lossは横ばい。詳細は [experiments.md](../experiments.md) 参照。コードはrevert済み。
3. ~~**クラス（格）変化**~~ — **検証済み・採用**（2026-08-03）。`races.grade` ではなく `race_condition`（自由文）からクラス序列を抽出する方式に変更（`grade` は重賞のみにしか付かないため）。標準split・walk-forwardの両方でwin_accuracy・Log Lossが改善。詳細は [experiments.md](../experiments.md) 参照。`spec.md` に反映済み。

### バッチ2（血統・相性系、コスト: 中）

4. ~~**累積獲得賞金**~~ — **検証済み・不採用**（2026-08-03）。標準splitでは回収率+1.01ptと有望に見えたが、walk-forwardでは-1.15ptと再現せず、他の指標も実質横ばい。既存の近走成績・勝率系フィーチャーと情報が重複していた可能性。詳細は [experiments.md](../experiments.md) 参照。コードはrevert済み。
5. ~~**騎手×馬の組み合わせ成績**~~ — **検証済み・不採用**（2026-08-03）。標準splitで全指標が横ばい〜悪化。同一馬×同一騎手の再騎乗自体が稀でサンプル不足だった可能性。詳細は [experiments.md](../experiments.md) 参照。コードはrevert済み。
6. ~~**血統の適性統計化**~~ — **検証済み・採用**（2026-08-10、再設計後）。初回（2026-08-09、単勝勝率ベース）は不採用（ペアード・ブートストラップ有意差検定で有意差なし）。単勝は稀事象でサンプルが薄いと高分散になる診断を受け、複勝率＋縮小推定（shrinkage）＋スピード指数ベースに再設計したところ、walk-forward・正式有意差検定（95%CI）とも一貫して有意な改善（win_logloss/place_logloss/win_accuracy）を確認し採用。`spec.md` に反映済み。詳細は [experiments.md](../experiments.md#血統適性統計再挑戦-複勝率縮小推定スピード指数の検証2026-08-10採用) 参照。

### バッチ3（コスト高 or 効果不確実、後回し）

7. ~~**レース内ペース予想**~~ — **検証済み・採用**（2026-08-03）。`avg_corner_last3` をレース内で二次集計し `corner_style_race_rank`（相対脚質順位）・`race_leader_count`（先行馬頭数）を追加。place_loglossの改善が標準split・walk-forward両方で一貫。詳細は [experiments.md](../experiments.md) 参照。`spec.md` に反映済み。
8. ~~**タイム偏差値（スピード指数）**~~ — **検証済み・採用**（2026-08-03）。当初想定した「コース・距離・馬場状態での正規化」ではなく「レース内z-score」方式に設計変更（他馬という一番厳密な比較対象を使うことで正規化問題を回避）。標準split・walk-forwardとも4指標全てが改善し、本日最大の効果。詳細は [experiments.md](../experiments.md) 参照。`spec.md` に反映済み。
9. ~~**重賞実績フラグ**~~ — **検証済み・不採用**（2026-08-03）。標準splitで改善した指標が一つもなく、既存の近走成績・クラス変化と情報が重複していた可能性。詳細は [experiments.md](../experiments.md) 参照。コードはrevert済み。

## 血統適性統計の実装パターン（2026-08-09、検証済み・不採用 → 2026-08-10 再設計で採用）

> ユーザーがipynbでの独自分析で血統が回収率向上に寄与する手応えを得ているため、複数パターンを個別実装し `train --no-walkforward` で計測してから組み合わせを決めた（バッチ4の個別検証と同じ運用）。**この単勝勝率ベースの設計自体は不採用**（詳細・数値は [experiments.md](../experiments.md#血統適性統計バッチ2-3の検証2026-08-09) 参照）だが、以下の設計方針・診断が2026-08-10の複勝率＋縮小推定＋スピード指数への再設計（[experiments.md](../experiments.md#血統適性統計再挑戦-複勝率縮小推定スピード指数の検証2026-08-10採用)、採用済み）の出発点になった。以下は初回設計時点の記録。

### 設計方針

既存の `jockey_win_rate_venue_cond`（`jockey_id × venue × course_type` でグルーピングし、日付シフトした累積勝率を出す方式）と同じパターンを流用する。グルーピングキーに `course_type`（レース自身の値）を含めることで、芝レースなら自動的にその馬の父馬の芝実績が、ダートレースならダート実績が引かれる。芝/ダートを別カラムに分ける必要がない。

### 候補パターン（個別に `get_feature_columns()` へ追加 → 計測 → 効果がなければrevert）

1. **パターンA: `sire_win_rate_cond` / `sire_progeny_mounts_cond`** — `sire × course_type` でグルーピングした産駒の累積勝率・累積出走数（日付シフトでリーク防止）。
2. **パターンB: `bms_win_rate_cond` / `bms_progeny_mounts_cond`** — `broodmare_sire × course_type` で同様。母父（BMS）はダート・スタミナ適性の経験則指標として知られるため父馬とは別軸で検証する。
3. **パターンC: `sire_win_rate_distance_cond` / `sire_progeny_mounts_distance_cond`** — `sire × course_type × distance_band`（`bracket_distance_avg_finish` と同じ4バンド: 0=~1400, 1=1401~1800, 2=1801~2200, 3=2201~）でグルーピングし、距離適性まで加味した勝率。

`dam`（母馬本体）は1頭あたりの産駒数が少なすぎて統計が安定しないため対象外。

### 検証プロセス（既存バッチと同じ）

1. 現行baseline（採用済み特徴量セット）で `train --no-walkforward` を実行し基準値を記録。
2. パターンA/B/Cをそれぞれ単独で追加し、baselineと比較（Log Lossが明確に改善/横ばいでないものは不採用）。
3. 有望なものだけ組み合わせて再計測し、walk-forward pooled bootstrap CIで正式検証。
4. 結果は [experiments.md](../experiments.md) に記録し、採用したものだけ `spec.md` の特徴量表に追記する。

## 検証プロセス（各バッチ共通）

1. 実装は非破壊的に追加（`get_feature_columns()` に列を追加するのみ。既存列は変更しない）。
2. `python -m predictor.main train --no-walkforward` を baseline（現行コード）→ 新特徴量ありコードの順に同一データスナップショットで実行し、`win_accuracy` / `win_logloss` / `place_logloss` / 単勝 top1 回収率を比較する（Embeddingハイブリッド実験と同じ比較軸）。
3. Log Loss が悪化する場合は不採用（回収率のみの改善は分散が大きく信頼できないという既存知見 [[project_recovery_rate_goal]] に基づく）。
4. Log Loss が改善または横ばいで回収率も改善している場合のみ、walk-forward pooled bootstrap CI（`python -m predictor.main train`、馬連・三連複・ワイド）で正式検証する。
5. 結果は `docs/experiments.md` に記録し、採用したものだけ `docs/spec.md` の特徴量表に追記する。

---

> 実装が完了した項目は `docs/spec.md` の該当セクションに移す。

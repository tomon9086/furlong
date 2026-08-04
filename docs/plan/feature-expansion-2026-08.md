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
6. **血統の適性統計化** — `sire`/`dam`/`broodmare_sire` を生カテゴリのままでなく、「父馬の産駒芝勝率」「父馬産駒の平均得意距離」等の集計統計に変換する。**実装着手前に保留**（2026-08-03）: `h.sire` の充足率が全体で約35%（2010年以降でも約66%）しかなく、`docs/todo.md` の血統データ遡及補完（1995〜2006年、未着手）が終わるまでは欠損が多すぎて正しく効果測定できない可能性が高いと判断。遡及補完完了後に再検討する。

### バッチ3（コスト高 or 効果不確実、後回し）

7. ~~**レース内ペース予想**~~ — **検証済み・採用**（2026-08-03）。`avg_corner_last3` をレース内で二次集計し `corner_style_race_rank`（相対脚質順位）・`race_leader_count`（先行馬頭数）を追加。place_loglossの改善が標準split・walk-forward両方で一貫。詳細は [experiments.md](../experiments.md) 参照。`spec.md` に反映済み。
8. ~~**タイム偏差値（スピード指数）**~~ — **検証済み・採用**（2026-08-03）。当初想定した「コース・距離・馬場状態での正規化」ではなく「レース内z-score」方式に設計変更（他馬という一番厳密な比較対象を使うことで正規化問題を回避）。標準split・walk-forwardとも4指標全てが改善し、本日最大の効果。詳細は [experiments.md](../experiments.md) 参照。`spec.md` に反映済み。
9. ~~**重賞実績フラグ**~~ — **検証済み・不採用**（2026-08-03）。標準splitで改善した指標が一つもなく、既存の近走成績・クラス変化と情報が重複していた可能性。詳細は [experiments.md](../experiments.md) 参照。コードはrevert済み。

## 検証プロセス（各バッチ共通）

1. 実装は非破壊的に追加（`get_feature_columns()` に列を追加するのみ。既存列は変更しない）。
2. `python -m predictor.main train --no-walkforward` を baseline（現行コード）→ 新特徴量ありコードの順に同一データスナップショットで実行し、`win_accuracy` / `win_logloss` / `place_logloss` / 単勝 top1 回収率を比較する（Embeddingハイブリッド実験と同じ比較軸）。
3. Log Loss が悪化する場合は不採用（回収率のみの改善は分散が大きく信頼できないという既存知見 [[project_recovery_rate_goal]] に基づく）。
4. Log Loss が改善または横ばいで回収率も改善している場合のみ、walk-forward pooled bootstrap CI（`python -m predictor.main train`、馬連・三連複・ワイド）で正式検証する。
5. 結果は `docs/experiments.md` に記録し、採用したものだけ `docs/spec.md` の特徴量表に追記する。

---

> 実装が完了した項目は `docs/spec.md` の該当セクションに移す。

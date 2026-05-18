# 実装計画メモ

> このファイルは探索・議論の場です。決定前のアイデアや選択肢を自由に書いてください。
> 確定した仕様は `spec.md` に移してください。

---

## 概要

競馬予想プログラムの実装計画を検討する。

## 検討事項

### データソース

- ~~どのレースデータを使うか？~~ → **netkeiba スクレイピングに決定** (`spec.md` 参照)
- 履歴データの取得期間は今後決める

### 予測アプローチ

~~検討中~~ → **LightGBM（勾配ブースティング）に決定** (`spec.md` 参照)

#### 検討した選択肢

- ルールベース → 精度に限界あり、採用しない
- 機械学習（特徴量エンジニアリング）
  - ロジスティック回帰 → 非線形の関係を捉えにくい、採用しない
  - ランダムフォレスト → 予測確率の精度がやや低い、採用しない
  - **XGBoost / LightGBM → 採用。大規模表形式データに強く、欠損値・カテゴリ変数を扱いやすい**
- ディープラーニング → 実装コスト高・データ前処理複雑、採用しない

#### 学習方針の決定（2026-05-18）

- 新レースデータが追加されるたびに**全量再学習**する方式を採用
  - 古いデータの重みを下げたい場合は学習期間を直近N年に絞る
  - 継続学習（`init_model`）より全量再学習の方が精度が安定するため
- データ分割は**時系列分割**（ランダム分割は未来リークが発生するため不採用）
  - 直近約2割（2024〜2025年）をテストデータとして性能評価に使用

### 出力形式

- 着順予測（1着・2着・3着）
- 勝率・複勝率の確率出力
- 推奨買い目

### 評価指標

- 回収率
- 的中率
- ランキング精度（NDCG など）

## アイデア・メモ

### DB スキーマ調査メモ（2026-05-18）

実際の DB（golem.tailc53cfd.ts.net / netkeiba DB）を調査して判明した事項。

#### テーブル名の違い（spec.md 初期版との差異）

| spec.md 初期版 | 実際のテーブル名 |
|---|---|
| `race_entries` | `race_results` |
| `payouts` | `payoffs` |
| （なし） | `jockeys`（騎手マスタ） |
| （なし） | `trainers`（調教師マスタ） |

#### 型・設計に関する注意点

- `races.date` は **varchar** で `YYYY/MM/DD` 形式。日付比較には `TO_DATE(date, 'YYYY/MM/DD')` が必要。
- `payoffs.payout` も varchar（カンマ入り文字列 `1,310` など）。数値計算時は文字列処理が必要。
- `race_results` には `updated_at` がない（`created_at` のみ）。
- `race_results` の数値系カラム（`horse_weight`, `horse_weight_diff`）は integer だが、それ以外（`odds`, `finish_time` など）は varchar。
- `race_results` に `horse_name`, `jockey_name`, `trainer_name` が非正規化で持たれている（JOIN なしで取得可能）。

#### 特徴量として使えそうなカラム

- `race_results.odds`・`popularity` — 市場評価
- `race_results.horse_weight`, `horse_weight_diff` — 馬体重・増減
- `race_results.weight_carried` — 斤量
- `race_results.last_3f` — 上がり3ハロン
- `race_results.passing_order` — 通過順（先行力指標）
- `races.distance`, `course_type`, `direction`, `track_condition` — レース条件
- `horses.sire`, `dam`, `broodmare_sire` — 血統情報

<!-- 自由にメモを追加してください -->

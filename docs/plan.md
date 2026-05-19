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

## 近走成績フィーチャーの実装方針（確定）

### 決定事項（2026-05-19）

- **集計ウィンドウ**: 直近3走 + 直近5走の2セット
- **条件フィルタ**: 全レース共通 + 同コース種別・同距離の両方を特徴量化
- **実装方式**: フェーズによって使い分ける
  - **学習時**: 全件ロード後に pandas rolling で集計（案B）
    - どちらも79万行転送が必要で差がないため、Python で完結する案Bが保守しやすい
  - **予測時（特定レース）**: SQL ウィンドウ関数 + `WHERE horse_id IN (...)` で対象馬のみ取得（案A）
    - 79万行 → 数十〜百行に削減でき、パフォーマンスが有意に向上する

→ 確定仕様は `spec.md` に記載。

---

## repository 共有パッケージの導入（検討中）

### 背景

- `scraper` が `Database` クラスと型定義（`types.py`）を持っている
- `predictor` も今後 DB アクセスが必要になる
- このまま進めると DB 接続コードと型定義が重複・乖離するリスクがある

### 方針

uv workspace の既存構成を活かし、`repository` パッケージを新設して共有層にする。

```
furlong/
├── pyproject.toml          # members に "repository" を追加
├── repository/             # 新設
│   ├── pyproject.toml      # name = "furlong-repository", psycopg 依存はここに集約
│   └── repository/
│       ├── __init__.py
│       ├── models.py       # 現 scraper/types.py の TypedDict 群を移動
│       └── database.py     # 現 scraper/database.py の Database クラスを移動
├── scraper/
│   ├── pyproject.toml      # furlong-repository = { workspace = true } を追加、psycopg 依存を削除
│   └── scraper/
│       ├── types.py        # 削除（models.py に統合）
│       └── database.py     # 削除（repository に移動）
└── predictor/
    ├── pyproject.toml      # furlong-repository = { workspace = true } を追加、psycopg 依存を削除
    └── ...
```

### メリット

- `psycopg` 依存が `repository` 側に一本化される
- 型定義（`HorseProfile` 等）が一元化され、scraper/predictor で同じモデルを使える
- predictor の DB アクセス実装時にゼロから書く必要がない

### 懸念点

- scraper 内の import パスが変わる（`from .types import ...` → `from repository.models import ...`）
- 現時点では predictor の DB アクセスは未実装のため、恩恵はまだ小さい

### 結論

→ 議論中。実施する場合は `spec.md` に移す。

### SQL 設計メモ（予測時用）

リーク防止のため `ROWS BETWEEN N PRECEDING AND 1 PRECEDING` を使い、当該レース自身を集計から除外する。
同日に複数レースがある場合の順序安定化のため `ORDER BY race_date, race_id` とする。
`last_3f` が数値以外（`'-'` など）の場合は NULL に変換して集計から除外する。

```sql
WITH base AS (
  SELECT
    rr.race_id,
    rr.horse_id,
    TO_DATE(r.date, 'YYYY/MM/DD') AS race_date,
    r.course_type,
    r.distance,
    rr.finishing_position::integer AS finishing_pos,
    CASE WHEN rr.last_3f ~ '^\d+\.?\d*$' THEN rr.last_3f::float ELSE NULL END AS last_3f_num
  FROM race_results rr
  JOIN races r ON rr.race_id = r.race_id
  WHERE rr.finishing_position ~ '^[0-9]+$'
)
SELECT
  race_id,
  horse_id,
  -- 全レース 直近3走
  AVG(finishing_pos) OVER (PARTITION BY horse_id
    ORDER BY race_date, race_id ROWS BETWEEN 3 PRECEDING AND 1 PRECEDING) AS avg_finish_last3,
  MIN(finishing_pos) OVER (PARTITION BY horse_id
    ORDER BY race_date, race_id ROWS BETWEEN 3 PRECEDING AND 1 PRECEDING) AS best_finish_last3,
  AVG(last_3f_num)   OVER (PARTITION BY horse_id
    ORDER BY race_date, race_id ROWS BETWEEN 3 PRECEDING AND 1 PRECEDING) AS avg_last3f_last3,
  -- 全レース 直近5走
  AVG(finishing_pos) OVER (PARTITION BY horse_id
    ORDER BY race_date, race_id ROWS BETWEEN 5 PRECEDING AND 1 PRECEDING) AS avg_finish_last5,
  MIN(finishing_pos) OVER (PARTITION BY horse_id
    ORDER BY race_date, race_id ROWS BETWEEN 5 PRECEDING AND 1 PRECEDING) AS best_finish_last5,
  AVG(last_3f_num)   OVER (PARTITION BY horse_id
    ORDER BY race_date, race_id ROWS BETWEEN 5 PRECEDING AND 1 PRECEDING) AS avg_last3f_last5,
  -- 条件別 直近3走
  AVG(finishing_pos) OVER (PARTITION BY horse_id, course_type, distance
    ORDER BY race_date, race_id ROWS BETWEEN 3 PRECEDING AND 1 PRECEDING) AS avg_finish_last3_cond,
  MIN(finishing_pos) OVER (PARTITION BY horse_id, course_type, distance
    ORDER BY race_date, race_id ROWS BETWEEN 3 PRECEDING AND 1 PRECEDING) AS best_finish_last3_cond,
  AVG(last_3f_num)   OVER (PARTITION BY horse_id, course_type, distance
    ORDER BY race_date, race_id ROWS BETWEEN 3 PRECEDING AND 1 PRECEDING) AS avg_last3f_last3_cond,
  -- 条件別 直近5走
  AVG(finishing_pos) OVER (PARTITION BY horse_id, course_type, distance
    ORDER BY race_date, race_id ROWS BETWEEN 5 PRECEDING AND 1 PRECEDING) AS avg_finish_last5_cond,
  MIN(finishing_pos) OVER (PARTITION BY horse_id, course_type, distance
    ORDER BY race_date, race_id ROWS BETWEEN 5 PRECEDING AND 1 PRECEDING) AS best_finish_last5_cond,
  AVG(last_3f_num)   OVER (PARTITION BY horse_id, course_type, distance
    ORDER BY race_date, race_id ROWS BETWEEN 5 PRECEDING AND 1 PRECEDING) AS avg_last3f_last5_cond
FROM base
```

---

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

---

## モデル評価結果（2026-05-19）

### ベースラインモデルの学習結果

`uv run python -m predictor.main train` を実行した結果。

- **データ分割**: 学習 617,609 行 / テスト 145,241 行（時系列分割）

| 指標 | 値 |
|---|---|
| `win_accuracy` | 0.3006（30.06%） |
| `recovery_rate` | 0.8004（80.04%） |
| `win_logloss` | 0.2169 |
| `place_logloss` | 0.4208 |

### 所感

- **win_accuracy 30%**: ランダム予測（≒ 1/出走頭数 ≈ 6〜7%）の約4〜5倍。特徴量が機能している。
- **recovery_rate 80%**: 単勝全賭けで投資額の80%しか戻らない水準。実用には100%超が必要。
- **win_logloss 0.2169**: 単勝は1着馬が1頭だけの極端な不均衡ラベルのため低値になりやすく、単独では判断しにくい。
- **place_logloss 0.4208**: 複勝（3着以内）はラベルが均衡しやすいため win_logloss より高くなるのは自然。

### 懸念点

- 人気馬（低オッズ）ばかりを推奨している可能性がある → 的中率が高くても回収率が低い原因になる。
- 人気別・オッズ帯別の的中率・回収率を追加分析すると実態が把握しやすい。

### 改善の方向性（検討中）

1. **特徴量の強化**: 枠順・距離適性・馬場状態・前走着差・コース実績・血統など
2. **買い目戦略の導入**: `win_prob × odds > 閾値` となる馬だけ購入する期待値ベースの絞り込み
3. **確率の正規化確認**: レース内 `win_prob` の合計が 1.0 になっているか検証
4. **評価指標の拡充**: 人気別回収率・NDCG など

---

## 学習・推論改善計画（2026-05-19）

ベースライン評価（win_accuracy=30%、recovery_rate=80%）を踏まえた改善方針。

### 1. 未使用特徴量の追加（即実施可能）

`preprocessing.py` ですでに計算済みだが `get_feature_columns()` に含まれていない：

| カラム | 説明 | 追加理由 |
|---|---|---|
| `finish_time_sec` | タイムを秒換算した値 | 馬の絶対的な走力を直接反映 |
| `first_corner_pos` | 最初のコーナー通過順 | 先行力の指標。展開適性に関係 |

→ `get_feature_columns()` に追記するだけで反映できる。

### 2. win_prob のレース内正規化

現状の LightGBM binary 出力はレース内合計が 1.0 にならない。

- **問題**: 出走頭数が多いレースで全馬の確率が低くなり、比較がしにくい
- **対策**: `predict()` 内で `win_prob / win_prob.sum()` をレース単位で実施
- **注意**: 正規化後も `place_prob` は independent なので別途検討

### 3. 人気別・オッズ帯別の評価指標を追加

回収率 80% の原因が「人気馬偏重」かどうかを確認するため。

追加する指標：

```
人気別 (1番人気 / 2-3番人気 / 4-6番人気 / 7番人気以下)
  - 推奨頻度（何レース中何回推奨されているか）
  - 的中率
  - 回収率

オッズ帯別 (1倍台 / 2-4倍 / 5-9倍 / 10倍以上)
  - 推奨頻度・的中率・回収率
```

→ `evaluation.py` に `evaluate_by_popularity()` 関数を追加する。

### 4. 期待値ベースの買い目絞り込み（推論側）

`win_prob × odds > threshold` の条件で推奨馬を絞り込む戦略。

- **仮説**: 人気馬（低オッズ）を避けることで回収率が改善する
- **実装方針**: `output.py` または推論フローに「期待値フィルタ」オプションを追加
- **閾値の探索**: 0.8〜1.5 の範囲でグリッドサーチしてテストデータで検証

### 5. モデルハイパーパラメータの見直し（後回し）

まず上記1〜4を実施して特徴量・評価基盤を整えてからチューニングする。

### 優先順位

| 優先度 | 項目 | 工数感 |
|---|---|---|
| 高 | 未使用特徴量の追加（#1） | 小（1行〜数行） |
| 高 | 人気別評価指標の追加（#3） | 中 |
| 中 | win_prob の正規化（#2） | 小 |
| 中 | 期待値フィルタ（#4） | 中 |
| 低 | ハイパーパラメータ調整（#5） | 大 |

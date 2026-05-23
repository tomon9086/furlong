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

## 未来レース予想機能（検討中）

### 背景・目的

現在の `predictor` は DB に結果が登録済みのレースのみ対象。
今週開催される（まだ結果が出ていない）レースを予想するには追加実装が必要。

### 必要な機能一覧

#### 1. 出馬表データの取得・保存

- **課題**: 出馬表ページ（出走馬・斤量・騎手が確定、着順なし）を DB に保存する仕組みがない
- **データソース候補**:
  - netkeiba の出馬表ページ（`/race/shutuba.html?race_id=XXXX`）
  - JRA 公式サイト（netkeiba にない場合のフォールバック）
  - → まず netkeiba に出馬表ページが存在するか調査が必要
- **実装案**:
  - `scraper` に `ShutsubaParser`（出馬表パーサー）を追加
  - 既存の `race_results` テーブルに着順 NULL で INSERT（または専用テーブルを新設）
  - コマンド: `uv run --package furlong-scraper python -m scraper shutuba <race_id>`

#### 2. 対象 race_id の特定方法

- **課題**: 今週のレース一覧から race_id を取得する手段がない
- **選択肢**:
  - A. 手動で race_id を調べて指定する（netkeiba URL から確認）
  - B. 開催スケジュールページをスクレイピングして race_id 一覧を取得する
  - → 初期実装は A（手動指定）で進め、慣れたら B を検討

#### 3. 前処理クエリの対応

- **課題**: 現在の `_QUERY` が `WHERE rr.finishing_position ~ '^[0-9]+$'` で結果確定済みのみに絞っている
- **実装案**:
  - 予測時クエリを別途用意し、指定 race_id の出走馬を取得
  - 近走成績は過去の確定レースから集計（plan.md のウィンドウ関数 SQL を活用）
  - `finishing_position` が NULL / 非数値の行も対象にできるよう条件を分岐

#### 4. 未登録馬のデータ自動補完

- **課題**: 出馬表に新馬など未登録の馬が含まれる場合、`horses` テーブルにデータがない
- **方針**: 出馬表取り込み時に `horses` テーブルを参照し、未登録馬は scraper で自動取得して補完
- **実装案**: `scrape_horse(horse_id)` を出馬表保存フローの中に組み込む

#### 5. 出力形式

確認済みの要求:
- 着順予測（1〜3着）
- 勝率・複勝率の確率
- 推奨買い目（馬連・三連複など）
- CSV への保存

→ 現在の `output.py` に推奨買い目生成を追加する必要がある

### 調査結果（2026-05-20）

- **netkeiba に出馬表ページあり** → `https://race.netkeiba.com/race/shutuba.html?race_id=XXXX` でアクセス可能
  - 例: `https://race.netkeiba.com/race/shutuba.html?race_id=202605021011&rf=race_list`
  - curl で直接取得可能（リダイレクトなし）。エンコーディングは EUC-JP（既存と同様）
  - ドメインが `db.netkeiba.com`（既存）ではなく `race.netkeiba.com` → `NetkeibaClient` に `get_shutuba` メソッドを追加する必要あり
- **JRA フォールバックは不要** → netkeiba で取得できることが確認できたため
- **race_id は手動指定で進める**（フェーズ1）

#### 出馬表ページの HTML 構造

**レース情報:**

| 情報 | セレクタ | 例 |
|---|---|---|
| レース名 | `h1.RaceName` | `オークス` |
| レース番号 | `.RaceList_Item01 .RaceNum` | `11R` |
| 発走時刻・コース | `div.RaceData01` | `15:40発走 / 芝2400m (左 B)` |
| 開催・頭数など | `div.RaceData02` | `2回 東京 10日目 ... 22頭` |
| グレード | `span.Icon_GradeType1` など | 既存パーサーと同じパターン |

→ `db.netkeiba.com` の `dl.racedata` とは構造が異なるため、`ShutsubaParser` に専用の `parse_race_info` が必要

**出走馬テーブル:**

- テーブル: `<table class="Shutuba_Table RaceTable01 ShutubaTable">`
- 馬行: `<tr class="HorseList" id="tr_{登録番号}">` — id の数字が登録番号

| td クラス | 内容 | 備考 |
|---|---|---|
| `Waku Txt_C` | 枠番 | 枠順確定前は空 |
| `Umaban Txt_C` | 馬番 | 枠順確定前は空 → `id="tr_XX"` から取得 |
| `HorseInfo` | 馬名 + horse_id | href `/horse/XXXX` から ID 抽出 |
| `Barei Txt_C` | 性齢 | `牝3` など |
| `Txt_C`（斤量列） | 斤量 | `55.0` など |
| `Jockey` | 騎手名 + jockey_id | href `/jockey/result/recent/XXXXX/` |
| `Trainer` | 厩舎名 + trainer_id | href `/trainer/result/recent/XXXXX/` |
| `Weight` | 馬体重(増減) | 前日発表前は空 |
| `Txt_R Popular` | オッズ | 発売前は `---.-` |
| `Popular Popular_Ninki Txt_C` | 人気 | 発売前は `**` |

→ `race_results` の既存カラムにほぼ対応。`finishing_position` / `finish_time` / `margin` / `passing_order` / `last_3f` は NULL になる

### 未解決の論点

（なし — 調査完了）

### 決定事項

- **出馬表データの保存先**: 既存の `race_results` テーブルに `finishing_position = NULL` で INSERT（案A）
  - `finishing_position` は NOT NULL 制約なし → スキーマ変更不要
  - `race.netkeiba.com` と `db.netkeiba.com` の race_id 形式は共通
  - 予測時は `finishing_position IS NULL` で出馬表データを識別できる

### 実装順序（暫定）

1. netkeiba 出馬表ページの構造調査・パーサー実装
2. 出馬表保存コマンド追加（`scraper shutuba <race_id>`）
3. 未登録馬の自動補完
4. 予測時クエリの分離（近走成績フィーチャーをウィンドウ関数で計算）
5. 推奨買い目出力の追加

---

## scrape_race / scrape_backfill における馬データの欠損問題（検討中）

### 背景

`scrape_shutuba` は出馬表取り込み時に未登録馬を自動補完しているが、
`scrape_race` および `scrape_backfill` には馬の補完ロジックが実装されていない。

そのため、`scrape_backfill` で過去レースを一括取得した場合、レース結果の `horse_id` が `horses` テーブルに存在しない状態になり得る。

実際に 2026-05-23 のバックフィル実行ログを確認したところ、騎手・調教師の補完ログは出ているが馬の補完ログは皆無だった（補完処理が存在しないため）。

### 問題の影響

- `race_results.horse_id` が `horses` テーブルに存在しない行がある可能性
- 学習・予測時に血統情報など `horses` テーブルのカラムを JOIN で参照する場合、NULL になるか行が欠落する

### 解決方針

`_supplement_jockeys_and_trainers` と同様に `_supplement_horses` ヘルパーを実装し、`scrape_race` と `scrape_backfill` の両方から呼び出す。

`RaceDetailParser.parse()` はすでに `row["馬ID"]` を含んでいるため、パーサーの変更は不要。

```python
def _supplement_horses(rows, db, client):
    horse_ids = list(dict.fromkeys(row["馬ID"] for row in rows if row.get("馬ID")))
    if not horse_ids:
        return
    existing_ids = db.get_existing_horse_ids(horse_ids)
    missing_ids = [hid for hid in horse_ids if hid not in existing_ids]
    if missing_ids:
        logger.info("未登録馬 %d 頭を補完します: %s", len(missing_ids), missing_ids)
        horse_parser = HorseParser()
        for horse_id in missing_ids:
            try:
                html = client.get_horse(horse_id)
                profile, _ = horse_parser.parse(html)
                db.save_horse(horse_id, profile)
            except Exception:
                logger.exception("馬 %s の取得に失敗しました。スキップします。", horse_id)
```

### 遡及修正方針

既存データも修正する。以下の2段階で対応する。

1. **コード修正**: `_supplement_horses` を実装し `scrape_race` / `scrape_backfill` に組み込む（再発防止）
2. **遡及スクリプト**: `race_results` に存在する `horse_id` のうち `horses` テーブルに未登録のものを洗い出し、1頭ずつ scrape して補完する1回限りのスクリプトを用意する

#### 遡及スクリプトの実装イメージ

```sql
-- 未登録馬の horse_id を列挙
SELECT DISTINCT horse_id
FROM race_results
WHERE horse_id IS NOT NULL
  AND horse_id <> ''
  AND horse_id NOT IN (SELECT horse_id FROM horses);
```

このクエリ結果を Python で受け取り、`scrape_horse(horse_id)` を順次呼び出す。
既存の `scrape_horse` 関数がそのまま使えるため、新たな関数実装は不要。

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

---

## 予測精度の問題分析（2026-05-20）

### 観察された症状

- 直近の重賞レースで予測が全然当たっていない
- 1番人気1着・2番人気2着・3番人気3着という順当な結果のレースでも予測が外れた
- 全 output CSV で `odds` / `ev` 列が空欄

### 原因の特定

#### 問題1: `odds` / `popularity` が予測時に常に NULL

`get_feature_columns()` には `odds` と `popularity` が含まれているが、予測時（出馬表スクレイピング直後）はオッズ発売前のため `---.-` / `**` → NULL になる。

- モデルはオッズ・人気を最重要フィーチャーとして学習しているはずだが、推論時はこれらが欠損しているためほぼ機能していない
- 実際の予測確率がほぼ一様分布に近い（18頭で 3.4%〜7.0%、均一なら 5.6%）ことがその証拠

#### 問題2: `finish_time_sec` / `first_corner_pos` がリークフィーチャー

これらは**当該レースの結果**から計算される値（タイム・通過順）。

- 学習時：全馬で非 NULL（過去の確定レースから取得）→ モデルが重視して学習
- 推論時：常に NULL（レースはまだ行われていない）
- → 学習時と推論時でフィーチャーの存在パターンが大きく乖離し、予測品質が劣化する
- 厳密には「リーク」ではなく「訓練/推論フィーチャー不一致（train-serve skew）」

#### 問題3: 重賞は荒れやすく少数データ

- 学習データ内の重賞（GI/GII/GIII）は全体の 4.4%（2,498 レース）のみ
- 重賞の平均単勝配当は 1,118 円（平場 1,002 円より高い）→ 波乱が多く予測が難しい
- 重賞固有のパターン（騎手の戦術変化・一線級同士の初対戦など）が学習不足

### 方針の整理（2026-05-20 更新）

#### オッズ・人気を特徴量にすべきか？ → **使うべきでない（or 慎重に）**

オッズは「市場参加者全員の予測の集約」であり、それをそのまま学習すると：

- モデルが「市場の総意を再現するだけ」になる
- 市場の期待回収率 ≈ 100% − 控除率（≒25%）= **75〜80%** が理論上限
- モデルが市場と同じ判断をするなら、どう転んでも 80% 以上にはなれない

→ 市場より先に情報を持っているフィーチャーを使ってこそ 100% 超えが狙える。
→ `odds` / `popularity` は特徴量から**除外**する方向で検討する。

#### `finish_time_sec` / `first_corner_pos` → **除外必須（評価指標が偽物）**

これらは「当該レースの実際の結果」から計算される値。

- 学習・テスト時：全馬で非 NULL → モデルが「速いタイムの馬が勝つ」「先行した馬が勝つ」を学習（自明、かつ循環）
- 推論時：NULL（レース未走行）
- 現在の「回収率 110%」はこの循環論法による **偽の指標**

→ 除外後は回収率が 80% 台前後まで落ちると予想されるが、それが現実の出発点。

#### 100% 超えを狙えるフィーチャー候補（市場に先行できる可能性あり）

| フィーチャー | 概要 | 実装難度 |
|---|---|---|
| 先行指数（過去走 first_corner_pos の集計値） | 直近3走の平均先行順位 → 先行馬が多数いるレースでの枠順相性 | 低 |
| 上がり3ハロン相対順位 | `last_3f` の絶対値でなく、そのレース内での順位の履歴 | 中 |
| クラス変化 | 前走比での格上げ/格下げ（条件戦クラス番号の差分） | 中 |
| 騎手×コース勝率 | `jockey_id × venue × course_type` の過去勝率 | 中 |
| 調教師近況勝率 | `trainer_id` の直近 30 走勝率 | 中 |
| 血統×距離適性 | 父系×距離帯の過去平均着順 | 高 |
| ペース適性 | 出走馬全員の先行指数から推定ペース × 各馬のペース適性 | 高 |

#### 対処優先順位

1. **`finish_time_sec` と `first_corner_pos` を特徴量から除外し再学習** → 評価指標をリセット
2. **`odds` / `popularity` も除外して再評価** → 真の実力値を把握
3. **先行指数（過去走 first_corner_pos の集計）を追加** → 実装コストが低い割に効果が期待できる
4. **重賞フラグ補完** → `race_name` から `(GI)/(GII)/(GIII)` を抽出して `grade` カラムを埋める

<!-- 自由にメモを追加してください -->

---

> 実験結果は [experiments.md](./experiments.md) を参照。
>
> 次フェーズの改善計画は [improvement_plan.md](./improvement_plan.md) を参照。

---

## scraper 定期実行機能（検討中）

### 背景・目的

現状の scraper はすべて手動コマンドで実行している。
レース結果・馬・騎手・調教師データを日次で自動収集できるようにしたい。

### 実行フロー（案）

エラーでデータが欠損した場合でも次回実行時に自動補完できるよう、**取得開始日を固定せず DB の最新レース日から差分を取得する**方式を採用する。

スケジュールは役割ごとに2本立てとする。

```
[バッチ 1] 毎日 14:00 (日本時間)  ← 枠順確定(前日11時)・調教タイム(前日13時)が揃った後
scrape_shutuba_upcoming()
  ├─ RaceListParser で翌日以降の未取得レースを検索
  └─ 各 race_id について shutuba ページを取得・保存
        └─ 未登録馬は scrape_horse() で自動補完

[バッチ 2] 毎日 22:00 (日本時間)  ← 全レース終了後
scrape_incremental()
  ├─ DB から MAX(races.date) を取得（= 最終取得済み日付）
  ├─ 最終取得済み日付〜今日の範囲で RaceListParser にレース一覧を問い合わせ
  ├─ DB に未登録の race_id だけに絞る（既存の get_existing_race_ids() を流用）
  ├─ 各 race_id について
  │     ├─ RaceDetailParser でレース結果を保存
  │     └─ race_results に登場した horse_id を抽出
  │           └─ horses テーブルに未登録の馬を scrape_horse() で補完
  └─ (将来) 騎手・調教師も同様に補完
```

**netkeiba の更新スケジュール（参考）:**

| 情報 | 更新タイミング |
|---|---|
| 出走確定 | 木曜19時頃 |
| 枠順確定 | **レース前日11時頃** |
| 調教タイム | レース前日13時頃 |
| レース結果・払戻 | レース後30秒〜10分 |

→ バッチ1（14:00）は枠順・調教タイムが揃った後に取得できる。

**エラー耐性のポイント:**
- 途中でクラッシュしても「DB にないレース = 未取得」として次回実行時に再取得される
- 日付固定方式（昨日分のみ）だと、当日エラー → その日のデータが永久に欠損するリスクがあった

### スケジューラの実装方式（候補）

| 方式 | メリット | デメリット | 推奨度 |
|---|---|---|---|
| **APScheduler** | Python コード内で完結・Docker 追加不要 | プロセスが落ちるとスケジュールも止まる | ◎ |
| OS/Docker cron | シンプル・実績あり | Python 環境の呼び出しが煩雑 | ○ |
| Celery + Broker | タスク管理・リトライが充実 | Redis/RabbitMQ など別サービスが必要 | △（過剰） |

→ **APScheduler を採用する方向で検討**。`scheduler/` パッケージ（または scraper 内の `scheduler.py`）として実装する。

### 未解決の論点

- [ ] 取得開始日の初期値: DB が空のとき `MAX(races.date)` が NULL になる → フォールバック日付をどう設定するか
- [ ] 騎手・調教師の自動補完: 現状 jockey/trainer パーサーが未実装。backfill フローに含めるか、別タスクにするか
  - `jockeys` / `trainers` テーブルはスキーマに存在するが、`scraper/` に対応パーサーがない
- [ ] ログ・アラート: 定期実行の結果をどこに記録するか

### 決定事項

- **バッチ構成**: 2本立て
  - バッチ1（14:00）: `scrape_shutuba_upcoming()` — 翌日の出馬表を取得（枠順・調教タイム確定後）
  - バッチ2（22:00）: `scrape_incremental()` — 当日レース結果を差分取得

### 実装ステップ（暫定）

1. `scrape_incremental()` 関数を `scraper/main.py` に追加（手動実行もできるよう開始日を引数でオーバーライド可能に）
2. `scrape_shutuba_upcoming()` 関数を `scraper/main.py` に追加（翌日の未取得出馬表を検索して保存）
3. APScheduler で 2 つのバッチを 14:00 / 22:00 に呼び出す `scheduler.py` を実装
4. Docker サービス（`docker-compose.yml`）に scraper デーモンを追加
5. 騎手・調教師パーサーを実装して補完フローに組み込む（後回し可）

---

## predictor HTTP API（検討中）

### 背景・目的

現状の predictor は CLI（`python -m predictor.main predict <race_id>`）でのみ利用できる。
HTTP API 化することで外部サービス・フロントエンドなどから予測結果を取得できるようにしたい。

### フレームワーク

**FastAPI** を採用（確定）

- 型安全・自動ドキュメント（Swagger UI）・非同期対応
- 既存の Python 環境に追加しやすい

### エンドポイント設計（案）

#### `GET /health`

サービスの死活確認。

```json
{ "status": "ok" }
```

#### `GET /predict/{race_id}`

指定レースの予測結果を返す。

**レスポンス例（案）:**

```json
{
  "race_id": "202506050811",
  "predictions": [
    {
      "horse_number": 1,
      "horse_name": "ドウデュース",
      "win_prob": 0.312,
      "place_prob": 0.618,
      "win_rank": 1,
      "place_rank": 1
    },
    ...
  ]
}
```

**エラーケース:**

| 状況 | HTTP ステータス | 挙動 |
|---|---|---|
| 出馬表が DB に未登録 | 404 | エラーメッセージを返す（自動取得はしない） |
| モデルファイルが存在しない | 503 | エラーメッセージを返す |

### モデルのロード戦略

- **サーバ起動時に1回だけロード**してメモリに保持する（リクエストごとのロードは重い）
- モデルディレクトリが更新された場合は再起動が必要（または `/reload` エンドポイントを追加）

### 実装構成（案）

```
predictor/
└── predictor/
    ├── main.py         # 既存 CLI エントリーポイント
    ├── api.py          # FastAPI アプリ定義（新設）
    ├── model.py        # 既存（モデルロード・推論）
    └── ...
```

起動コマンド（案）:
```
uv run --package furlong-predictor uvicorn predictor.api:app --host 0.0.0.0 --port 8000
```

### 決定事項

- `/predict/{race_id}` で出馬表が DB に未登録の場合は **404 を返す**（API 内で自動スクレイプしない）
  - 出馬表は scraper バッチ1（`scrape_shutuba_upcoming()`、毎日14:00）で事前に自動取得されるため、通常は DB に揃っている想定
- レスポンス形式: `output.print_prediction()` の出力に近い形（`win_prob`・`place_prob`・順位など）
- Docker サービスとして **常駐**（`docker-compose.yml` に追加）
- `uvicorn`（FastAPI を動かす ASGI サーバ）は `furlong-predictor` の `pyproject.toml` に依存追加

---

## 本番デプロイ構成 `docker-compose.prod.yml`（検討中）

### 背景・目的

predictor HTTP API・scraper デーモン・DB を本番環境でコンテナとして常時稼働させる。
開発用 `docker-compose.yml` とは別に `docker-compose.prod.yml` を用意して本番設定を定義する。

### サービス構成

| サービス | 内容 | restart ポリシー |
|---|---|---|
| `db` | PostgreSQL 16 | `always` |
| `api` | predictor FastAPI サーバー | `always` |
| `scraper` | APScheduler を使った定期スクレイピングデーモン | `always` |

### 開発用との主な差分

| 設定 | 開発用 (`docker-compose.yml`) | 本番用 (`docker-compose.prod.yml`) |
|---|---|---|
| db ポート公開 | ○（ホスト直接接続のため） | ✗（コンテナ内部のみ） |
| restart | `unless-stopped` | `always` |
| api サービス | なし | あり（port 8000） |
| scraper サービス | なし | あり（デーモン） |

### 未解決の論点

- [ ] api の Dockerfile 作成（`predictor/Dockerfile` を新設）
- [ ] scraper デーモン（APScheduler）の Dockerfile 作成（`scraper/Dockerfile` を新設）
- [ ] 環境変数の管理方法（本番では `.env` ファイルではなくシークレット管理ツールが望ましい）
- [ ] HTTPS 対応（リバースプロキシ / Nginx 等の前段配置）
- [ ] モデルファイルをどう渡すか（ボリュームマウント or イメージに埋め込み）

### 決定事項

- `docker-compose.prod.yml` を新設し、本番構成のみを定義する
- db のポートはホストに公開しない（コンテナ内ネットワークのみ）
- 全サービスの restart ポリシーを `always` に設定
- db の healthcheck を定義し、api/scraper は `service_healthy` を待ってから起動する
- モデルファイルは `predictor/models/` をボリュームマウントして渡す

### 実装ステップ

1. `docker-compose.prod.yml` を作成（db・api・scraper の骨格）← **完了**
2. `predictor/Dockerfile` を作成（FastAPI + uvicorn で起動）
3. `scraper/Dockerfile` を作成（APScheduler デーモンとして起動）
4. `predictor/predictor/api.py` を実装（「predictor HTTP API」セクション参照）
5. `scraper/scraper/scheduler.py` を実装（「scraper 定期実行機能」セクション参照）

---

## DB バックアップ（検討中）

### 背景・目的

- 本番 DB（PostgreSQL 16）はコンテナで稼働し、ポートはホスト非公開
- 障害・誤操作によるデータロストに備えて定期バックアップを行いたい
- **保持世代**: 7日分（7日より古いファイルは自動削除）
- **バッチ方式**: scraper の APScheduler と同じく Docker コンテナで定期実行

---

### 論点1: バックアップ先

本番 DB ポートが非公開のため `pg_dump` はコンテナ内から実行する必要がある。
バックアップファイルの置き先として以下の候補がある。

| 候補 | 概要 | メリット | デメリット |
|---|---|---|---|
| **A: ホスト bind mount** | コンテナ内で dump → ホストディレクトリへマウント | シンプル・追加コストなし | サーバごと消えると失う |
| **B: S3 / GCS（クラウド）** | dump → `aws s3 cp` / `gsutil cp` でアップロード | 耐障害性が高い・別サーバ復旧に使える | クラウド認証設定が必要 |
| **C: A + B の併用** | ローカルに保存しつつクラウドにも転送 | 両方の利点を享受 | 設定がやや複雑 |

**→ 決定: A（ホスト bind mount）から始め、将来的にクラウド対応できる設計にする**

---

### 論点2: バックアップコンテナの構成

scraper と同様の APScheduler 方式を基本としつつ、以下の選択肢がある。

#### 案1: 専用 `backup` Docker サービスを追加

```yaml
backup:
  image: postgres:16-alpine   # pg_dump が同梱されている
  restart: always
  environment:
    PGPASSWORD: ${POSTGRES_PASSWORD}
  volumes:
    - ./backup:/backup        # ホストへ bind mount（バックアップ先が A の場合）
  networks:
    - backend
  depends_on:
    db:
      condition: service_healthy
  # シェルスクリプト or Python + APScheduler でスケジューリング
```

- **メリット**: `pg_dump` が既存イメージに含まれており追加インストール不要
- **デメリット**: サービスが増える（管理対象が増える）

#### 案2: scraper コンテナに同居

- scraper の APScheduler にバックアップジョブを追加
- バックアップのために scraper に `pg_dump` が使える環境が必要（追加インストールか、Python の `subprocess` 呼び出しで `pg_dump` バイナリを使う）
- **メリット**: サービスを増やさなくて済む
- **デメリット**: scraper と backup の責務が混在する

#### 案3: ホスト cron + docker exec

```sh
# crontab
0 3 * * * docker exec db pg_dump -U furlong furlong | gzip > /backup/furlong_$(date +\%Y\%m\%d).sql.gz
```

- **メリット**: Docker 設定不要・最もシンプル
- **デメリット**: scraper のバッチ方式（APScheduler in Docker）と統一されない

**→ 決定: 案1（専用 `backup` Docker サービス）を採用**

---

### 論点3: バックアップ形式・スクリプト構成

| 形式 | コマンド | 特徴 |
|---|---|---|
| プレーンSQL（gzip圧縮） | `pg_dump \| gzip` | 人間が読みやすい・どの環境でも復元しやすい |
| カスタム形式 | `pg_dump -Fc` | 圧縮済み・差分リストア可能・やや高機能 |

**ファイル命名案**: `furlong_YYYYMMDD_HHMMSS.sql.gz`

**世代管理（7日）**: `find /backup -name "*.sql.gz" -mtime +7 -delete`

---

### 未解決の論点

_なし（全論点決定済み）_

### 決定事項

- 保持世代: **7日分**（`find /backup -name "*.sql.gz" -mtime +7 -delete`）
- バックアップ先: **ホスト bind mount**（`./backup:/backup`）。将来クラウド対応できる設計に
- コンテナ構成: **専用 `backup` Docker サービス**（`postgres:16-alpine` ベース）
- バックアップ形式: **プレーンSQL + gzip 圧縮**（`.sql.gz`）
- ファイル命名: `furlong_YYYYMMDD_HHMMSS.sql.gz`
- スケジューラ: **シェルスクリプト + `crond`**（Alpine 内蔵）
- 実行時刻: **毎日深夜3:00**（レース結果取得バッチ 22:00 の後）
- 失敗通知: **ログのみ**（`docker logs` で確認）。将来アラート追加できる設計に

### 実装ステップ

1. `backup/backup.sh` を作成（`pg_dump | gzip` → `/backup/` に保存、7日以上古いファイルを削除）
2. `backup/crontab` を作成（`0 3 * * * /backup.sh`）
3. `backup/Dockerfile` を作成（`postgres:16-alpine` ベース、crontab を組み込む）
4. `docker-compose.prod.yml` に `backup` サービスを追加

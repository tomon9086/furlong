# 仕様書

> このファイルには `plan.md` での議論を経て**確定した**仕様のみを記録します。
> 未確定の事項は `plan.md` に記載してください。

---

## プロジェクト概要

netkeiba からレース・馬・払い戻しデータをスクレイピングし、PostgreSQL に蓄積した上で競馬予想を行うシステム。

## 機能要件

- netkeiba のレースページから以下のデータを取得・保存する
  - レース情報（日程・競馬場・距離・グレードなど）
  - レース結果・出走馬情報（騎手・斤量・馬体重・オッズ・着順など）
  - 馬マスタ（馬名・性別・生年月日・調教師など）
  - 騎手マスタ（名前・所属・生年月日・初免許年）
  - 調教師マスタ（名前・所属・生年月日・初免許年）
  - 払い戻し（券種・組み合わせ・払い戻し金額）
- 蓄積データを元に予想結果を出力する
  - 予測モデル: **LightGBM** （勝ちモデル: `lambdarank`、複勝モデル: `binary` の2モデル構成）
  - 学習方式: 新データ追加時に全量再学習
  - データ分割: 時系列分割（直近約2割をテストデータとして性能評価）
  - 確率較正: IsotonicRegression または Platt Scaling（LogisticRegression）で後段較正

## 非機能要件

> TODO: 確定した非機能要件をここに記載する

## アーキテクチャ

### モノレポ構成

```
furlong/
├── docker-compose.yml   # PostgreSQL 起動設定
├── .env.example         # 環境変数テンプレート
├── scraper/             # netkeiba スクレイパー (Python)
├── predictor/           # 予想プログラム (Python)
├── repository/          # 共有データモデル・DB アクセス層 (Python)
└── db/                  # テーブル定義 SQL
    └── schema.sql       # 全テーブル定義（sqldef で管理）
```

### DB

- **RDBMS**: PostgreSQL 16
- **起動**: Docker (`docker-compose.yml`)
- スキーマは `db/schema.sql` で管理し、[psqldef](https://github.com/sqldef/sqldef) で冪等適用する
  - Docker 起動時: `docker-entrypoint-initdb.d` 経由で自動実行（初回のみ）
  - スキーマ変更時: `psqldef -U $POSTGRES_USER -h localhost $POSTGRES_DB < db/schema.sql`

## データ仕様

### テーブル一覧

| テーブル | 内容 | 件数（参考） |
|---|---|---|
| `horses` | 馬マスタ | 約 129,000件 |
| `jockeys` | 騎手マスタ | 約 1,000件 |
| `trainers` | 調教師マスタ | 約 1,100件 |
| `races` | レースマスタ | 約 55,700件 |
| `race_results` | レース結果・出走馬情報 | 約 790,000件 |
| `payoffs` | 払い戻し | 約 587,600件 |
| `pre_race_odds` | 事前オッズ（締切前スクレイプ） | ― |

### データ収録期間

- **races.date**: 1995/01/05 〜 2025/12/28

### テーブル定義

#### `horses` — 馬マスタ

| カラム | 型 | NOT NULL | 説明 |
|---|---|---|---|
| `horse_id` | varchar(20) | ✓ | **PK**。netkeiba の馬ID |
| `horse_name` | varchar(100) | | 馬名 |
| `sex` | varchar(10) | | 性別 |
| `coat_color` | varchar(20) | | 毛色 |
| `birthday` | varchar(20) | | 生年月日 |
| `trainer_name` | varchar(50) | | 調教師名（非正規化） |
| `trainer_id` | varchar(20) | | 調教師ID（`trainers.trainer_id` 参照） |
| `owner` | varchar(100) | | 馬主名 |
| `owner_id` | varchar(20) | | 馬主ID |
| `breeder` | varchar(100) | | 生産者名 |
| `birthplace` | varchar(50) | | 産地 |
| `sire` | varchar(100) | | 父馬名 |
| `dam` | varchar(100) | | 母馬名 |
| `broodmare_sire` | varchar(100) | | 母父馬名 |
| `raw_data` | text | | スクレイピング生データ（JSON） |
| `created_at` | timestamp | ✓ | 作成日時 |
| `updated_at` | timestamp | ✓ | 更新日時 |

#### `jockeys` — 騎手マスタ

| カラム | 型 | NOT NULL | 説明 |
|---|---|---|---|
| `jockey_id` | varchar(20) | ✓ | **PK**。netkeiba の騎手ID |
| `jockey_name` | varchar(50) | | 騎手名 |
| `affiliation` | varchar(50) | | 所属 |
| `birthday` | varchar(20) | | 生年月日 |
| `first_license_year` | varchar(10) | | 初免許年 |
| `raw_data` | text | | スクレイピング生データ（JSON） |
| `created_at` | timestamp | ✓ | 作成日時 |
| `updated_at` | timestamp | ✓ | 更新日時 |

#### `trainers` — 調教師マスタ

| カラム | 型 | NOT NULL | 説明 |
|---|---|---|---|
| `trainer_id` | varchar(20) | ✓ | **PK**。netkeiba の調教師ID |
| `trainer_name` | varchar(50) | | 調教師名 |
| `affiliation` | varchar(50) | | 所属 |
| `birthday` | varchar(20) | | 生年月日 |
| `first_license_year` | varchar(10) | | 初免許年 |
| `raw_data` | text | | スクレイピング生データ（JSON） |
| `created_at` | timestamp | ✓ | 作成日時 |
| `updated_at` | timestamp | ✓ | 更新日時 |

#### `races` — レースマスタ

| カラム | 型 | NOT NULL | 説明 |
|---|---|---|---|
| `race_id` | varchar(20) | ✓ | **PK**。12桁の数字文字列（例: `199505010201`） |
| `race_name` | varchar(200) | | レース名 |
| `race_number` | varchar(5) | | レース番号（R番号） |
| `date` | varchar(20) | | 開催日（フォーマット: `YYYY/MM/DD`） |
| `venue` | varchar(50) | | 競馬場名（例: 東京、阪神） |
| `course_type` | varchar(20) | | コース種別（芝／ダート） |
| `distance` | integer | | 距離（m） |
| `direction` | varchar(10) | | 回り（左／右） |
| `weather` | varchar(20) | | 天候 |
| `track_condition` | varchar(20) | | 馬場状態（良／稍重／重／不良） |
| `grade` | varchar(20) | | グレード（G1/G2/G3 など） |
| `start_time` | varchar(10) | | 発走時刻 |
| `head_count` | integer | | 出走頭数 |
| `raw_data` | text | | スクレイピング生データ（JSON） |
| `created_at` | timestamp | ✓ | 作成日時 |
| `updated_at` | timestamp | ✓ | 更新日時 |

#### `race_results` — レース結果・出走馬情報

| カラム | 型 | NOT NULL | 説明 |
|---|---|---|---|
| `race_id` | varchar(20) | ✓ | **PK(1/2)**。`races.race_id` 参照 |
| `horse_number` | varchar(5) | ✓ | **PK(2/2)**。馬番 |
| `finishing_position` | varchar(10) | | 着順 |
| `bracket_number` | varchar(5) | | 枠番 |
| `horse_name` | varchar(100) | | 馬名（非正規化） |
| `horse_id` | varchar(20) | | 馬ID（`horses.horse_id` 参照）。インデックスあり |
| `sex_age` | varchar(10) | | 性齢（例: `牝4`） |
| `weight_carried` | varchar(10) | | 斤量 |
| `jockey_name` | varchar(50) | | 騎手名（非正規化） |
| `jockey_id` | varchar(20) | | 騎手ID（`jockeys.jockey_id` 参照）。インデックスあり |
| `finish_time` | varchar(20) | | タイム（例: `1:51.4`） |
| `margin` | varchar(20) | | 着差（例: `クビ`、`3`） |
| `passing_order` | varchar(20) | | 通過順位（例: `6-7-11-12`） |
| `last_3f` | varchar(10) | | 上がり3ハロン（秒） |
| `odds` | varchar(10) | | 単勝オッズ |
| `popularity` | varchar(10) | | 人気順 |
| `horse_weight` | integer | | 馬体重（kg） |
| `horse_weight_diff` | integer | | 馬体重増減（kg） |
| `trainer_name` | varchar(50) | | 調教師名（非正規化） |
| `trainer_id` | varchar(20) | | 調教師ID（`trainers.trainer_id` 参照）。インデックスあり |
| `owner` | varchar(100) | | 馬主名 |
| `prize_money` | varchar(20) | | 賞金 |
| `raw_data` | text | | スクレイピング生データ（JSON） |
| `created_at` | timestamp | ✓ | 作成日時 |

#### `payoffs` — 払い戻し

| カラム | 型 | NOT NULL | 説明 |
|---|---|---|---|
| `id` | integer | ✓ | **PK**（serial） |
| `race_id` | varchar(20) | ✓ | `races.race_id` 参照。インデックスあり |
| `bet_type` | varchar(20) | | 券種（単勝・複勝・枠連・馬連・馬単・ワイド・三連複・三連単） |
| `combination` | varchar(100) | | 組み合わせ（例: `16`、`3-7`） |
| `payout` | varchar(50) | | 払い戻し金額（例: `1,310`） |
| `popularity` | varchar(20) | | 人気 |
| `created_at` | timestamp | ✓ | 作成日時 |

#### `pre_race_odds` — 事前オッズ

締切前（前日／当日朝）にスクレイプした暫定単勝オッズ。**EV 計算・買い目選定にのみ使用し、学習の特徴量として使わない**。

> **学習除外方針**：事前オッズを学習特徴量に含めると「市場オッズの模倣」になり、控除率（約20%）分の損失が上限となって回収率が頭打ちになる。EV の算出（`EV = win_prob × pre_race_odds.win_odds`）と買い目フィルタリングの入力としてのみ参照する。確定オッズ（`race_results.odds`）も同様に学習特徴量から除外する。

| カラム | 型 | NOT NULL | 説明 |
|---|---|---|---|
| `race_id` | varchar(20) | ✓ | **PK(1/2)**。`races.race_id` 参照 |
| `horse_number` | varchar(5) | ✓ | **PK(2/2)**。馬番 |
| `win_odds` | numeric(8,1) | | 単勝オッズ（数値型。EV 計算に使用） |
| `scraped_at` | timestamp | ✓ | オッズ取得日時（最新スクレイプ時刻） |
| `created_at` | timestamp | ✓ | 作成日時 |

- PK は `(race_id, horse_number)` で 1 レース × 1 馬 = 1 行。再スクレイプ時は Upsert で上書き。
- `win_odds` は `varchar` でなく `numeric` で保持し、直接 EV 計算に使える形にする。

### データソース

- **netkeiba** (スクレイピング)

## 入出力仕様

### scraper

#### 入力

| 項目 | 内容 |
|---|---|
| スクレイピング対象 URL | `https://db.netkeiba.com/race/{race_id}/` など netkeiba の各ページ |
| `race_id` | 12桁数字文字列（例: `199505010201`） |
| 環境変数 `DATABASE_URL` | 接続先 PostgreSQL の DSN |

#### 出力

| 項目 | 内容 |
|---|---|
| DB 保存先 | `races`, `race_results`, `horses`, `jockeys`, `trainers`, `payoffs` テーブル |
| Upsert 方式 | 主キーが衝突した場合は上書き更新（`ON CONFLICT DO UPDATE`） |

---

### predictor

#### 入力

| 項目 | 内容 |
|---|---|
| `race_id` | 予測対象レースの ID（CLI 引数または環境変数） |
| 環境変数 `DATABASE_URL` | 接続先 PostgreSQL の DSN |
| モデルファイル | 学習済みモデル（`predictor/models/{timestamp}/win_calibrated.pkl`, `place_calibrated.pkl`） |

近走成績フィーチャーの取得方式はフェーズによって異なる：

- **学習時**: 全件ロード後に pandas rolling で集計（全データを1クエリで取得）
- **予測時**: SQL ウィンドウ関数 + `WHERE horse_id IN (対象馬)` で対象レースの馬のみ取得

学習フェーズでは DB から以下の特徴量を取得する：

| カテゴリ | 特徴量（カラム） |
|---|---|
| レース条件 | `venue`, `course_type`, `distance`, `direction`, `weather`, `track_condition`, `grade`, `head_count` |
| 出走馬 | `horse_number`, `bracket_number`, `sex`（`sex_age` より分離）, `age`（同）, `weight_carried`, `horse_weight`, `horse_weight_diff`, `horse_weight_relative`（レース内 z-score） |
| 前走との比較 | `distance_change`（距離変化）, `course_type_change`（コース替わりフラグ）, `jockey_change`（騎手乗り替わりフラグ） |
| 近走成績（全レース・直近3走） | `avg_finish_last3`, `best_finish_last3`, `avg_last3f_last3` |
| 近走成績（全レース・直近5走） | `avg_finish_last5`, `best_finish_last5`, `avg_last3f_last5` |
| 近走成績（同コース種別・同距離・直近3走） | `avg_finish_last3_cond`, `best_finish_last3_cond`, `avg_last3f_last3_cond` |
| 近走成績（同コース種別・同距離・直近5走） | `avg_finish_last5_cond`, `best_finish_last5_cond`, `avg_last3f_last5_cond` |
| 先行指数（全レース） | `avg_corner_last3`, `avg_corner_last5`（最初のコーナー通過順位の平均） |
| 先行指数（同コース種別・同距離） | `avg_corner_last3_cond`, `avg_corner_last5_cond` |
| 上がり3ハロン相対順位（全レース） | `avg_last3f_rank_last3`, `avg_last3f_rank_last5` |
| 上がり3ハロン相対順位（同コース種別・同距離） | `avg_last3f_rank_last3_cond`, `avg_last3f_rank_last5_cond` |
| 血統 | `sire`, `dam`, `broodmare_sire` |
| 騎手統計 | `jockey_win_rate_venue_cond`（場・コース種別の勝率） |
| 調教師統計 | `trainer_win_rate_last30`（直近成績の勝率） |
| 騎手・調教師 | `jockey_id`, `trainer_id` |
| 枠番×距離帯 | `bracket_distance_avg_finish`（枠番×距離帯の平均着順） |

> **市場オッズ（`odds`, `popularity`）は学習特徴量から除外。** 確定オッズを含めると「市場オッズの模倣」になり控除率分の損失が上限となるため。事前オッズ（`pre_race_odds.win_odds`）は EV 計算にのみ使用する。

#### 出力

標準出力（テキスト形式）および CSV ファイル（`output/prediction_{race_id}.csv`）。

| カラム | 内容 |
|---|---|
| `horse_number` | 馬番 |
| `horse_name` | 馬名 |
| `win_prob` | 単勝確率（0〜1） |
| `place_prob` | 複勝確率（0〜1、3着以内） |
| `predicted_rank` | 予測着順 |
| `ev` | 単勝 EV（`win_prob × win_odds`。`win_odds` 未取得時は NaN） |
| `recommended_win` | 単勝推奨フラグ |
| `recommended_place` | 複勝推奨フラグ |
| `recommended_quinella` | 馬連推奨フラグ（各レースの推奨ペア2頭に `true`） |
| `recommended_wide` | ワイド推奨フラグ（各レースの推奨ペア2頭に `true`） |
| `recommended_trifecta_box` | 三連複推奨フラグ（各レースの推奨トリプレット3頭に `true`） |
| `recommended` | いずれかの券種で推奨の場合 `true` |

推奨買い目の基準：

| 券種 | 推奨基準 |
|---|---|
| 単勝 | EV（`win_prob × win_odds`）> 1.5 のうち `win_prob` 最大の1頭 |
| 複勝 | `place_prob` 上位3頭 |
| 馬連 | MC 馬連確率（両馬が2着以内に収まる確率）が最大のペア1点 |
| ワイド | MC ワイド確率（両馬が3着以内に収まる確率）が最大のペア1点 |
| 三連複 | MC 三連複確率（3頭が3着以内に収まる確率）が最大のトリプレット1点 |

---

## モンテカルロ着順シミュレーション

### サンプリング方式

**Plackett-Luce（Gumbel max trick）** を採用する。

各馬のスコアを以下の式で算出し、降順に並べた順序を着順とする：

$$\text{score}_i = \log(\text{win\_prob}_i) + G_i, \quad G_i \sim \text{Gumbel}(0, 1)$$

- $G_i = -\log(-\log(U_i)), \quad U_i \sim \text{Uniform}(0, 1)$
- 1回のシミュレーションで全馬の着順が一括算出される（効率的なベクトル演算が可能）。
- ガンベルノイズを加えた argsort により、Plackett-Luce 分布からの正確なサンプリングと等価になる。

候補② の「能力スコア + ガンベルノイズで argsort」と実質同一の手法だが、`log(win_prob)` を能力スコアとみなすことで候補① の Plackett-Luce とも整合する。

### パラメータ方針

| パラメータ | デフォルト値 | 方針 |
|---|---|---|
| `n_iter` | 10,000 | 1レース 18 頭で標準誤差 ≈ 0.5% 未満。速度と精度のバランス点。 |
| `rng` | `None`（再現性なし） | 呼び出し側から `np.random.default_rng(seed)` を渡すことで固定できる。バックテストや検証時は固定シードを推奨。 |

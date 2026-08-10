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
| レース条件 | `venue`, `course_type`, `distance`, `direction`, `weather`, `track_condition`, `grade`, `head_count`, `class_level`（`race_condition` から抽出したクラス序列。0=新馬〜5=オープン） |
| 出走馬 | `horse_number`, `bracket_number`, `sex`（`sex_age` より分離）, `age`（同）, `weight_carried`, `horse_weight`, `horse_weight_diff`, `horse_weight_relative`（レース内 z-score） |
| 前走との比較 | `distance_change`（距離変化）, `course_type_change`（コース替わりフラグ）, `jockey_change`（騎手乗り替わりフラグ）, `class_change`（クラス変化。正=昇級・負=降級）, `days_since_last_race`（出走間隔・経過日数） |
| 近走成績（全レース・直近3走） | `avg_finish_last3`, `best_finish_last3`, `avg_last3f_last3` |
| 近走成績（全レース・直近5走） | `avg_finish_last5`, `best_finish_last5`, `avg_last3f_last5` |
| 近走成績（同コース種別・同距離・直近3走） | `avg_finish_last3_cond`, `best_finish_last3_cond`, `avg_last3f_last3_cond` |
| 近走成績（同コース種別・同距離・直近5走） | `avg_finish_last5_cond`, `best_finish_last5_cond`, `avg_last3f_last5_cond` |
| 先行指数（全レース） | `avg_corner_last3`, `avg_corner_last5`（最初のコーナー通過順位の平均） |
| 先行指数（同コース種別・同距離） | `avg_corner_last3_cond`, `avg_corner_last5_cond` |
| レース内ペース予想 | `corner_style_race_rank`（`avg_corner_last3` のレース内相対順位）, `race_leader_count`（`avg_corner_last3 <= 5.0` の頭数） |
| 上がり3ハロン相対順位（全レース） | `avg_last3f_rank_last3`, `avg_last3f_rank_last5` |
| 上がり3ハロン相対順位（同コース種別・同距離） | `avg_last3f_rank_last3_cond`, `avg_last3f_rank_last5_cond` |
| タイム偏差値（スピード指数） | `avg_speed_index_last3`, `avg_speed_index_last5`（タイムのレース内z-scoreを直近走で平均） |
| 血統 | `sire`, `broodmare_sire`（`dam` は検証の結果、有意な寄与が確認できず不採用。[ADR-0030](./adr/0030-dam-feature-removed.md) 参照） |
| 血統適性統計 | `sire_place_rate_cond`（父馬×コース種別の産駒複勝率、縮小推定）, `sire_progeny_mounts_cond`（同・累積産駒数）, `sire_avg_speed_index_cond`（父馬×コース種別の産駒平均スピード指数、縮小推定） |
| 騎手統計 | `jockey_win_rate_venue_cond`（場・コース種別の勝率）, `jockey_prior_win_rate`, `jockey_prior_mounts`（デビューからそのレース直前までの全期間累積勝率・累積騎乗数） |
| 調教師統計 | `trainer_win_rate_last30`（直近30走の勝率）, `trainer_prior_win_rate`, `trainer_prior_mounts`（全期間累積勝率・累積騎乗数） |
| 馬主統計 | `owner_prior_win_rate`, `owner_prior_mounts`（全期間累積勝率・累積騎乗数。エンティティキーは `race_results.owner` の文字列） |
| 騎手・調教師 | `jockey_id`, `trainer_id` |
| 枠番×距離帯 | `bracket_distance_avg_finish`（枠番×距離帯の平均着順） |

> **全期間累積勝率系（`*_prior_win_rate`, `*_prior_mounts`）の共通ロジック**: 日付単位で騎乗数・勝利数を集計してから1日分ずらして累積することで、当該レース自身は集計から除外する（同日複数レースの前後関係は不明なため）。既存の直近30走・venue×course_type限定版とは別軸として併存させる（置き換えではない）。検証結果は [ADR-0013](./adr/0013-trainer-jockey-lifetime-win-rate.md)（調教師・騎手、2026-08-01採用）・[ADR-0014](./adr/0014-owner-lifetime-win-rate.md)（馬主、同日追加採用）参照。

> **`class_level`（クラス序列）の抽出方法**: `races.race_condition`（レース条件の自由文）から正規表現でクラスを判定する（0=新馬, 1=未勝利, 2=1勝クラス/旧500万下, 3=2勝クラス/旧1000万下, 4=3勝クラス/旧1600万下, 5=オープン）。JRAが2019年にクラス呼称を変更したため、新旧両方の表記に対応している。JRAレースでは99.8%で `race_condition` が取得済みで抽出可能（地方競馬は非対応レースが多く欠損しうる）。`class_change` は前走との `class_level` 差（正=昇級、負=降級）。2026-08-03採用、詳細は [ADR-0018](./adr/0018-class-level-change.md) 参照。

> **`days_since_last_race`（出走間隔）は2段階の検証を経て採用。** 単独での初回検証（2026-08-03朝、`class_change`等の採用前）では標準splitの回収率が悪化し一度不採用と判定したが、walk-forward検証は行わなかった。後日、他の特徴量（クラス変化・レース内ペース予想・スピード指数）採用後の状態で再検証したところ、標準splitでの悪化はほぼ誤差範囲まで縮小し、walk-forwardでは4指標（win_accuracy・recovery_rate・win_logloss・place_logloss）すべてが改善したため採用に切り替えた。特徴量の価値は既存の特徴量セットに依存して変わりうる（単独検証の結果を過信しない）教訓として記録。詳細は [ADR-0024](./adr/0024-days-since-last-race-accepted.md)（初回不採用は[ADR-0016](./adr/0016-days-since-last-race-initial-rejected.md)）参照。

> **血統適性統計（`sire_place_rate_cond` 等）は2段階の検証を経て採用。** 当初「父馬×コース種別（×距離帯）の単勝勝率」で検証したところ、標準splitでは改善して見えたが正式なペアード・ブートストラップ有意差検定では win_logloss・place_logloss・win_accuracy いずれも95%CIが0を跨ぎ有意差なし（不採用、詳細は [ADR-0027](./adr/0027-pedigree-affinity-win-rate-rejected.md) 参照）。単勝は稀事象で父馬あたりのサンプルが薄いと高分散になるのが原因と判断し、(1) 発生率の高い複勝率への変更、(2) 少サンプルの極端値を抑える縮小推定（shrinkage、式: `(実測合計 + K×事前平均) / (件数 + K)`。複勝率は K=20、事前平均は全体複勝率、スピード指数は K=10・事前平均0）、(3) 連続値であるスピード指数（`race_time_zscore`）ベースの適性指標、の3方向で再設計したところ、`sire_place_rate_cond` と `sire_avg_speed_index_cond` の組み合わせが標準split・walk-forward・正式有意差検定（95%CI）のすべてで一貫して有意な改善を示したため採用した。母父馬×馬場状態版（BMSのダート・重馬場適性という経験則の検証）は単体でLog Lossが悪化し不採用。**構成要素ごとの個別検定では `sire_avg_speed_index_cond`（スピード指数側）のみ単体で3指標とも有意、`sire_place_rate_cond`（複勝率側）は単体では有意差なし**。ただし複勝率側を追加すると単体のスピード指数版よりLog Lossがさらに有意に改善する（D+E+F vs F単体の直接比較で確認済み）ため、複勝率側の追加自体が本物の相補効果と判断し組み合わせで採用した。2026-08-10採用、詳細は [ADR-0028](./adr/0028-pedigree-affinity-place-rate-shrinkage-accepted.md) 参照。
>
> **`dam`（母馬名）は特徴量から除外。** gain降順rankでは複勝モデル常に1位に見えていたが、permutation importance検定（シャッフルによるlog-loss悪化幅の95% bootstrap CI、CI下限>0で有意）では複勝モデルで全walk-forwardフォールド非有意、単勝モデルでも一部フォールドで非有意と判明。高カーディナリティな個体名categoricalはgainが訓練データへの過適合を過大評価しやすいと判断し、除外案をペアード・ブートストラップ有意差検定（標準split・walk-forward双方、95%CI）で検証したところ、除外後の方がwin_logloss・place_logloss・win_accuracyいずれも統計的に有意に改善し、recovery_rateも有意差なし（悪化ではない）だったため除外を採用した。2026-08-10、詳細は [ADR-0030](./adr/0030-dam-feature-removed.md) 参照。
>
> **市場オッズ（`odds`, `popularity`）は学習特徴量から除外。** 確定オッズを含めると「市場オッズの模倣」になり控除率分の損失が上限となるため。事前オッズ（`pre_race_odds.win_odds`）は EV 計算にのみ使用する。

#### 時間減衰サンプルウェイト・LightGBMハイパーパラメータ

`model.train(train_df, half_life_days=...)` で、レース日付からの経過日数に応じた指数減衰サンプルウェイト（`preprocessing.compute_time_decay_weight`）を学習時に適用できる。`half_life_days=None` を指定した場合は重みなしで学習する。

- 基準日（`reference_date`）はデフォルトで学習データ（`train_df`）の `date` 最大値。
- CLI: `python -m predictor.main train --half-life-days 1095`（半減期を日数で指定。`--half-life-days none` で明示的に無効化。未指定時はデフォルト値 `1095` を使用）。
- LightGBM パラメータ（`num_leaves`, `learning_rate`, `min_child_samples`, `feature_fraction`）も CLI から上書き可能: `--num-leaves N`, `--learning-rate F`, `--min-child-samples N`, `--feature-fraction F`（`predictor/predictor/model.py` の `win_params`/`place_params` に渡され、単勝・複勝モデルの両方に同じ値を適用する）。
- 比較実験: `python -m predictor.main compare-half-life` で `half_life_days ∈ {365, 1095, 1825, 3650, None}` を学習・較正・評価し、`output/half_life_comparison_{timestamp}.csv` に結果を保存する。
- Optuna 連携（`predictor/predictor/tuning.py`）: `python -m predictor.main tune [--n-trials N]` で `num_leaves`, `learning_rate`, `min_child_samples`, `feature_fraction`, `half_life_days` を探索する。目的関数は walk-forward 平均 `win_logloss`（最小化）。回収率は分散が大きく直接最適化すると特定の fold 構成のノイズに過学習しやすいため（下記2026-07-30の検証結果）、各 trial の walk-forward 平均回収率は `user_attrs["recovery_rate"]` に記録するのみに留め、`tuning.top_trials()` で Log Loss 上位の候補と回収率を並べて人手で確認する運用とする。

**デフォルトパラメータ（2026-08-01 更新、詳細は [ADR-0012](./adr/0012-optuna-winlogloss-hyperparameters.md) 参照）**: `model.py` の `_PARAMS`/`_RANK_PARAMS` は `num_leaves=127, learning_rate=0.0128, min_child_samples=41, feature_fraction=0.56`、`half_life_days` は CLI・`train_mode` ともデフォルト `1095` を採用。

- **経緯**: 2026-07-30 の検証では、(1) 単一 split で `half_life_days` のみ比較 → 重みなしが最良。(2) Optuna 同時探索（`n_trials=10`、回収率を目的関数）→ walk-forward平均回収率では `half_life_days=1095` を含む組み合わせが最良（84.08%）。(3) しかしその最良パラメータを標準の train/val/test split で再学習し bootstrap CI で検証したところ、win_accuracy・Log Loss・回収率のすべてで重みなしのデフォルトパラメータより悪化（汎化しなかった）。これを受けて Optuna の目的関数を分散の小さい `win_logloss` に変更した。
- **2026-08-01 の再検証**: `win_logloss` 最小化で探索した trial（`num_leaves=127, learning_rate=0.0128, min_child_samples=41, feature_fraction=0.56, half_life_days=1095`）を標準 train/val/test split で再学習したところ、win_accuracy（20.37%→21.27%）・win_logloss（0.2406→0.2376）・place_logloss（0.4815→0.4744）がいずれも改善し、回収率は誤差範囲で横ばい（73.06%→72.92%）だった。2026-07-30 とは異なり全指標で悪化する汎化失敗は再現せず、**目的関数を `win_logloss` に変更した設計が意図通り機能したことを確認**。ただし回収率自体は動いていないため、110%目標への寄与は限定的（精度改善であって黒字化ではない）。この結果を踏まえ、上記パラメータをデフォルトとして採用した。

#### Embeddingハイブリッド（オプション機能）

騎手ID・調教師ID・父馬名・母父馬名を対象に、PyTorch の `nn.Embedding` で低次元ベクトルを事前学習し、LightGBM の特徴量に追加できる。`model.train(..., embedding_feature_columns=...)` で既存特徴量に追加する形（非破壊的）で統合し、`train_mode(use_embeddings=False)`（デフォルト）の場合は従来と完全互換。

- **学習**: `python -m predictor.main train-embeddings` で `split_by_date` の train 部分のみを使い Embedding を学習・保存する（val/test への情報リークを防ぐため）。保存先は `predictor/embeddings/{timestamp}/embeddings.pkl`（`predictor/models/` と同じバージョニング方式）。
- **次元数**: カーディナリティに応じた経験則 `min(50, cardinality**0.25 * 4)` で自動決定。
- **未知IDフォールバック**: 学習データに存在しない ID・欠損値はカテゴリごとの平均ベクトル（`"__mean__"`）にフォールバックする。
- **LightGBM統合**: `python -m predictor.main train --use-embeddings [--embedding-pca-dim N]` で有効化。`--embedding-pca-dim` を指定すると各カテゴリの Embedding テーブルを PCA でその次元数に圧縮してから使用する。
- **類似度確認**: `python -m predictor.main similar-embeddings <category> <id> [--top-n N]` でコサイン類似度上位を表示できる。
- **重要な実装上の注意（torch と lightgbm のプロセス分離）**: この環境では torch と lightgbm を同一プロセスで読み込むと OpenMP ランタイムの競合により `lgb.Dataset.construct()` がセグメンテーション違反を起こすことを確認済み。そのため定数を torch 非依存の `embedding_common.py` に切り出し、LightGBM の学習・推論パス（`model.py`, `embedding_features.py`）が `embedding.py`（torch 依存）を import しない設計にしている。`predict()` / `calibration._extract_features()` は `get_feature_columns()` を再計算せず学習済み Booster 自身の `feature_name()` を使うことで、Embedding 特徴量の有無に関わらず学習時と厳密に同じカラム集合を参照する。
- **検証結果（2026-07-30〜31、詳細は [ADR-0011](./adr/0011-embedding-hybrid-rejected.md) 参照）**: 標準 train/val/test split で比較したところ、生の Embedding（73次元）は全指標で悪化。PCA圧縮（4カテゴリ×6次元=24列）は回収率が 73.06%→74.45%（+1.4pt）と改善したが、より安定した指標である Log Loss は横ばい〜微悪化。さらに単勝 top1 戦略の回収率を bootstrap CI（n=10,000）で検証したところ、baseline [73.16%, 83.50%] と embedding+PCA [74.36%, 85.38%] の 95% CI はほぼ全域が重なり、**+1.4pt の改善は統計的に有意ではない**ことを確認。3段階の検証を通じて**Embeddingハイブリッドが改善するという信頼できる証拠は得られておらず、現時点ではデフォルト（`use_embeddings=False`、Embeddingなし）の維持を推奨する**。

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

> **`race.betting`（軸）は未検証の参考表示であり、検証済み戦略ではない。** 上記の単勝・馬連・ワイド・三連複の基準は、どの人気帯についても walk-forward pooled bootstrap CI で回収率100%超えが示されたことは一度もない（各ADRの複数箇所で単勝top1戦略は65〜80%止まりと繰り返し確認済み。2026-08-02 の7番人気以下タイ再検証（[ADR-0009](./adr/0009-longshot-quinella-trio-strategy-rejected.md)）でも馬連・三連複・ワイドいずれもCI上限が100%未達）。実際にベット判断の根拠として使ってよいのは、bootstrap CI で個別に検証されている下記「戦略別（堅実・大穴）」の2つだけであり、`race.betting` は「モデルが現在どの馬を上位視しているか」を見るための参考情報に留める。

> **軸と「大穴」戦略の重複防止（2026-08-02）**: レース内 `win_prob` 最大馬（top1）が人気帯「7番人気以下」に該当する場合、単勝・馬連・ワイド・三連複の推奨（複勝を除く）は出力しない。理由: 「大穴」戦略（下記）は top1 が7番人気以下のときに発火する設計のため、素の推奨をそのまま出すと軸側の推奨と「大穴」戦略が同一馬に収束し、2つの戦略が実質1つになってしまう（2026-08-02 クイーンS で実際に発生。詳細は [ADR-0015](./adr/0015-longshot-specialized-model-rejected.md) 参照）。複勝は `place_prob` 上位3頭という別基準のため対象外。

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

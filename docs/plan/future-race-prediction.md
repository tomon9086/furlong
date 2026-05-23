# 未来レース予想機能（検討中）

> このファイルは探索・議論の場です。決定前のアイデアや選択肢を自由に書いてください。
> 確定した仕様は `spec.md` に移してください。

---

## 背景・目的

現在の `predictor` は DB に結果が登録済みのレースのみ対象。
今週開催される（まだ結果が出ていない）レースを予想するには追加実装が必要。

## 必要な機能一覧

### 1. 出馬表データの取得・保存

- **課題**: 出馬表ページ（出走馬・斤量・騎手が確定、着順なし）を DB に保存する仕組みがない
- **データソース候補**:
  - netkeiba の出馬表ページ（`/race/shutuba.html?race_id=XXXX`）
  - JRA 公式サイト（netkeiba にない場合のフォールバック）
  - → まず netkeiba に出馬表ページが存在するか調査が必要
- **実装案**:
  - `scraper` に `ShutsubaParser`（出馬表パーサー）を追加
  - 既存の `race_results` テーブルに着順 NULL で INSERT（または専用テーブルを新設）
  - コマンド: `uv run --package furlong-scraper python -m scraper shutuba <race_id>`

### 2. 対象 race_id の特定方法

- **課題**: 今週のレース一覧から race_id を取得する手段がない
- **選択肢**:
  - A. 手動で race_id を調べて指定する（netkeiba URL から確認）
  - B. 開催スケジュールページをスクレイピングして race_id 一覧を取得する
  - → 初期実装は A（手動指定）で進め、慣れたら B を検討

### 3. 前処理クエリの対応

- **課題**: 現在の `_QUERY` が `WHERE rr.finishing_position ~ '^[0-9]+$'` で結果確定済みのみに絞っている
- **実装案**:
  - 予測時クエリを別途用意し、指定 race_id の出走馬を取得
  - 近走成績は過去の確定レースから集計（`repository-package.md` のウィンドウ関数 SQL を活用）
  - `finishing_position` が NULL / 非数値の行も対象にできるよう条件を分岐

### 4. 未登録馬のデータ自動補完

- **課題**: 出馬表に新馬など未登録の馬が含まれる場合、`horses` テーブルにデータがない
- **方針**: 出馬表取り込み時に `horses` テーブルを参照し、未登録馬は scraper で自動取得して補完
- **実装案**: `scrape_horse(horse_id)` を出馬表保存フローの中に組み込む

### 5. 出力形式

確認済みの要求:
- 着順予測（1〜3着）
- 勝率・複勝率の確率
- 推奨買い目（馬連・三連複など）
- CSV への保存

→ 現在の `output.py` に推奨買い目生成を追加する必要がある

## 調査結果（2026-05-20）

- **netkeiba に出馬表ページあり** → `https://race.netkeiba.com/race/shutuba.html?race_id=XXXX` でアクセス可能
  - 例: `https://race.netkeiba.com/race/shutuba.html?race_id=202605021011&rf=race_list`
  - curl で直接取得可能（リダイレクトなし）。エンコーディングは EUC-JP（既存と同様）
  - ドメインが `db.netkeiba.com`（既存）ではなく `race.netkeiba.com` → `NetkeibaClient` に `get_shutuba` メソッドを追加する必要あり
- **JRA フォールバックは不要** → netkeiba で取得できることが確認できたため
- **race_id は手動指定で進める**（フェーズ1）

### 出馬表ページの HTML 構造

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

## 未解決の論点

（なし — 調査完了）

## 決定事項

- **出馬表データの保存先**: 既存の `race_results` テーブルに `finishing_position = NULL` で INSERT（案A）
  - `finishing_position` は NOT NULL 制約なし → スキーマ変更不要
  - `race.netkeiba.com` と `db.netkeiba.com` の race_id 形式は共通
  - 予測時は `finishing_position IS NULL` で出馬表データを識別できる

## 実装順序（暫定）

1. netkeiba 出馬表ページの構造調査・パーサー実装
2. 出馬表保存コマンド追加（`scraper shutuba <race_id>`）
3. 未登録馬の自動補完
4. 予測時クエリの分離（近走成績フィーチャーをウィンドウ関数で計算）
5. 推奨買い目出力の追加

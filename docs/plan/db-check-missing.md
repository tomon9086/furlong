# DB 欠損チェックスクリプト（検討中）

> このファイルは探索・議論の場です。決定前のアイデアや選択肢を自由に書いてください。
> 確定した仕様は `spec.md` に移してください。

---

## 背景・目的

スクレイピングや補完ロジックの不具合により、レース結果に紐づく周辺データ（馬・騎手・調教師・払い戻し）が登録されていないケースが発生しうる。
補完はせず「どのデータが欠けているか」を確認できるスクリプトがほしい。

## チェック対象（5種類）

| チェック | 内容 |
|---|---|
| 1. 馬マスタ欠損 | `race_results.horse_id` が `horses` テーブルに存在しない |
| 2. 騎手マスタ欠損 | `race_results.jockey_id` が `jockeys` テーブルに存在しない |
| 3. 調教師マスタ欠損 | `race_results.trainer_id` が `trainers` テーブルに存在しない |
| 4. レース結果欠落 | `races.race_id` に対応する `race_results` の行がない |
| 5. 払い戻し欠落 | `races.race_id` に対応する `payoffs` の行がない |

**対象レース**: 結果確定済みレースのみ（`race_results.finishing_position ~ '^[0-9]+$'` が1行以上ある `race_id`）。出馬表データ（未確定）は除外する。

**NULL/空文字の扱い**: `horse_id` / `jockey_id` / `trainer_id` が NULL または空文字の行はスキップ（データとして「不明」扱いで欠損カウントしない）。

## 出力形式

標準出力にテキストで出力する。各チェックについて以下を表示する。

```
=== 1. 馬マスタ欠損 ===
件数: 42 件
サンプル（最大10件）:
  horse_id=2019105042  horse_name=ソールオリエンス  race_id=202305281211
  horse_id=2020100123  horse_name=イクイノックス     race_id=202305281011
  ...

=== 2. 騎手マスタ欠損 ===
件数: 0 件
OK

...

=== サマリ ===
1. 馬マスタ欠損:       42 件
2. 騎手マスタ欠損:      0 件
3. 調教師マスタ欠損:    3 件
4. レース結果欠落:      1 件
5. 払い戻し欠落:        5 件
```

## スクリプト配置

- **パス**: `tools/check_missing.py`（ルートレベルに `tools/` ディレクトリを新設）
- **実行コマンド**: `uv run python tools/check_missing.py`
- DB 接続情報は環境変数（`DATABASE_URL` or `.env` ファイル）から取得

## 使用するクエリ（SQL 設計）

### チェック 1: 馬マスタ欠損

```sql
SELECT DISTINCT
    rr.horse_id,
    rr.horse_name,
    rr.race_id
FROM race_results rr
WHERE rr.horse_id IS NOT NULL
  AND rr.horse_id <> ''
  AND rr.horse_id NOT IN (SELECT horse_id FROM horses)
ORDER BY rr.horse_id
```

### チェック 2: 騎手マスタ欠損

```sql
SELECT DISTINCT
    rr.jockey_id,
    rr.jockey_name,
    rr.race_id
FROM race_results rr
WHERE rr.jockey_id IS NOT NULL
  AND rr.jockey_id <> ''
  AND rr.jockey_id NOT IN (SELECT jockey_id FROM jockeys)
ORDER BY rr.jockey_id
```

### チェック 3: 調教師マスタ欠損

```sql
SELECT DISTINCT
    rr.trainer_id,
    rr.trainer_name,
    rr.race_id
FROM race_results rr
WHERE rr.trainer_id IS NOT NULL
  AND rr.trainer_id <> ''
  AND rr.trainer_id NOT IN (SELECT trainer_id FROM trainers)
ORDER BY rr.trainer_id
```

### チェック 4: レース結果欠落（結果確定レース限定）

```sql
SELECT r.race_id, r.race_name, r.date
FROM races r
WHERE NOT EXISTS (
    SELECT 1 FROM race_results rr
    WHERE rr.race_id = r.race_id
      AND rr.finishing_position ~ '^[0-9]+$'
)
ORDER BY r.date DESC
```

> 注: 出馬表のみ取り込み済みで結果未取得のレースが対象になる。開催前レースも混入する可能性があるため、日付フィルタ（過去のみ）も付加する方が実用的か要検討。

### チェック 5: 払い戻し欠落（結果確定レース限定）

```sql
SELECT r.race_id, r.race_name, r.date
FROM races r
WHERE EXISTS (
    SELECT 1 FROM race_results rr
    WHERE rr.race_id = r.race_id
      AND rr.finishing_position ~ '^[0-9]+$'
)
  AND NOT EXISTS (
    SELECT 1 FROM payoffs p
    WHERE p.race_id = r.race_id
)
ORDER BY r.date DESC
```

## 未解決の論点

- [ ] チェック4の「開催前レース混入問題」: 今日以前の日付に限定する条件（`TO_DATE(r.date, 'YYYY/MM/DD') < CURRENT_DATE`）を加えるか
- [ ] DB 接続方法: `repository` パッケージの `Database` クラスを使うか、`psycopg` を直接使うか

## 実装ステップ

1. `tools/` ディレクトリを作成
2. `tools/check_missing.py` を実装（DB接続・各クエリ実行・結果フォーマット出力）
3. 動作確認（`uv run python tools/check_missing.py`）

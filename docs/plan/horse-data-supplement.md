# scrape_race / scrape_backfill における馬データの欠損問題（検討中）

> このファイルは探索・議論の場です。決定前のアイデアや選択肢を自由に書いてください。
> 確定した仕様は `spec.md` に移してください。

---

## 背景

`scrape_shutuba` は出馬表取り込み時に未登録馬を自動補完しているが、
`scrape_race` および `scrape_backfill` には馬の補完ロジックが実装されていない。

そのため、`scrape_backfill` で過去レースを一括取得した場合、レース結果の `horse_id` が `horses` テーブルに存在しない状態になり得る。

実際に 2026-05-23 のバックフィル実行ログを確認したところ、騎手・調教師の補完ログは出ているが馬の補完ログは皆無だった（補完処理が存在しないため）。

## 問題の影響

- `race_results.horse_id` が `horses` テーブルに存在しない行がある可能性
- 学習・予測時に血統情報など `horses` テーブルのカラムを JOIN で参照する場合、NULL になるか行が欠落する

## 解決方針

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

## 遡及修正方針

既存データも修正する。以下の2段階で対応する。

1. **コード修正**: `_supplement_horses` を実装し `scrape_race` / `scrape_backfill` に組み込む（再発防止）
2. **遡及スクリプト**: `race_results` に存在する `horse_id` のうち `horses` テーブルに未登録のものを洗い出し、1頭ずつ scrape して補完する1回限りのスクリプトを用意する

### 遡及スクリプトの実装イメージ

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

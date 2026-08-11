# 確定オッズ欠損バグ（2026-04-29〜）調査メモ

## 発端

[plan/regional-racing-model.md](./regional-racing-model.md) の検討中に見つかった
「勝ち馬oddsのnull」を深掘りした調査記録。

## 根本原因（確定）

`RaceDetailParser`（[scraper/scraper/parsers/race_detail.py](../../scraper/scraper/parsers/race_detail.py)）が
レース結果テーブルの `<th>` テキストをそのままキーにして行を辞書化している
（`row = dict(zip(headers, cells))`, L77）。

実際にレース結果ページ（`db.netkeiba.com/race/{race_id}/`）をBeautifulSoupで解析すると、
オッズ列のヘッダーは **`"単勝"`** であり、`"単勝オッズ"` というキーは存在しない
（ヘッダー一覧: `..., '通過', '上り', '単勝', '人気', '馬体重', ...`）。

一方、DB保存処理（[repository/repository/database.py:158,398](../../repository/repository/database.py#L158)）は
`row.get("単勝オッズ")` で値を取り出している。このキー名は出馬表（レース前）パーサー
（[scraper/scraper/parsers/shutuba.py:107](../../scraper/scraper/parsers/shutuba.py#L107)）が
明示的に `row["単勝オッズ"] = ...` をセットしているのに合わせたものだが、確定結果側の
`RaceDetailParser` はこのキーを一切生成しない。結果、`row.get("単勝オッズ")` は常に `None` を
返し、確定オッズが常にNULL保存されていた。

**venue名や日付での場合分けは無関係**（中央・地方問わず、`RaceDetailParser` を通る限り常に発生する）。

## なぜ2026/04/29から急に顕在化したか

- `race_detail.py` はスクレイパーの最初期実装コミットから一度も変更されていない
  （`git log --follow` で確認、[regional-racing-model.md](./regional-racing-model.md) 参照）。
  → 後から入った回帰（regression）ではなく、実装当初からのバグ。
- このリポジトリの `git log` 最古コミットは **2026-04-26 23:09** で、これが実運用の
  scraper が初めて稼働したタイミングと一致する。
- 2026/04/26以前の31年分の履歴データは、このリポジトリのscraperコードとは別の手段
  （既存シード投入）で入っていたため、このバグの影響を受けていなかった。
- 稼働開始後（2026/04/29〜）に `scrape_incremental`/`scrape_backfill` で新規取得された
  レースはすべてこのバグの影響を受けている。

## 影響範囲（2026-08-11時点で計測）

完走馬（`finishing_position` が数値）に限定して集計。非数値テキストの混入は0件、
純粋にこのバグによるNULLのみ。

- 対象レース数: **720件**
- 対象期間: **2026/04/29 〜 2026/07/24**
- venue別内訳: 門別98・大井94・園田85・笠松78・水沢46・金沢45・帯広(ば)40・
  名古屋36・川崎36・東京34・盛岡24・高知23・佐賀22・浦和/船橋/函館/京都各12・阪神11
  （地方競馬に集中しているが中央競馬4場も含む）
- `client.py` のレート制限（3秒/リクエスト）ベースで再取得は約36分の見込み

学習パイプラインの標準テスト期間（直近20%、2020/05/24〜）内では、完走馬の4.90%・
勝ち馬の6.49%がこの欠損の影響を受けている（詳細は会話ログ参照、値は今後変わりうるため
再検証時に再計測すること）。

## 修正方針（未着手）

1. `race_detail.py` の `row = dict(zip(headers, cells))` 直後に
   `row["単勝オッズ"] = row.get("単勝", "")` を追加（`馬ID`/`騎手ID`/`調教師ID` と同様の正規化パターン）
2. 該当720レースを `backfill_missing.py --force <race_id...>` 等で再取得し、oddsを埋め直す
3. `check_missing.py` に odds欠損検知クエリを追加する（行は存在するがカラムがnullのケースは
   現状検知できていない。再発防止）
4. 修正・再取得後、現行テストセットの回収率・EVフィルタ分析への影響度を bootstrap CI で定量化する

# TODO

> 完了したタスクは削除せず、チェックを付けてください。
> セクション内のタスクがすべて完了したら、セクションごと削除してください。

## 未来レース予想機能

### scraper: 出馬表対応

- [x] `NetkeibaClient` に `get_shutuba(race_id)` メソッドを追加（`race.netkeiba.com` へのリクエスト）
- [x] `ShutsubaParser` を新規作成
  - [x] `parse_race_info(html)` — `h1.RaceName` / `div.RaceData01` / `div.RaceData02` からレース情報を取得
  - [x] `parse(html)` — `tr.HorseList` から出走馬一覧を取得（枠順未確定時は `id="tr_XX"` から馬番を取得）
- [ ] `scraper/main.py` に `shutuba` モードを追加（`python -m scraper shutuba <race_id>`）
  - [ ] 出馬表取り込み時に未登録馬を `scrape_horse()` で自動補完
- [ ] `scraper/tests/` に `ShutsubaParser` のテストを追加

### predictor: 未来レース予測対応

- [ ] 予測時クエリを分離 — 指定 `race_id` の出走馬を `finishing_position IS NULL` で取得
- [ ] 近走成績フィーチャーをウィンドウ関数 SQL で計算（plan.md 記載の SQL を実装）
- [ ] `output.py` に推奨買い目（馬連・三連複）の生成を追加
- [ ] `predictor/main.py predict <race_id>` が出馬表データで動作することを確認


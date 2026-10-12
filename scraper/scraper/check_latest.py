"""DB に入っている最新データの日付を確認するスクリプト.

使い方:
    uv run --package furlong-scraper python -m scraper.check_latest

環境変数:
    DATABASE_URL  PostgreSQL 接続文字列（例: postgresql://user:pass@localhost:5432/furlong）
"""

import os
import sys

import psycopg
from dotenv import load_dotenv

load_dotenv()

# --------------------------------------------------------------------------- #
# クエリ定義
# --------------------------------------------------------------------------- #

# race_id の5〜6桁目が 01〜10 なら中央（JRA）、それ以外は地方
_CATEGORY = "CASE WHEN SUBSTRING(r.race_id, 5, 2) BETWEEN '01' AND '10' THEN '中央' ELSE '地方' END"

# 結果（着順）が入っているレースの最新開催日と、その日のレース数
_Q_LATEST_RESULT = f"""
WITH finished AS (
    SELECT r.race_id, r.date, {_CATEGORY} AS category
    FROM races r
    WHERE r.date IS NOT NULL
      AND EXISTS (
        SELECT 1 FROM race_results rr
        WHERE rr.race_id = r.race_id
          AND rr.finishing_position ~ '^[0-9]+$'
      )
)
SELECT f.category, f.date, COUNT(*)
FROM finished f
JOIN (SELECT category, MAX(date) AS date FROM finished GROUP BY category) m
  ON m.category = f.category AND m.date = f.date
GROUP BY f.category, f.date
ORDER BY f.category
"""

# 出馬表のみ（結果未取得）も含めた最新開催日
_Q_LATEST_ANY = """
SELECT MAX(date) FROM races WHERE date IS NOT NULL
"""

# 直近 N 日で開催日を過ぎているのに結果（着順）が1件も入っていないレース
# （出馬表だけ保存されたまま結果が取れていないレースの検知用。
#   古い地方競馬には開催中止で着順が空のレースが多数あるため期間を絞る）
_PENDING_DAYS = 30
_Q_RESULT_PENDING = f"""
SELECT r.race_id, r.race_name, r.date
FROM races r
WHERE r.date IS NOT NULL
  AND TO_DATE(r.date, 'YYYY/MM/DD') < CURRENT_DATE
  AND TO_DATE(r.date, 'YYYY/MM/DD') >= CURRENT_DATE - {_PENDING_DAYS}
  AND NOT EXISTS (
    SELECT 1 FROM race_results rr
    WHERE rr.race_id = r.race_id
      AND rr.finishing_position ~ '^[0-9]+$'
  )
ORDER BY r.date DESC, r.race_id DESC
"""

# 各テーブルの最終書き込み時刻
_Q_LAST_WRITE = """
SELECT 'races',         MAX(updated_at) FROM races
UNION ALL SELECT 'race_results',  MAX(created_at) FROM race_results
UNION ALL SELECT 'payoffs',       MAX(created_at) FROM payoffs
UNION ALL SELECT 'pre_race_odds', MAX(scraped_at) FROM pre_race_odds
UNION ALL SELECT 'horses',        MAX(updated_at) FROM horses
UNION ALL SELECT 'jockeys',       MAX(updated_at) FROM jockeys
UNION ALL SELECT 'trainers',      MAX(updated_at) FROM trainers
"""

# --------------------------------------------------------------------------- #
# メイン
# --------------------------------------------------------------------------- #


def main() -> None:
    try:
        database_url = os.environ["DATABASE_URL"]
    except KeyError:
        print("環境変数 DATABASE_URL が設定されていません。", file=sys.stderr)
        sys.exit(1)

    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(_Q_LATEST_RESULT)
            latest_result = cur.fetchall()

            cur.execute(_Q_LATEST_ANY)
            latest_any = cur.fetchone()[0]

            cur.execute(_Q_RESULT_PENDING)
            pending = cur.fetchall()

            cur.execute(_Q_LAST_WRITE)
            last_write = cur.fetchall()

    print("=== 結果取得済みの最新開催日 ===")
    if not latest_result:
        print("  結果の入ったレースがありません。")
    for category, race_date, count in latest_result:
        print(f"  {category}: {race_date}（{count} レース）")
    print()

    print("=== 出馬表のみも含めた最新開催日 ===")
    print(f"  {latest_any or 'なし'}")
    print()

    print(f"=== 開催日を過ぎて結果未取得のレース（直近{_PENDING_DAYS}日） ===")
    print(f"  件数: {len(pending)} 件")
    for race_id, race_name, race_date in pending[:10]:
        print(f"  race_id={race_id}  race_name={race_name}  date={race_date}")
    print()

    print("=== テーブル別の最終書き込み時刻 ===")
    for table, ts in last_write:
        value = ts.strftime("%Y-%m-%d %H:%M:%S") if ts else "なし"
        print(f"  {table:<14} {value}")


if __name__ == "__main__":
    main()

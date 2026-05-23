"""DB 欠損チェックスクリプト.

使い方:
    uv run --package furlong-scraper python -m scraper.check_missing

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

_Q1_HORSE = """
SELECT
    rr.horse_id,
    MIN(rr.horse_name) AS horse_name
FROM race_results rr
WHERE rr.horse_id IS NOT NULL
  AND rr.horse_id <> ''
  AND rr.horse_id NOT IN (SELECT horse_id FROM horses)
GROUP BY rr.horse_id
ORDER BY rr.horse_id
"""

_Q2_JOCKEY = """
SELECT
    rr.jockey_id,
    MIN(rr.jockey_name) AS jockey_name
FROM race_results rr
WHERE rr.jockey_id IS NOT NULL
  AND rr.jockey_id <> ''
  AND rr.jockey_id NOT IN (SELECT jockey_id FROM jockeys)
GROUP BY rr.jockey_id
ORDER BY rr.jockey_id
"""

_Q3_TRAINER = """
SELECT
    rr.trainer_id,
    MIN(rr.trainer_name) AS trainer_name
FROM race_results rr
WHERE rr.trainer_id IS NOT NULL
  AND rr.trainer_id <> ''
  AND rr.trainer_id NOT IN (SELECT trainer_id FROM trainers)
GROUP BY rr.trainer_id
ORDER BY rr.trainer_id
"""

_Q4_RACE_RESULTS = """
SELECT r.race_id, r.race_name, r.date
FROM races r
WHERE NOT EXISTS (
    SELECT 1 FROM race_results rr
    WHERE rr.race_id = r.race_id
)
  AND TO_DATE(r.date, 'YYYY/MM/DD') < CURRENT_DATE
ORDER BY r.date DESC
"""

_Q5_PAYOFFS = """
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
"""

# --------------------------------------------------------------------------- #
# 出力ヘルパー
# --------------------------------------------------------------------------- #


def _print_check(
    title: str,
    rows: list[tuple],
    col_labels: list[str],
) -> int:
    """チェック結果を整形して標準出力に書き出す。件数を返す。"""
    count = len(rows)
    print(f"=== {title} ===")
    print(f"件数: {count} 件")
    if count == 0:
        print("OK")
    else:
        print("サンプル（最大10件）:")
        for row in rows[:10]:
            parts = [f"{label}={val}" for label, val in zip(col_labels, row)]
            print("  " + "  ".join(parts))
    print()
    return count


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
            cur.execute(_Q1_HORSE)
            rows1 = cur.fetchall()

            cur.execute(_Q2_JOCKEY)
            rows2 = cur.fetchall()

            cur.execute(_Q3_TRAINER)
            rows3 = cur.fetchall()

            cur.execute(_Q4_RACE_RESULTS)
            rows4 = cur.fetchall()

            cur.execute(_Q5_PAYOFFS)
            rows5 = cur.fetchall()

    c1 = _print_check("1. 馬マスタ欠損", rows1, ["horse_id", "horse_name"])
    c2 = _print_check("2. 騎手マスタ欠損", rows2, ["jockey_id", "jockey_name"])
    c3 = _print_check("3. 調教師マスタ欠損", rows3, ["trainer_id", "trainer_name"])
    c4 = _print_check("4. レース結果欠落", rows4, ["race_id", "race_name", "date"])
    c5 = _print_check("5. 払い戻し欠落", rows5, ["race_id", "race_name", "date"])

    print("=== サマリ ===")
    print(f"1. 馬マスタ欠損:       {c1:>6} 件")
    print(f"2. 騎手マスタ欠損:     {c2:>6} 件")
    print(f"3. 調教師マスタ欠損:   {c3:>6} 件")
    print(f"4. レース結果欠落:     {c4:>6} 件")
    print(f"5. 払い戻し欠落:       {c5:>6} 件")


if __name__ == "__main__":
    main()

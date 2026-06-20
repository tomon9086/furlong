"""未登録の馬・騎手・調教師を DB から洗い出してスクレイプする遡及補完スクリプト.

使い方:
    uv run --package furlong-scraper python -m scraper.backfill_missing

    # 馬のみ補完する場合
    uv run --package furlong-scraper python -m scraper.backfill_missing --horses-only

    # 指定した race_id の出馬表を強制再取得（既存データを上書き）
    uv run --package furlong-scraper python -m scraper.backfill_missing --force 202605030511 202605030512

環境変数:
    DATABASE_URL  PostgreSQL 接続文字列（例: postgresql://user:pass@localhost:5432/furlong）
"""

import argparse
import logging
import os
import sys

import psycopg
from dotenv import load_dotenv

from repository import Database
from .client import NetkeibaClient
from .parsers import HorseParser, JockeyParser, RaceDetailParser, ShutsubaParser, TrainerParser

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# 未登録 ID 取得クエリ
# --------------------------------------------------------------------------- #

_Q_MISSING_HORSES = """
SELECT DISTINCT rr.horse_id
FROM race_results rr
WHERE rr.horse_id IS NOT NULL
  AND rr.horse_id <> ''
  AND rr.horse_id NOT IN (SELECT horse_id FROM horses)
ORDER BY rr.horse_id
"""

_Q_MISSING_JOCKEYS = """
SELECT DISTINCT rr.jockey_id
FROM race_results rr
WHERE rr.jockey_id IS NOT NULL
  AND rr.jockey_id <> ''
  AND rr.jockey_id NOT IN (SELECT jockey_id FROM jockeys)
ORDER BY rr.jockey_id
"""

_Q_MISSING_TRAINERS = """
SELECT DISTINCT rr.trainer_id
FROM race_results rr
WHERE rr.trainer_id IS NOT NULL
  AND rr.trainer_id <> ''
  AND rr.trainer_id NOT IN (SELECT trainer_id FROM trainers)
ORDER BY rr.trainer_id
"""

_Q_MISSING_RACES = """
SELECT r.race_id
FROM races r
WHERE NOT EXISTS (
    SELECT 1 FROM race_results rr
    WHERE rr.race_id = r.race_id
)
  AND TO_DATE(r.date, 'YYYY/MM/DD') < CURRENT_DATE
ORDER BY r.date DESC
"""


def _fetch_missing_ids(conn: psycopg.Connection, query: str) -> list[str]:
    with conn.cursor() as cur:
        cur.execute(query)
        return [row[0] for row in cur.fetchall()]


# --------------------------------------------------------------------------- #
# 補完処理
# --------------------------------------------------------------------------- #


def backfill_races(
    race_ids: list[str],
    db: Database,
    client: NetkeibaClient,
) -> tuple[int, int]:
    """結果未取得レースを1件ずつスクレイプして補完する。(成功数, 失敗数) を返す。"""
    if not race_ids:
        logger.info("未取得レースはありません。")
        return 0, 0

    logger.info("未取得レース %d 件を補完します。", len(race_ids))
    parser = RaceDetailParser()
    ok = fail = 0
    for i, race_id in enumerate(race_ids, start=1):
        logger.info("[レース %d/%d] %s を取得中...", i, len(race_ids), race_id)
        try:
            html = client.get_race(race_id)
            race_info = parser.parse_race_info(html)
            results = parser.parse(html)
            payoffs = parser.parse_payoff(html)
            db.save_race(race_id, race_info, results, payoffs)
            ok += 1
        except Exception:
            logger.exception(
                "レース %s の取得に失敗しました。スキップします。", race_id
            )
            fail += 1
    return ok, fail


def backfill_horses(
    horse_ids: list[str],
    db: Database,
    client: NetkeibaClient,
) -> tuple[int, int]:
    """未登録馬を1頭ずつスクレイプして補完する。(成功数, 失敗数) を返す。"""
    if not horse_ids:
        logger.info("未登録馬はありません。")
        return 0, 0

    logger.info("未登録馬 %d 頭を補完します。", len(horse_ids))
    parser = HorseParser()
    ok = fail = 0
    for i, horse_id in enumerate(horse_ids, start=1):
        logger.info("[馬 %d/%d] %s を取得中...", i, len(horse_ids), horse_id)
        try:
            html = client.get_horse(horse_id)
            profile, _ = parser.parse(html)
            db.save_horse(horse_id, profile)
            ok += 1
        except Exception:
            logger.exception("馬 %s の取得に失敗しました。スキップします。", horse_id)
            fail += 1
    return ok, fail


def backfill_jockeys(
    jockey_ids: list[str],
    db: Database,
    client: NetkeibaClient,
) -> tuple[int, int]:
    """未登録騎手を1名ずつスクレイプして補完する。(成功数, 失敗数) を返す。"""
    if not jockey_ids:
        logger.info("未登録騎手はありません。")
        return 0, 0

    logger.info("未登録騎手 %d 名を補完します。", len(jockey_ids))
    parser = JockeyParser()
    ok = fail = 0
    for i, jockey_id in enumerate(jockey_ids, start=1):
        logger.info("[騎手 %d/%d] %s を取得中...", i, len(jockey_ids), jockey_id)
        try:
            html = client.get_jockey(jockey_id)
            profile = parser.parse(html)
            db.save_jockey(jockey_id, profile)
            ok += 1
        except Exception:
            logger.exception(
                "騎手 %s の取得に失敗しました。スキップします。", jockey_id
            )
            fail += 1
    return ok, fail


def backfill_trainers(
    trainer_ids: list[str],
    db: Database,
    client: NetkeibaClient,
) -> tuple[int, int]:
    """未登録調教師を1名ずつスクレイプして補完する。(成功数, 失敗数) を返す。"""
    if not trainer_ids:
        logger.info("未登録調教師はありません。")
        return 0, 0

    logger.info("未登録調教師 %d 名を補完します。", len(trainer_ids))
    parser = TrainerParser()
    ok = fail = 0
    for i, trainer_id in enumerate(trainer_ids, start=1):
        logger.info("[調教師 %d/%d] %s を取得中...", i, len(trainer_ids), trainer_id)
        try:
            html = client.get_trainer(trainer_id)
            profile = parser.parse(html)
            db.save_trainer(trainer_id, profile)
            ok += 1
        except Exception:
            logger.exception(
                "調教師 %s の取得に失敗しました。スキップします。", trainer_id
            )
            fail += 1
    return ok, fail


def backfill_force_shutuba(
    race_ids: list[str],
    db: Database,
    client: NetkeibaClient,
) -> tuple[int, int]:
    """指定した race_id の出馬表を強制再取得して DB を上書きする。(成功数, 失敗数) を返す。"""
    if not race_ids:
        return 0, 0

    logger.info("出馬表を強制再取得: %d 件", len(race_ids))
    parser = ShutsubaParser()
    ok = fail = 0
    for i, race_id in enumerate(race_ids, start=1):
        logger.info("[%d/%d] 出馬表 %s を再取得中...", i, len(race_ids), race_id)
        try:
            html = client.get_shutuba(race_id)
            race_info = parser.parse_race_info(html)
            rows = parser.parse(html)
            db.save_race(race_id, race_info, rows)
            ok += 1
        except Exception:
            logger.exception(
                "出馬表 %s の再取得に失敗しました。スキップします。", race_id
            )
            fail += 1
    return ok, fail


# --------------------------------------------------------------------------- #
# エントリーポイント
# --------------------------------------------------------------------------- #


def main() -> None:
    parser = argparse.ArgumentParser(
        description="未登録の馬・騎手・調教師・レース結果を遡及補完する"
    )
    parser.add_argument(
        "--horses-only",
        action="store_true",
        help="馬のみ補完する（騎手・調教師・レース結果をスキップ）",
    )
    parser.add_argument(
        "--force",
        nargs="+",
        metavar="RACE_ID",
        help="指定した race_id の出馬表を強制再取得して DB を上書きする",
    )
    args = parser.parse_args()

    try:
        database_url = os.environ["DATABASE_URL"]
    except KeyError:
        print("環境変数 DATABASE_URL が設定されていません。", file=sys.stderr)
        sys.exit(1)

    # --force モード: 指定 race_id を再取得して終了
    if args.force:
        db = Database(database_url)
        with NetkeibaClient() as client:
            ok, fail = backfill_force_shutuba(args.force, db, client)
        print()
        print("=== 強制再取得 完了 ===")
        print(f"出馬表: 成功 {ok} 件 / 失敗 {fail} 件")
        return

    with psycopg.connect(database_url) as conn:
        race_ids = (
            _fetch_missing_ids(conn, _Q_MISSING_RACES) if not args.horses_only else []
        )
        horse_ids = _fetch_missing_ids(conn, _Q_MISSING_HORSES)
        if not args.horses_only:
            jockey_ids = _fetch_missing_ids(conn, _Q_MISSING_JOCKEYS)
            trainer_ids = _fetch_missing_ids(conn, _Q_MISSING_TRAINERS)
        else:
            jockey_ids = []
            trainer_ids = []

    logger.info(
        "補完対象: レース結果 %d 件 / 馬 %d 頭 / 騎手 %d 名 / 調教師 %d 名",
        len(race_ids),
        len(horse_ids),
        len(jockey_ids),
        len(trainer_ids),
    )

    if not race_ids and not horse_ids and not jockey_ids and not trainer_ids:
        logger.info("補完対象がありません。終了します。")
        return

    db = Database(database_url)
    with NetkeibaClient() as client:
        r_ok, r_fail = backfill_races(race_ids, db, client)
        h_ok, h_fail = backfill_horses(horse_ids, db, client)
        j_ok, j_fail = backfill_jockeys(jockey_ids, db, client)
        t_ok, t_fail = backfill_trainers(trainer_ids, db, client)

    print()
    print("=== 遡及補完 完了 ===")
    if not args.horses_only:
        print(f"レース結果: 成功 {r_ok} 件 / 失敗 {r_fail} 件")
    print(f"馬        : 成功 {h_ok} 頭 / 失敗 {h_fail} 頭")
    if not args.horses_only:
        print(f"騎手      : 成功 {j_ok} 名 / 失敗 {j_fail} 名")
        print(f"調教師    : 成功 {t_ok} 名 / 失敗 {t_fail} 名")


if __name__ == "__main__":
    main()

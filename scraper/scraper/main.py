"""スクレイパーエントリーポイント"""

import logging
import os
import sys

from dotenv import load_dotenv

from .client import NetkeibaClient
from repository import Database
from .parsers import HorseParser, RaceDetailParser, ShutsubaParser

load_dotenv()

DATABASE_URL = os.environ["DATABASE_URL"]

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def scrape_race(race_id: str) -> None:
    """指定レースIDのレースページをスクレイピングして DB に保存する."""
    parser = RaceDetailParser()

    with NetkeibaClient() as client:
        logger.info("レース %s を取得中...", race_id)
        html = client.get_race(race_id)

    race_info = parser.parse_race_info(html)
    results = parser.parse(html)
    payoffs = parser.parse_payoff(html)

    db = Database(DATABASE_URL)
    db.save_race(race_id, race_info, results, payoffs)


def scrape_horse(horse_id: str) -> None:
    """指定馬IDの馬ページをスクレイピングして DB に保存する."""
    parser = HorseParser()

    with NetkeibaClient() as client:
        logger.info("馬 %s を取得中...", horse_id)
        html = client.get_horse(horse_id)

    profile, _ = parser.parse(html)

    db = Database(DATABASE_URL)
    db.save_horse(horse_id, profile)


def scrape_shutuba(race_id: str) -> None:
    """指定レースIDの出馬表をスクレイピングして DB に保存する.

    未登録馬は scrape_horse() で自動補完する。
    """
    parser = ShutsubaParser()

    with NetkeibaClient() as client:
        logger.info("出馬表 %s を取得中...", race_id)
        html = client.get_shutuba(race_id)

    race_info = parser.parse_race_info(html)
    rows = parser.parse(html)

    db = Database(DATABASE_URL)
    db.save_race(race_id, race_info, rows)

    # 未登録馬を自動補完
    horse_ids = [row["馬ID"] for row in rows if row.get("馬ID")]
    existing_ids = db.get_existing_horse_ids(horse_ids)
    missing_ids = [hid for hid in horse_ids if hid not in existing_ids]

    if missing_ids:
        logger.info("未登録馬 %d 頭を補完します: %s", len(missing_ids), missing_ids)
        for horse_id in missing_ids:
            scrape_horse(horse_id)
    else:
        logger.info("全馬登録済み。補完不要。")


def main() -> None:
    if len(sys.argv) < 3:
        print("使用方法: python -m scraper <mode> <id>")
        print("  mode=race    例: python -m scraper race 202506050801")
        print("  mode=horse   例: python -m scraper horse 2019105806")
        print("  mode=shutuba 例: python -m scraper shutuba 202506050801")
        sys.exit(1)

    mode = sys.argv[1]
    target_id = sys.argv[2]

    if mode == "race":
        scrape_race(target_id)
    elif mode == "horse":
        scrape_horse(target_id)
    elif mode == "shutuba":
        scrape_shutuba(target_id)
    else:
        print(f"不明なmode: {mode}")
        sys.exit(1)


if __name__ == "__main__":
    main()

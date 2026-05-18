"""スクレイパーエントリーポイント"""

import logging
import os
import sys

from dotenv import load_dotenv

from .client import NetkeibaClient
from .database import Database
from .parsers import HorseParser, RaceDetailParser

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


def main() -> None:
    if len(sys.argv) < 3:
        print("使用方法: python -m scraper <mode> <id>")
        print("  mode=race  例: python -m scraper race 202506050801")
        print("  mode=horse 例: python -m scraper horse 2019105806")
        sys.exit(1)

    mode = sys.argv[1]
    target_id = sys.argv[2]

    if mode == "race":
        scrape_race(target_id)
    elif mode == "horse":
        scrape_horse(target_id)
    else:
        print(f"不明なmode: {mode}")
        sys.exit(1)


if __name__ == "__main__":
    main()

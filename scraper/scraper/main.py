"""スクレイパーエントリーポイント"""

import logging
import os
import sys

from dotenv import load_dotenv

from .client import NetkeibaClient
from .parsers import HorseParser, RaceDetailParser

load_dotenv()

DATABASE_URL = os.environ["DATABASE_URL"]

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def scrape_race(race_id: str) -> None:
    """指定レースIDのレースページをスクレイピングしてログ出力する."""
    parser = RaceDetailParser()

    with NetkeibaClient() as client:
        logger.info("レース %s を取得中...", race_id)
        html = client.get_race(race_id)

    race_info = parser.parse_race_info(html)
    results = parser.parse(html)
    payoffs = parser.parse_payoff(html)

    logger.info("レース情報: %s", race_info)
    logger.info("出走馬数: %d", len(results))
    logger.info("払い戻し件数: %d", len(payoffs))

    for row in results:
        logger.info("  %s着 %s %s", row.get("着順"), row.get("馬番"), row.get("馬名"))


def scrape_horse(horse_id: str) -> None:
    """指定馬IDの馬ページをスクレイピングしてログ出力する."""
    parser = HorseParser()

    with NetkeibaClient() as client:
        logger.info("馬 %s を取得中...", horse_id)
        html = client.get_horse(horse_id)

    profile, race_results = parser.parse(html)

    logger.info("馬名: %s", profile.get("馬名"))
    logger.info("性別: %s  毛色: %s", profile.get("性別"), profile.get("毛色"))
    logger.info("父: %s  母: %s", profile.get("父"), profile.get("母"))
    logger.info("母父: %s", profile.get("母父"))
    logger.info("競走成績件数: %d", len(race_results))


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

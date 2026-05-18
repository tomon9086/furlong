"""スクレイパーエントリーポイント"""

import logging
import os
import sys

from dotenv import load_dotenv

from .client import NetkeibaClient
from .parsers import RaceDetailParser

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


def main() -> None:
    if len(sys.argv) < 2:
        print("使用方法: python -m scraper <race_id>")
        print("例: python -m scraper 202506050801")
        sys.exit(1)

    race_id = sys.argv[1]
    scrape_race(race_id)


if __name__ == "__main__":
    main()

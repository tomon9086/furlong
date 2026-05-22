"""スクレイパースケジューラ

APScheduler を使い、以下の定期バッチを実行する:
  - 14:00 : scrape_incremental()  — 当月までの差分レース結果を収集
  - 22:00 : scrape_shutuba_upcoming() — 翌日の出馬表を収集
"""

import logging

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from .main import scrape_incremental, scrape_shutuba_upcoming

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _job_incremental() -> None:
    logger.info("=== [scheduler] scrape_incremental 開始 ===")
    try:
        scrape_incremental()
    except Exception:
        logger.exception("scrape_incremental でエラーが発生しました。")
    logger.info("=== [scheduler] scrape_incremental 完了 ===")


def _job_shutuba() -> None:
    logger.info("=== [scheduler] scrape_shutuba_upcoming 開始 ===")
    try:
        scrape_shutuba_upcoming()
    except Exception:
        logger.exception("scrape_shutuba_upcoming でエラーが発生しました。")
    logger.info("=== [scheduler] scrape_shutuba_upcoming 完了 ===")


def main() -> None:
    scheduler = BlockingScheduler(timezone="Asia/Tokyo")

    scheduler.add_job(
        _job_incremental,
        trigger=CronTrigger(hour=14, minute=0, timezone="Asia/Tokyo"),
        id="scrape_incremental",
        name="差分レース結果収集 (14:00)",
        max_instances=1,
        misfire_grace_time=3600,
    )

    scheduler.add_job(
        _job_shutuba,
        trigger=CronTrigger(hour=22, minute=0, timezone="Asia/Tokyo"),
        id="scrape_shutuba_upcoming",
        name="翌日出馬表収集 (22:00)",
        max_instances=1,
        misfire_grace_time=3600,
    )

    logger.info("スケジューラを起動しました。14:00 に差分収集、22:00 に出馬表収集を実行します。")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("スケジューラを停止しました。")


if __name__ == "__main__":
    main()

"""スクレイパーエントリーポイント"""

import logging
import os
import sys
from datetime import date, timedelta

from dotenv import load_dotenv

from .client import NetkeibaClient
from repository import Database
from .parsers import HorseParser, JockeyParser, RaceDetailParser, RaceListParser, ShutsubaParser, TrainerParser

load_dotenv()

DATABASE_URL = os.environ["DATABASE_URL"]

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def scrape_race(race_id: str) -> None:
    """指定レースIDのレースページをスクレイピングして DB に保存する."""
    parser = RaceDetailParser()
    db = Database(DATABASE_URL)

    with NetkeibaClient() as client:
        logger.info("レース %s を取得中...", race_id)
        html = client.get_race(race_id)

        race_info = parser.parse_race_info(html)
        results = parser.parse(html)
        payoffs = parser.parse_payoff(html)

        db.save_race(race_id, race_info, results, payoffs)

        # 未登録騎手・調教師を自動補完
        _supplement_jockeys_and_trainers(results, db, client)


def scrape_horse(horse_id: str) -> None:
    """指定馬IDの馬ページをスクレイピングして DB に保存する."""
    parser = HorseParser()

    with NetkeibaClient() as client:
        logger.info("馬 %s を取得中...", horse_id)
        html = client.get_horse(horse_id)

    profile, _ = parser.parse(html)

    db = Database(DATABASE_URL)
    db.save_horse(horse_id, profile)


def scrape_jockey(jockey_id: str) -> None:
    """指定騎手IDの騎手ページをスクレイピングして DB に保存する."""
    parser = JockeyParser()

    with NetkeibaClient() as client:
        logger.info("騎手 %s を取得中...", jockey_id)
        html = client.get_jockey(jockey_id)

    profile = parser.parse(html)

    db = Database(DATABASE_URL)
    db.save_jockey(jockey_id, profile)


def scrape_trainer(trainer_id: str) -> None:
    """指定調教師IDの調教師ページをスクレイピングして DB に保存する."""
    parser = TrainerParser()

    with NetkeibaClient() as client:
        logger.info("調教師 %s を取得中...", trainer_id)
        html = client.get_trainer(trainer_id)

    profile = parser.parse(html)

    db = Database(DATABASE_URL)
    db.save_trainer(trainer_id, profile)


def _supplement_jockeys_and_trainers(
    rows: list,
    db: "Database",
    client: "NetkeibaClient",
) -> None:
    """rows に含まれる騎手・調教師のうち未登録のものを補完する."""
    jockey_ids = list(dict.fromkeys(row["騎手ID"] for row in rows if row.get("騎手ID")))
    trainer_ids = list(dict.fromkeys(row["調教師ID"] for row in rows if row.get("調教師ID")))

    if jockey_ids:
        existing_jockey_ids = db.get_existing_jockey_ids(jockey_ids)
        missing_jockey_ids = [jid for jid in jockey_ids if jid not in existing_jockey_ids]
        if missing_jockey_ids:
            logger.info(
                "未登録騎手 %d 名を補完します: %s", len(missing_jockey_ids), missing_jockey_ids
            )
            jockey_parser = JockeyParser()
            for jockey_id in missing_jockey_ids:
                try:
                    html = client.get_jockey(jockey_id)
                    profile = jockey_parser.parse(html)
                    db.save_jockey(jockey_id, profile)
                except Exception:
                    logger.exception("騎手 %s の取得に失敗しました。スキップします。", jockey_id)

    if trainer_ids:
        existing_trainer_ids = db.get_existing_trainer_ids(trainer_ids)
        missing_trainer_ids = [tid for tid in trainer_ids if tid not in existing_trainer_ids]
        if missing_trainer_ids:
            logger.info(
                "未登録調教師 %d 名を補完します: %s", len(missing_trainer_ids), missing_trainer_ids
            )
            trainer_parser = TrainerParser()
            for trainer_id in missing_trainer_ids:
                try:
                    html = client.get_trainer(trainer_id)
                    profile = trainer_parser.parse(html)
                    db.save_trainer(trainer_id, profile)
                except Exception:
                    logger.exception("調教師 %s の取得に失敗しました。スキップします。", trainer_id)


def scrape_shutuba(race_id: str) -> None:
    """指定レースIDの出馬表をスクレイピングして DB に保存する.

    未登録馬は scrape_horse() で自動補完する。
    """
    parser = ShutsubaParser()

    db = Database(DATABASE_URL)

    with NetkeibaClient() as client:
        logger.info("出馬表 %s を取得中...", race_id)
        html = client.get_shutuba(race_id)

        race_info = parser.parse_race_info(html)
        rows = parser.parse(html)

        db.save_race(race_id, race_info, rows)

        # 未登録馬を自動補完
        horse_ids = [row["馬ID"] for row in rows if row.get("馬ID")]
        existing_horse_ids = db.get_existing_horse_ids(horse_ids)
        missing_horse_ids = [hid for hid in horse_ids if hid not in existing_horse_ids]

        if missing_horse_ids:
            logger.info("未登録馬 %d 頭を補完します: %s", len(missing_horse_ids), missing_horse_ids)
            horse_parser = HorseParser()
            for horse_id in missing_horse_ids:
                try:
                    horse_html = client.get_horse(horse_id)
                    profile, _ = horse_parser.parse(horse_html)
                    db.save_horse(horse_id, profile)
                except Exception:
                    logger.exception("馬 %s の取得に失敗しました。スキップします。", horse_id)
        else:
            logger.info("全馬登録済み。補完不要。")

        # 未登録騎手・調教師を自動補完
        _supplement_jockeys_and_trainers(rows, db, client)


def scrape_backfill(year: int, month: int) -> None:
    """指定年月の全レースをスクレイピングして DB に保存する.

    レース一覧ページを全ページ走査し、DB に未登録のレースのみ取得する。
    クライアントを使い回すことでインターバルが正しく機能する。
    """
    list_parser = RaceListParser()
    race_parser = RaceDetailParser()
    db = Database(DATABASE_URL)

    with NetkeibaClient() as client:
        # 1ページ目を取得して総ページ数を確認
        logger.info("%d年%d月のレース一覧を取得中...", year, month)
        first_html = client.get_race_list(year, month, year, month, page=1)
        total_pages = list_parser.parse_total_pages(first_html)
        logger.info("総ページ数: %d", total_pages)

        all_race_ids: list[str] = list_parser.parse(first_html)

        for page in range(2, total_pages + 1):
            logger.info("ページ %d/%d を取得中...", page, total_pages)
            html = client.get_race_list(year, month, year, month, page=page)
            all_race_ids.extend(list_parser.parse(html))

        logger.info("一覧から取得したレース数: %d", len(all_race_ids))

        # DB に未登録のレースだけ対象にする
        existing_ids = db.get_existing_race_ids(all_race_ids)
        missing_ids = [rid for rid in all_race_ids if rid not in existing_ids]
        logger.info(
            "未登録レース数: %d（スキップ: %d）", len(missing_ids), len(existing_ids)
        )

        for i, race_id in enumerate(missing_ids, start=1):
            logger.info("[%d/%d] レース %s を取得中...", i, len(missing_ids), race_id)
            try:
                html = client.get_race(race_id)
                race_info = race_parser.parse_race_info(html)
                results = race_parser.parse(html)
                payoffs = race_parser.parse_payoff(html)
                db.save_race(race_id, race_info, results, payoffs)
                _supplement_jockeys_and_trainers(results, db, client)
            except Exception:
                logger.exception(
                    "レース %s の取得に失敗しました。スキップします。", race_id
                )


def scrape_incremental(start_date: date | None = None) -> None:
    """最終取得日の翌月から今月までの全レースを差分スクレイピングする.

    Args:
        start_date: スクレイピング開始月を指定する場合に渡す (手動実行用)。
                    省略時は DB の最新レース日付の月を開始月とする。
                    DB が空の場合はエラーを出力して終了する。
    """
    today = date.today()

    if start_date is not None:
        start_year, start_month = start_date.year, start_date.month
    else:
        db = Database(DATABASE_URL)
        latest = db.get_latest_race_date()
        if latest is None:
            logger.error(
                "DB にレースが1件もありません。--start-date で開始月を指定してください。"
            )
            return
        start_year, start_month = latest

    logger.info(
        "%d年%d月 〜 %d年%d月 の差分スクレイピングを開始します。",
        start_year,
        start_month,
        today.year,
        today.month,
    )

    year, month = start_year, start_month
    while (year, month) <= (today.year, today.month):
        logger.info("=== %d年%d月 ===", year, month)
        scrape_backfill(year, month)
        if month == 12:
            year, month = year + 1, 1
        else:
            month += 1


def scrape_shutuba_upcoming(target_date: date | None = None) -> None:
    """翌日（または指定日）の未取得出馬表を検索して保存する.

    Args:
        target_date: 取得対象日を指定する場合に渡す（手動実行用）。
                     省略時は翌日の出馬表を取得する。
    """
    if target_date is None:
        target_date = date.today() + timedelta(days=1)

    kaisai_date = target_date.strftime("%Y%m%d")
    logger.info("%s の出馬表を取得します。", kaisai_date)

    list_parser = RaceListParser()
    db = Database(DATABASE_URL)

    with NetkeibaClient() as client:
        html = client.get_race_list_by_date(kaisai_date)
        race_ids = list_parser.parse_by_date(html)

    logger.info("%s のレース数: %d", kaisai_date, len(race_ids))
    if not race_ids:
        logger.info("対象レースが見つかりませんでした。")
        return

    existing_ids = db.get_existing_race_ids(race_ids)
    missing_ids = [rid for rid in race_ids if rid not in existing_ids]
    logger.info(
        "未取得出馬表: %d件（スキップ: %d件）", len(missing_ids), len(existing_ids)
    )

    for i, race_id in enumerate(missing_ids, start=1):
        logger.info("[%d/%d] 出馬表 %s を取得中...", i, len(missing_ids), race_id)
        try:
            scrape_shutuba(race_id)
        except Exception:
            logger.exception(
                "出馬表 %s の取得に失敗しました。スキップします。", race_id
            )


def main() -> None:
    if len(sys.argv) < 2:
        print("使用方法: python -m scraper <mode> [args...]")
        print("  mode=race              例: python -m scraper race 202506050801")
        print("  mode=horse             例: python -m scraper horse 2019105806")
        print("  mode=jockey            例: python -m scraper jockey 05212")
        print("  mode=trainer           例: python -m scraper trainer 01120")
        print("  mode=shutuba           例: python -m scraper shutuba 202506050801")
        print("  mode=shutuba_upcoming  例: python -m scraper shutuba_upcoming")
        print(
            "                             python -m scraper shutuba_upcoming 2026 5 23"
        )
        print("  mode=backfill          例: python -m scraper backfill 2026 1")
        print("  mode=incremental       例: python -m scraper incremental")
        print("                             python -m scraper incremental 2026 5")
        sys.exit(1)

    mode = sys.argv[1]

    if mode == "race":
        if len(sys.argv) < 3:
            print("使用方法: python -m scraper race <race_id>")
            sys.exit(1)
        scrape_race(sys.argv[2])
    elif mode == "horse":
        if len(sys.argv) < 3:
            print("使用方法: python -m scraper horse <horse_id>")
            sys.exit(1)
        scrape_horse(sys.argv[2])
    elif mode == "jockey":
        if len(sys.argv) < 3:
            print("使用方法: python -m scraper jockey <jockey_id>")
            sys.exit(1)
        scrape_jockey(sys.argv[2])
    elif mode == "trainer":
        if len(sys.argv) < 3:
            print("使用方法: python -m scraper trainer <trainer_id>")
            sys.exit(1)
        scrape_trainer(sys.argv[2])
    elif mode == "shutuba":
        if len(sys.argv) < 3:
            print("使用方法: python -m scraper shutuba <race_id>")
            sys.exit(1)
        scrape_shutuba(sys.argv[2])
    elif mode == "shutuba_upcoming":
        if len(sys.argv) >= 5:
            target = date(int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]))
            scrape_shutuba_upcoming(target_date=target)
        else:
            scrape_shutuba_upcoming()
    elif mode == "backfill":
        if len(sys.argv) < 4:
            print("使用方法: python -m scraper backfill <year> <month>")
            print("  例: python -m scraper backfill 2026 1")
            sys.exit(1)
        scrape_backfill(int(sys.argv[2]), int(sys.argv[3]))
    elif mode == "incremental":
        if len(sys.argv) >= 4:
            start = date(int(sys.argv[2]), int(sys.argv[3]), 1)
            scrape_incremental(start_date=start)
        else:
            scrape_incremental()
    else:
        print(f"不明なmode: {mode}")
        sys.exit(1)


if __name__ == "__main__":
    main()

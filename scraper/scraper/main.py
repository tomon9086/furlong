"""スクレイパーエントリーポイント"""

import logging
import os
import sys
from datetime import date, timedelta

from dotenv import load_dotenv

from .client import NetkeibaClient
from repository import Database
from .parsers import (
    HorseParser,
    JockeyParser,
    OddsParser,
    RaceDetailParser,
    RaceListParser,
    ShutsubaParser,
    TrainerParser,
)

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

        # 未登録馬を自動補完
        _supplement_horses(results, db, client)

        # 未登録騎手・調教師を自動補完
        _supplement_jockeys_and_trainers(results, db, client)


def scrape_odds(race_id: str) -> None:
    """指定レースIDの単勝オッズページをスクレイピングして DB に保存する."""
    parser = OddsParser()
    db = Database(DATABASE_URL)

    with NetkeibaClient() as client:
        logger.info("レース %s の単勝オッズを取得中...", race_id)
        html = client.get_odds(race_id)

    rows = parser.parse(html)
    db.save_pre_race_odds(race_id, rows)


def _fetch_horse_profile(
    client: "NetkeibaClient", parser: "HorseParser", horse_id: str
) -> tuple[dict, list]:
    """馬のプロフィール・競走成績・血統をまとめて取得する.

    血統テーブルは馬詳細ページ (/horse/{horse_id}/) には含まれなくなった
    （2026年頃の netkeiba 仕様変更）ため、専用の血統ページを別途取得して merge する。
    """
    html = client.get_horse(horse_id)
    profile, race_results = parser.parse(html)

    pedigree_html = client.get_horse_pedigree(horse_id)
    profile.update(parser.parse_pedigree(pedigree_html))  # type: ignore[arg-type]

    return profile, race_results


def scrape_horse(horse_id: str) -> None:
    """指定馬IDの馬ページをスクレイピングして DB に保存する."""
    parser = HorseParser()

    with NetkeibaClient() as client:
        logger.info("馬 %s を取得中...", horse_id)
        profile, _ = _fetch_horse_profile(client, parser, horse_id)

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


def _supplement_horses(
    rows: list,
    db: "Database",
    client: "NetkeibaClient",
) -> None:
    """rows に含まれる馬のうち未登録のものを補完する."""
    horse_ids = list(dict.fromkeys(row["馬ID"] for row in rows if row.get("馬ID")))
    if not horse_ids:
        return

    existing_horse_ids = db.get_existing_horse_ids(horse_ids)
    missing_horse_ids = [hid for hid in horse_ids if hid not in existing_horse_ids]

    if not missing_horse_ids:
        logger.info("全馬登録済み。補完不要。")
        return

    logger.info(
        "未登録馬 %d 頭を補完します: %s",
        len(missing_horse_ids),
        missing_horse_ids,
    )
    horse_parser = HorseParser()
    for horse_id in missing_horse_ids:
        try:
            profile, _ = _fetch_horse_profile(client, horse_parser, horse_id)
            db.save_horse(horse_id, profile)
        except Exception:
            logger.exception("馬 %s の取得に失敗しました。スキップします。", horse_id)


def _supplement_jockeys_and_trainers(
    rows: list,
    db: "Database",
    client: "NetkeibaClient",
) -> None:
    """rows に含まれる騎手・調教師のうち未登録のものを補完する."""
    jockey_ids = list(dict.fromkeys(row["騎手ID"] for row in rows if row.get("騎手ID")))
    trainer_ids = list(
        dict.fromkeys(row["調教師ID"] for row in rows if row.get("調教師ID"))
    )

    if jockey_ids:
        existing_jockey_ids = db.get_existing_jockey_ids(jockey_ids)
        missing_jockey_ids = [
            jid for jid in jockey_ids if jid not in existing_jockey_ids
        ]
        if missing_jockey_ids:
            logger.info(
                "未登録騎手 %d 名を補完します: %s",
                len(missing_jockey_ids),
                missing_jockey_ids,
            )
            jockey_parser = JockeyParser()
            for jockey_id in missing_jockey_ids:
                try:
                    html = client.get_jockey(jockey_id)
                    profile = jockey_parser.parse(html)
                    db.save_jockey(jockey_id, profile)
                except Exception:
                    logger.exception(
                        "騎手 %s の取得に失敗しました。スキップします。", jockey_id
                    )

    if trainer_ids:
        existing_trainer_ids = db.get_existing_trainer_ids(trainer_ids)
        missing_trainer_ids = [
            tid for tid in trainer_ids if tid not in existing_trainer_ids
        ]
        if missing_trainer_ids:
            logger.info(
                "未登録調教師 %d 名を補完します: %s",
                len(missing_trainer_ids),
                missing_trainer_ids,
            )
            trainer_parser = TrainerParser()
            for trainer_id in missing_trainer_ids:
                try:
                    html = client.get_trainer(trainer_id)
                    profile = trainer_parser.parse(html)
                    db.save_trainer(trainer_id, profile)
                except Exception:
                    logger.exception(
                        "調教師 %s の取得に失敗しました。スキップします。", trainer_id
                    )


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
            logger.info(
                "未登録馬 %d 頭を補完します: %s",
                len(missing_horse_ids),
                missing_horse_ids,
            )
            horse_parser = HorseParser()
            for horse_id in missing_horse_ids:
                try:
                    profile, _ = _fetch_horse_profile(client, horse_parser, horse_id)
                    db.save_horse(horse_id, profile)
                except Exception:
                    logger.exception(
                        "馬 %s の取得に失敗しました。スキップします。", horse_id
                    )
        else:
            logger.info("全馬登録済み。補完不要。")

        # 未登録騎手・調教師を自動補完
        _supplement_jockeys_and_trainers(rows, db, client)


def scrape_backfill(
    year: int,
    month: int,
    venue_codes: list[str] | None = None,
    limit: int | None = None,
) -> int:
    """指定年月の全レースをスクレイピングして DB に保存する.

    レース一覧ページを全ページ走査し、DB に未登録のレースのみ取得する。
    クライアントを使い回すことでインターバルが正しく機能する。

    Parameters
    ----------
    venue_codes : list[str] | None
        指定した場合、race_id中のvenueコード（5〜6桁目）でフィルタする
        （地方競馬の場だけを対象にする遡及バックフィル用）。
    limit : int | None
        指定した場合、この呼び出しで新規保存する件数をその上限で打ち切る
        （複数月にまたがる累計件数を呼び出し側で制御するパイロット実行用）。

    Returns
    -------
    int
        この呼び出しで実際に保存できた件数。
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

        if venue_codes is not None:
            all_race_ids = [rid for rid in all_race_ids if rid[4:6] in venue_codes]
            logger.info("venueフィルタ後のレース数: %d", len(all_race_ids))

        # DB に未登録のレースだけ対象にする
        existing_ids = db.get_existing_race_ids(all_race_ids)
        missing_ids = [rid for rid in all_race_ids if rid not in existing_ids]
        if limit is not None:
            missing_ids = missing_ids[:limit]
        logger.info(
            "未登録レース数: %d（スキップ: %d）", len(missing_ids), len(existing_ids)
        )

        ok = 0
        for i, race_id in enumerate(missing_ids, start=1):
            logger.info("[%d/%d] レース %s を取得中...", i, len(missing_ids), race_id)
            try:
                html = client.get_race(race_id)
                race_info = race_parser.parse_race_info(html)
                results = race_parser.parse(html)
                payoffs = race_parser.parse_payoff(html)
                db.save_race(race_id, race_info, results, payoffs)
                _supplement_horses(results, db, client)
                _supplement_jockeys_and_trainers(results, db, client)
                ok += 1
            except Exception:
                logger.exception(
                    "レース %s の取得に失敗しました。スキップします。", race_id
                )
        return ok


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


def scrape_regional_backfill(
    venue_codes: list[str],
    start_year: int,
    start_mon: int,
    end_year: int,
    end_mon: int,
    limit: int | None = None,
) -> None:
    """地方競馬の指定venue・期間を遡及バックフィルする.

    直近月から過去に向かって1ヶ月ずつ `scrape_backfill` を呼び出す（新しいデータほど
    優先的に取得し、途中で打ち切ってもその時点までの分は無駄にならないようにするため）。

    Parameters
    ----------
    venue_codes : list[str]
        対象venueコードのリスト（例: ["42", "43", "44", "45"] = 浦和・船橋・大井・川崎）。
    limit : int | None
        指定した場合、累計保存件数がこれに達した時点で打ち切る（パイロット実行用）。
    """
    logger.info(
        "地方競馬遡及バックフィル: venue=%s 期間=%d年%d月〜%d年%d月 limit=%s",
        venue_codes,
        start_year,
        start_mon,
        end_year,
        end_mon,
        limit,
    )

    year, month = end_year, end_mon
    total = 0
    while (year, month) >= (start_year, start_mon):
        remaining = None if limit is None else limit - total
        if limit is not None and remaining <= 0:
            break
        logger.info("=== %d年%d月 (累計 %d件保存済み) ===", year, month, total)
        total += scrape_backfill(year, month, venue_codes=venue_codes, limit=remaining)
        if month == 1:
            year, month = year - 1, 12
        else:
            month -= 1

    logger.info("地方競馬遡及バックフィル完了: 累計 %d件保存", total)


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


def scrape_incremental_cli() -> None:
    """scrape-incremental コマンドのエントリポイント.

    使用方法:
        uv run scrape-incremental
        uv run scrape-incremental 2026 5
    """
    if len(sys.argv) >= 3:
        start = date(int(sys.argv[1]), int(sys.argv[2]), 1)
        scrape_incremental(start_date=start)
    else:
        scrape_incremental()


def main() -> None:
    if len(sys.argv) < 2:
        print("使用方法: python -m scraper <mode> [args...]")
        print("  mode=odds              例: python -m scraper odds 202506050801")
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
        print(
            "  mode=backfill_regional 例: python -m scraper backfill_regional "
            "44 2016 1 2026 7 [--limit 300]"
        )
        print(
            "                             "
            "(venue_codesはカンマ区切り。直近月から過去に向かって取得。"
            "--limitは累計保存件数の上限＝パイロット実行用)"
        )
        sys.exit(1)

    mode = sys.argv[1]

    if mode == "odds":
        if len(sys.argv) < 3:
            print("使用方法: python -m scraper odds <race_id>")
            sys.exit(1)
        scrape_odds(sys.argv[2])
    elif mode == "race":
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
    elif mode == "backfill_regional":
        if len(sys.argv) < 7:
            print(
                "使用方法: python -m scraper backfill_regional "
                "<venue_codes> <start_year> <start_mon> <end_year> <end_mon> [--limit N]"
            )
            print("  例: python -m scraper backfill_regional 44 2016 1 2026 7 --limit 300")
            sys.exit(1)
        venue_codes = sys.argv[2].split(",")
        start_year, start_mon = int(sys.argv[3]), int(sys.argv[4])
        end_year, end_mon = int(sys.argv[5]), int(sys.argv[6])
        limit = None
        if "--limit" in sys.argv:
            idx = sys.argv.index("--limit")
            limit = int(sys.argv[idx + 1])
        scrape_regional_backfill(
            venue_codes, start_year, start_mon, end_year, end_mon, limit=limit
        )
    else:
        print(f"不明なmode: {mode}")
        sys.exit(1)


if __name__ == "__main__":
    main()

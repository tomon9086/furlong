"""repository.database の統合テスト（実 PostgreSQL コンテナ使用）."""

import gzip
from decimal import Decimal

import psycopg

from repository.database import Database
from repository.models import HorseProfile, OddsRow, PayoffRow, RaceDetailRow, RaceInfo


class TestSaveRace:
    def test_inserts_race(self, db: Database, db_url: str) -> None:
        """レース情報が races テーブルに正しく保存される。"""
        race_info: RaceInfo = {
            "レース名": "テストレース",
            "R": "11",
            "日付": "2024/01/01",
            "開催": "東京",
            "コース種別": "芝",
            "距離": "1600m",
            "回り": "右",
            "天候": "晴",
            "馬場状態": "良",
            "グレード": "G1",
            "発走時刻": "15:40",
        }
        db.save_race("202401010101", race_info)

        with psycopg.connect(db_url) as conn:
            row = conn.execute(
                "SELECT race_name, distance, venue FROM races WHERE race_id = %s",
                ("202401010101",),
            ).fetchone()

        assert row is not None
        assert row[0] == "テストレース"
        assert row[1] == 1600
        assert row[2] == "東京"

    def test_upserts_race(self, db: Database, db_url: str) -> None:
        """同じ race_id で再保存すると行が重複せず、内容が更新される。"""
        db.save_race("R001", {"レース名": "旧レース名", "距離": "1800m"})
        db.save_race("R001", {"レース名": "新レース名", "距離": "1800m"})

        with psycopg.connect(db_url) as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM races WHERE race_id = %s", ("R001",)
            ).fetchone()[0]
            name = conn.execute(
                "SELECT race_name FROM races WHERE race_id = %s", ("R001",)
            ).fetchone()[0]

        assert count == 1
        assert name == "新レース名"

    def test_inserts_results(self, db: Database, db_url: str) -> None:
        """results 付きで保存すると race_results に行が挿入される。"""
        race_info: RaceInfo = {"レース名": "テストレース", "日付": "2024/01/01"}
        results: list[RaceDetailRow] = [
            {"馬番": "1", "着順": "1", "馬名": "テストウマA", "馬体重": "480(0)"},
            {"馬番": "2", "着順": "2", "馬名": "テストウマB", "馬体重": "460(-2)"},
        ]
        db.save_race("R002", race_info, results=results)

        with psycopg.connect(db_url) as conn:
            rows = conn.execute(
                """
                SELECT horse_number, horse_weight, horse_weight_diff
                FROM race_results
                WHERE race_id = %s
                ORDER BY horse_number
                """,
                ("R002",),
            ).fetchall()

        assert len(rows) == 2
        assert rows[0] == ("1", 480, 0)
        assert rows[1] == ("2", 460, -2)

    def test_inserts_payoffs(self, db: Database, db_url: str) -> None:
        """payoffs 付きで保存すると payoffs テーブルに行が挿入される。"""
        race_info: RaceInfo = {"レース名": "テストレース", "日付": "2024/01/01"}
        payoffs: list[PayoffRow] = [
            {"券種": "単勝", "組番": "3", "払戻金": "230", "人気": "1"},
            {"券種": "複勝", "組番": "3", "払戻金": "110", "人気": "1"},
        ]
        db.save_race("R003", race_info, payoffs=payoffs)

        with psycopg.connect(db_url) as conn:
            rows = conn.execute(
                "SELECT bet_type, combination, payout FROM payoffs WHERE race_id = %s ORDER BY id",
                ("R003",),
            ).fetchall()

        assert len(rows) == 2
        assert rows[0] == ("単勝", "3", "230")
        assert rows[1] == ("複勝", "3", "110")

    def test_replaces_results_on_resave(self, db: Database, db_url: str) -> None:
        """再保存時に古い race_results が削除されて新しいものに差し替わる。"""
        race_info: RaceInfo = {"レース名": "テストレース", "日付": "2024/01/01"}
        db.save_race(
            "R004",
            race_info,
            results=[
                {"馬番": "1", "着順": "1", "馬体重": "480(0)"},
                {"馬番": "2", "着順": "2", "馬体重": "460(0)"},
            ],
        )
        db.save_race(
            "R004",
            race_info,
            results=[
                {"馬番": "1", "着順": "2", "馬体重": "482(+2)"},
            ],
        )

        with psycopg.connect(db_url) as conn:
            rows = conn.execute(
                "SELECT horse_number FROM race_results WHERE race_id = %s",
                ("R004",),
            ).fetchall()

        assert len(rows) == 1
        assert rows[0][0] == "1"

    def test_no_results_leaves_race_results_empty(self, db: Database, db_url: str) -> None:
        """results を渡さない場合、race_results には行が挿入されない。"""
        db.save_race("R005", {"レース名": "テストレース"})

        with psycopg.connect(db_url) as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM race_results WHERE race_id = %s", ("R005",)
            ).fetchone()[0]

        assert count == 0


class TestSaveHorse:
    def test_inserts_horse(self, db: Database, db_url: str) -> None:
        """馬情報が horses テーブルに正しく保存される。"""
        profile: HorseProfile = {
            "馬名": "テストウマ",
            "性別": "牡",
            "毛色": "鹿毛",
            "生年月日": "2020/03/15",
            "父": "ディープインパクト",
        }
        db.save_horse("H001", profile)

        with psycopg.connect(db_url) as conn:
            row = conn.execute(
                "SELECT horse_name, sex, sire FROM horses WHERE horse_id = %s",
                ("H001",),
            ).fetchone()

        assert row == ("テストウマ", "牡", "ディープインパクト")

    def test_upserts_horse(self, db: Database, db_url: str) -> None:
        """同じ horse_id で再保存すると行が重複せず、内容が更新される。"""
        db.save_horse("H002", {"馬名": "旧馬名"})
        db.save_horse("H002", {"馬名": "新馬名"})

        with psycopg.connect(db_url) as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM horses WHERE horse_id = %s", ("H002",)
            ).fetchone()[0]
            name = conn.execute(
                "SELECT horse_name FROM horses WHERE horse_id = %s", ("H002",)
            ).fetchone()[0]

        assert count == 1
        assert name == "新馬名"


def _odds_row(
    bet_type: str,
    combination: str,
    odds: str,
    odds_max: str = "0.0",
    popularity: str = "1",
) -> OddsRow:
    return {
        "券種": bet_type,
        "組番": combination,
        "オッズ": odds,
        "オッズ上限": odds_max,
        "人気": popularity,
    }


class TestSaveOddsSnapshot:
    _ROWS: list[OddsRow] = [
        _odds_row("1", "12", "4.0"),
        _odds_row("1", "05", "---", popularity=""),
        _odds_row("5", "0712", "3.2", odds_max="3.7"),
        _odds_row("7", "030712", "11.3"),
        _odds_row("8", "030712", "53.9"),
    ]

    def test_saves_payload_and_final_odds(self, db: Database, db_url: str) -> None:
        """応答を gzip で保存し、final_odds に展開する。

        三連単と数値化できない行（取消馬の "---"）は final_odds に入れない。
        """
        payload = '{"status": "result"}'
        n = db.save_odds_snapshot(
            "201906050901", payload, "result", "2019-12-28 09:55:40", self._ROWS
        )
        assert n == 3

        with psycopg.connect(db_url) as conn:
            snap = conn.execute(
                "SELECT status, official_datetime, payload FROM odds_snapshots"
            ).fetchone()
            rows = conn.execute(
                "SELECT bet_type, combination, odds, odds_max, popularity "
                "FROM final_odds ORDER BY bet_type"
            ).fetchall()

        assert snap is not None
        assert snap[0] == "result"
        assert str(snap[1]) == "2019-12-28 09:55:40"
        assert gzip.decompress(snap[2]).decode("utf-8") == payload
        assert [(r[0], r[1], float(r[2]), r[3], r[4]) for r in rows] == [
            (1, "12", 4.0, None, 1),
            (5, "0712", 3.2, Decimal("3.7"), 1),
            (7, "030712", 11.3, None, 1),
        ]

    def test_resave_replaces_final_odds(self, db: Database, db_url: str) -> None:
        """再取得すると final_odds は置き換わり、odds_snapshots は履歴として増える。"""
        db.save_odds_snapshot("R001", "{}", "result", None, self._ROWS)
        db.save_odds_snapshot(
            "R001",
            "{}",
            "result",
            None,
            [_odds_row("1", "12", "5.0")],
        )

        with psycopg.connect(db_url) as conn:
            n_snap = conn.execute("SELECT count(*) FROM odds_snapshots").fetchone()
            rows = conn.execute("SELECT odds FROM final_odds").fetchall()

        assert n_snap is not None and n_snap[0] == 2
        assert [float(r[0]) for r in rows] == [5.0]

    def test_non_result_status_skips_final_odds(
        self, db: Database, db_url: str
    ) -> None:
        """status=NG（取得不可）は応答だけ保存し、final_odds には何も入れない。"""
        n = db.save_odds_snapshot("R002", '{"status": "NG"}', "NG", None, [])
        assert n == 0
        assert db.get_race_ids_with_odds_snapshot(["R002", "R003"]) == {"R002"}

        with psycopg.connect(db_url) as conn:
            count = conn.execute("SELECT count(*) FROM final_odds").fetchone()
        assert count is not None and count[0] == 0

    def test_middle_status_is_not_skipped(self, db: Database) -> None:
        """発走前オッズ（middle）だけのレースは、確定オッズの取得対象として残す。"""
        db.save_odds_snapshot("R004", "{}", "middle", None, self._ROWS)
        assert db.get_race_ids_with_odds_snapshot(["R004"]) == set()


class TestGetJraRaceIds:
    def test_filters_jra_venues_and_years(self, db: Database) -> None:
        """JRA 10場・指定期間のレースだけを新しい順に返す。

        地方の venue コード（例: 44=大井）は除く。
        """
        for race_id in ["200805010101", "201909050101", "202044010101", "202610010101"]:
            db.save_race(race_id, {"レース名": "テスト"})
        assert db.get_jra_race_ids(2008, 2025) == ["201909050101", "200805010101"]

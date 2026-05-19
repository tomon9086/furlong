"""repository.database の統合テスト（実 PostgreSQL コンテナ使用）."""

import psycopg

from repository.database import Database
from repository.models import HorseProfile, PayoffRow, RaceDetailRow, RaceInfo


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

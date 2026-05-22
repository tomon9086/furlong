"""データベース保存ヘルパー (psycopg3 + PostgreSQL)."""

import json
import logging
import re
from datetime import datetime

import psycopg

from .models import HorseProfile, JockeyProfile, PayoffRow, RaceDetailRow, RaceInfo, TrainerProfile

logger = logging.getLogger(__name__)


def _or_none(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped if stripped else None


def _parse_distance(value: str | None) -> int | None:
    if not value:
        return None
    m = re.search(r"(\d+)", value)
    return int(m.group(1)) if m else None


def _parse_horse_weight(value: str | None) -> int | None:
    if not value:
        return None
    m = re.search(r"(\d+)", value)
    return int(m.group(1)) if m else None


def _parse_horse_weight_diff(value: str | None) -> int | None:
    if not value:
        return None
    m = re.search(r"\(([+-]?\d+)\)", value)
    return int(m.group(1)) if m else None


class Database:
    """スクレイピング結果を PostgreSQL に保存するラッパー."""

    def __init__(self, database_url: str) -> None:
        self._database_url = database_url

    def save_race(
        self,
        race_id: str,
        race_info: RaceInfo,
        results: list[RaceDetailRow] | None = None,
        payoffs: list[PayoffRow] | None = None,
    ) -> None:
        """レース情報・結果・払い戻しを保存（upsert）."""
        now = datetime.now()
        with psycopg.connect(self._database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO races (
                        race_id, race_name, race_number, date, venue,
                        course_type, distance, direction, weather,
                        track_condition, grade, start_time, head_count,
                        raw_data, created_at, updated_at
                    ) VALUES (
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s,
                        %s, %s, %s, %s,
                        %s, %s, %s
                    )
                    ON CONFLICT (race_id) DO UPDATE SET
                        race_name = EXCLUDED.race_name,
                        race_number = EXCLUDED.race_number,
                        date = EXCLUDED.date,
                        venue = EXCLUDED.venue,
                        course_type = EXCLUDED.course_type,
                        distance = EXCLUDED.distance,
                        direction = EXCLUDED.direction,
                        weather = EXCLUDED.weather,
                        track_condition = EXCLUDED.track_condition,
                        grade = EXCLUDED.grade,
                        start_time = EXCLUDED.start_time,
                        head_count = EXCLUDED.head_count,
                        raw_data = EXCLUDED.raw_data,
                        updated_at = EXCLUDED.updated_at
                    """,
                    (
                        race_id,
                        _or_none(race_info.get("レース名")),
                        _or_none(race_info.get("R")),
                        _or_none(race_info.get("日付")),
                        _or_none(race_info.get("開催")),
                        _or_none(race_info.get("コース種別")),
                        _parse_distance(race_info.get("距離")),
                        _or_none(race_info.get("回り")),
                        _or_none(race_info.get("天候")),
                        _or_none(race_info.get("馬場状態")),
                        _or_none(race_info.get("グレード")),
                        _or_none(race_info.get("発走時刻")),
                        len(results) if results else None,
                        json.dumps(dict(race_info), ensure_ascii=False),
                        now,
                        now,
                    ),
                )

                if results:
                    cur.execute(
                        "DELETE FROM race_results WHERE race_id = %s",
                        (race_id,),
                    )
                    for row in results:
                        hw = row.get("馬体重")
                        cur.execute(
                            """
                            INSERT INTO race_results (
                                race_id, horse_number,
                                finishing_position, bracket_number,
                                horse_name, horse_id, sex_age, weight_carried,
                                jockey_name, jockey_id, finish_time, margin,
                                passing_order, last_3f, odds, popularity,
                                horse_weight, horse_weight_diff,
                                trainer_name, trainer_id, owner, prize_money,
                                raw_data, created_at
                            ) VALUES (
                                %s, %s, %s, %s, %s, %s, %s, %s,
                                %s, %s, %s, %s, %s, %s, %s, %s,
                                %s, %s, %s, %s, %s, %s, %s, %s
                            )
                            """,
                            (
                                race_id,
                                _or_none(row.get("馬番")),
                                _or_none(row.get("着順")),
                                _or_none(row.get("枠番")),
                                _or_none(row.get("馬名")),
                                _or_none(row.get("馬ID")),
                                _or_none(row.get("性齢")),
                                _or_none(row.get("斤量")),
                                _or_none(row.get("騎手")),
                                _or_none(row.get("騎手ID")),
                                _or_none(row.get("タイム")),
                                _or_none(row.get("着差")),
                                _or_none(row.get("通過")),
                                _or_none(row.get("上り")),
                                _or_none(row.get("単勝オッズ")),
                                _or_none(row.get("人気")),
                                _parse_horse_weight(hw),
                                _parse_horse_weight_diff(hw),
                                _or_none(row.get("調教師")),
                                _or_none(row.get("調教師ID")),
                                _or_none(row.get("馬主")),
                                _or_none(row.get("賞金")),
                                json.dumps(dict(row), ensure_ascii=False),
                                now,
                            ),
                        )

                if payoffs:
                    cur.execute(
                        "DELETE FROM payoffs WHERE race_id = %s",
                        (race_id,),
                    )
                    for pay in payoffs:
                        cur.execute(
                            """
                            INSERT INTO payoffs (
                                race_id, bet_type, combination,
                                payout, popularity, created_at
                            ) VALUES (%s, %s, %s, %s, %s, %s)
                            """,
                            (
                                race_id,
                                _or_none(pay.get("券種")),
                                _or_none(pay.get("組番")),
                                _or_none(pay.get("払戻金")),
                                _or_none(pay.get("人気")),
                                now,
                            ),
                        )

        logger.info(
            "レース %s を保存 (結果: %d件, 払戻: %d件)",
            race_id,
            len(results) if results else 0,
            len(payoffs) if payoffs else 0,
        )

    def save_horse(self, horse_id: str, profile: HorseProfile) -> None:
        """馬情報を保存（upsert）."""
        now = datetime.now()
        with psycopg.connect(self._database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO horses (
                        horse_id, horse_name, sex, coat_color, birthday,
                        trainer_name, trainer_id, owner, owner_id,
                        breeder, birthplace, sire, dam, broodmare_sire,
                        raw_data, created_at, updated_at
                    ) VALUES (
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s,
                        %s, %s, %s, %s, %s,
                        %s, %s, %s
                    )
                    ON CONFLICT (horse_id) DO UPDATE SET
                        horse_name = EXCLUDED.horse_name,
                        sex = EXCLUDED.sex,
                        coat_color = EXCLUDED.coat_color,
                        birthday = EXCLUDED.birthday,
                        trainer_name = EXCLUDED.trainer_name,
                        trainer_id = EXCLUDED.trainer_id,
                        owner = EXCLUDED.owner,
                        owner_id = EXCLUDED.owner_id,
                        breeder = EXCLUDED.breeder,
                        birthplace = EXCLUDED.birthplace,
                        sire = EXCLUDED.sire,
                        dam = EXCLUDED.dam,
                        broodmare_sire = EXCLUDED.broodmare_sire,
                        raw_data = EXCLUDED.raw_data,
                        updated_at = EXCLUDED.updated_at
                    """,
                    (
                        horse_id,
                        _or_none(profile.get("馬名")),
                        _or_none(profile.get("性別")),
                        _or_none(profile.get("毛色")),
                        _or_none(profile.get("生年月日")),
                        _or_none(profile.get("調教師")),
                        _or_none(profile.get("調教師ID")),
                        _or_none(profile.get("馬主")),
                        _or_none(profile.get("馬主ID")),
                        _or_none(profile.get("生産者")),
                        _or_none(profile.get("産地")),
                        _or_none(profile.get("父")),
                        _or_none(profile.get("母")),
                        _or_none(profile.get("母父")),
                        json.dumps(dict(profile), ensure_ascii=False),
                        now,
                        now,
                    ),
                )

        logger.info("馬 %s (%s) を保存", horse_id, profile.get("馬名"))

    def save_jockey(self, jockey_id: str, profile: JockeyProfile) -> None:
        """騎手情報を保存（upsert）."""
        now = datetime.now()
        with psycopg.connect(self._database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO jockeys (
                        jockey_id, jockey_name, affiliation,
                        birthday, first_license_year,
                        raw_data, created_at, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (jockey_id) DO UPDATE SET
                        jockey_name = EXCLUDED.jockey_name,
                        affiliation = EXCLUDED.affiliation,
                        birthday = EXCLUDED.birthday,
                        first_license_year = EXCLUDED.first_license_year,
                        raw_data = EXCLUDED.raw_data,
                        updated_at = EXCLUDED.updated_at
                    """,
                    (
                        jockey_id,
                        _or_none(profile.get("騎手名")),
                        _or_none(profile.get("所属")),
                        _or_none(profile.get("生年月日")),
                        _or_none(profile.get("初免許年")),
                        json.dumps(dict(profile), ensure_ascii=False),
                        now,
                        now,
                    ),
                )

        logger.info("騎手 %s (%s) を保存", jockey_id, profile.get("騎手名"))

    def save_trainer(self, trainer_id: str, profile: TrainerProfile) -> None:
        """調教師情報を保存（upsert）."""
        now = datetime.now()
        with psycopg.connect(self._database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO trainers (
                        trainer_id, trainer_name, affiliation,
                        birthday, first_license_year,
                        raw_data, created_at, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (trainer_id) DO UPDATE SET
                        trainer_name = EXCLUDED.trainer_name,
                        affiliation = EXCLUDED.affiliation,
                        birthday = EXCLUDED.birthday,
                        first_license_year = EXCLUDED.first_license_year,
                        raw_data = EXCLUDED.raw_data,
                        updated_at = EXCLUDED.updated_at
                    """,
                    (
                        trainer_id,
                        _or_none(profile.get("調教師名")),
                        _or_none(profile.get("所属")),
                        _or_none(profile.get("生年月日")),
                        _or_none(profile.get("初免許年")),
                        json.dumps(dict(profile), ensure_ascii=False),
                        now,
                        now,
                    ),
                )

        logger.info("調教師 %s (%s) を保存", trainer_id, profile.get("調教師名"))

    def get_existing_jockey_ids(self, jockey_ids: list[str]) -> set[str]:
        """指定された騎手IDのうち、すでに DB に登録済みのものを返す."""
        if not jockey_ids:
            return set()
        with psycopg.connect(self._database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT jockey_id FROM jockeys WHERE jockey_id = ANY(%s)",
                    (jockey_ids,),
                )
                return {row[0] for row in cur.fetchall()}

    def get_existing_trainer_ids(self, trainer_ids: list[str]) -> set[str]:
        """指定された調教師IDのうち、すでに DB に登録済みのものを返す."""
        if not trainer_ids:
            return set()
        with psycopg.connect(self._database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT trainer_id FROM trainers WHERE trainer_id = ANY(%s)",
                    (trainer_ids,),
                )
                return {row[0] for row in cur.fetchall()}

    def get_existing_horse_ids(self, horse_ids: list[str]) -> set[str]:
        """指定された馬IDのうち、すでに DB に登録済みのものを返す."""
        if not horse_ids:
            return set()
        with psycopg.connect(self._database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT horse_id FROM horses WHERE horse_id = ANY(%s)",
                    (horse_ids,),
                )
                return {row[0] for row in cur.fetchall()}

    def get_existing_race_ids(self, race_ids: list[str]) -> set[str]:
        """指定されたレースIDのうち、すでに DB に登録済みのものを返す."""
        if not race_ids:
            return set()
        with psycopg.connect(self._database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT race_id FROM races WHERE race_id = ANY(%s)",
                    (race_ids,),
                )
                return {row[0] for row in cur.fetchall()}

    def get_latest_race_date(self) -> tuple[int, int] | None:
        """DB に登録されている最新レースの (year, month) を返す。レースが1件もない場合は None を返す."""
        with psycopg.connect(self._database_url) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT MAX(date) FROM races WHERE date IS NOT NULL")
                row = cur.fetchone()
                if row is None or row[0] is None:
                    return None
                # date は "YYYY/MM/DD" 形式で格納されている
                parts = str(row[0]).split("/")
                return int(parts[0]), int(parts[1])

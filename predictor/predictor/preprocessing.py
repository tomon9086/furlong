"""データ前処理モジュール"""

from __future__ import annotations

import re

import numpy as np
import pandas as pd
import psycopg

# テストデータに使う直近の割合
TEST_RATIO = 0.2
# 較正（バリデーション）データに使う割合
VAL_RATIO = 0.1

# 血統適性統計（父馬×コース種別）の縮小推定パラメータ。
# 学習時（compute_recent_stats）と予測時（load_predict_data の SQL）で共通の値を使う。
_PEDIGREE_K_SHRINK = 20.0  # 複勝率の縮小推定の仮想サンプル数
_PEDIGREE_K_SPEED_SHRINK = 10.0  # スピード指数の縮小推定の仮想サンプル数（母平均0）

_SELECT_COLS = """
    r.race_id,
    r.race_name,
    r.race_number,
    r.date,
    r.venue,
    r.course_type,
    r.distance,
    r.direction,
    r.weather,
    r.track_condition,
    r.grade,
    r.head_count,
    r.race_condition,
    rr.horse_number,
    rr.finishing_position,
    rr.bracket_number,
    rr.horse_id,
    rr.horse_name,
    rr.sex_age,
    rr.weight_carried,
    rr.jockey_id,
    rr.jockey_name,
    rr.finish_time,
    rr.passing_order,
    rr.last_3f,
    rr.odds,
    rr.popularity,
    rr.horse_weight,
    rr.horse_weight_diff,
    rr.trainer_id,
    rr.owner,
    h.sire,
    h.dam,
    h.broodmare_sire"""

_FROM_CLAUSE = """
FROM races r
JOIN race_results rr ON r.race_id = rr.race_id
LEFT JOIN horses h ON rr.horse_id = h.horse_id"""

_QUERY = f"""
SELECT{_SELECT_COLS}{_FROM_CLAUSE}
WHERE rr.finishing_position ~ '^[0-9]+$'
ORDER BY TO_DATE(r.date, 'YYYY/MM/DD'), r.race_id, rr.horse_number::integer
"""

_PREDICT_RACE_QUERY = f"""
SELECT{_SELECT_COLS}{_FROM_CLAUSE}
WHERE r.race_id = %s
  AND rr.finishing_position IS NULL
ORDER BY rr.horse_number::integer
"""

_RECENT_STATS_QUERY = """
WITH race_last3f AS (
  SELECT
    race_id,
    horse_id,
    RANK() OVER (
      PARTITION BY race_id
      ORDER BY CASE WHEN last_3f ~ '^\\d+\\.?\\d*$' THEN last_3f::float ELSE NULL END NULLS LAST
    ) AS last_3f_rank
  FROM race_results
  WHERE finishing_position ~ '^[0-9]+$'
),
race_time_z AS (
  SELECT
    race_id,
    horse_id,
    CASE WHEN STDDEV(ft) OVER (PARTITION BY race_id) > 0
      THEN (AVG(ft) OVER (PARTITION BY race_id) - ft)
        / STDDEV(ft) OVER (PARTITION BY race_id)
      ELSE NULL
    END AS race_time_zscore
  FROM (
    SELECT
      race_id,
      horse_id,
      CASE
        WHEN finish_time ~ '^[0-9]+:[0-9]+\\.[0-9]+$'
          THEN SPLIT_PART(finish_time, ':', 1)::float * 60
            + SPLIT_PART(finish_time, ':', 2)::float
        WHEN finish_time ~ '^[0-9]+\\.?[0-9]*$'
          THEN finish_time::float
        ELSE NULL
      END AS ft
    FROM race_results
    WHERE finishing_position ~ '^[0-9]+$'
  ) t
),
history AS (
  SELECT
    rr.horse_id,    rr.jockey_id,    TO_DATE(r.date, 'YYYY/MM/DD') AS race_date,
    r.race_id,
    r.course_type,
    r.distance,
    r.race_condition,
    rr.finishing_position::integer AS finishing_pos,
    CASE WHEN rr.last_3f ~ '^\\d+\\.?\\d*$' THEN rr.last_3f::float ELSE NULL END AS last_3f_num,
    CASE WHEN rr.passing_order ~ '^\\d' THEN SPLIT_PART(rr.passing_order, '-', 1)::integer ELSE NULL END AS first_corner_pos,
    rl.last_3f_rank,
    rtz.race_time_zscore
  FROM race_results rr
  JOIN races r ON rr.race_id = r.race_id
  LEFT JOIN race_last3f rl ON rr.race_id = rl.race_id AND rr.horse_id = rl.horse_id
  LEFT JOIN race_time_z rtz ON rr.race_id = rtz.race_id AND rr.horse_id = rtz.horse_id
  WHERE rr.finishing_position ~ '^[0-9]+$'
    AND rr.horse_id = ANY(%s)
),
windowed AS (
  SELECT
    horse_id,
    jockey_id,
    course_type,
    distance,
    race_condition,
    race_date,
    AVG(finishing_pos) OVER w3  AS avg_finish_last3,
    MIN(finishing_pos) OVER w3  AS best_finish_last3,
    AVG(last_3f_num)   OVER w3  AS avg_last3f_last3,
    AVG(finishing_pos) OVER w5  AS avg_finish_last5,
    MIN(finishing_pos) OVER w5  AS best_finish_last5,
    AVG(last_3f_num)   OVER w5  AS avg_last3f_last5,
    AVG(finishing_pos) OVER w3c AS avg_finish_last3_cond,
    MIN(finishing_pos) OVER w3c AS best_finish_last3_cond,
    AVG(last_3f_num)   OVER w3c AS avg_last3f_last3_cond,
    AVG(finishing_pos) OVER w5c AS avg_finish_last5_cond,
    MIN(finishing_pos) OVER w5c AS best_finish_last5_cond,
    AVG(last_3f_num)   OVER w5c AS avg_last3f_last5_cond,
    AVG(first_corner_pos) OVER w3  AS avg_corner_last3,
    AVG(first_corner_pos) OVER w5  AS avg_corner_last5,
    AVG(first_corner_pos) OVER w3c AS avg_corner_last3_cond,
    AVG(first_corner_pos) OVER w5c AS avg_corner_last5_cond,
    AVG(last_3f_rank)     OVER w3  AS avg_last3f_rank_last3,
    AVG(last_3f_rank)     OVER w5  AS avg_last3f_rank_last5,
    AVG(last_3f_rank)     OVER w3c AS avg_last3f_rank_last3_cond,
    AVG(last_3f_rank)     OVER w5c AS avg_last3f_rank_last5_cond,
    AVG(race_time_zscore) OVER w3  AS avg_speed_index_last3,
    AVG(race_time_zscore) OVER w5  AS avg_speed_index_last5,
    ROW_NUMBER() OVER (PARTITION BY horse_id
      ORDER BY race_date DESC, race_id DESC) AS rn_all,
    ROW_NUMBER() OVER (PARTITION BY horse_id, course_type, distance
      ORDER BY race_date DESC, race_id DESC) AS rn_cond
  FROM history
  WINDOW
    w3  AS (PARTITION BY horse_id
            ORDER BY race_date, race_id ROWS BETWEEN 2 PRECEDING AND CURRENT ROW),
    w5  AS (PARTITION BY horse_id
            ORDER BY race_date, race_id ROWS BETWEEN 4 PRECEDING AND CURRENT ROW),
    w3c AS (PARTITION BY horse_id, course_type, distance
            ORDER BY race_date, race_id ROWS BETWEEN 2 PRECEDING AND CURRENT ROW),
    w5c AS (PARTITION BY horse_id, course_type, distance
            ORDER BY race_date, race_id ROWS BETWEEN 4 PRECEDING AND CURRENT ROW)
),
latest_all AS (
  SELECT
    horse_id,
    avg_finish_last3, best_finish_last3, avg_last3f_last3,
    avg_finish_last5, best_finish_last5, avg_last3f_last5,
    avg_corner_last3, avg_corner_last5,
    avg_last3f_rank_last3, avg_last3f_rank_last5,
    avg_speed_index_last3, avg_speed_index_last5,
    distance AS prev_distance,
    course_type AS prev_course_type,
    jockey_id AS prev_jockey_id,
    race_condition AS prev_race_condition,
    race_date AS prev_race_date
  FROM windowed
  WHERE rn_all = 1
),
latest_cond AS (
  SELECT
    horse_id,
    avg_finish_last3_cond, best_finish_last3_cond, avg_last3f_last3_cond,
    avg_finish_last5_cond, best_finish_last5_cond, avg_last3f_last5_cond,
    avg_corner_last3_cond, avg_corner_last5_cond,
    avg_last3f_rank_last3_cond, avg_last3f_rank_last5_cond
  FROM windowed
  WHERE rn_cond = 1
    AND course_type = %s
    AND distance = %s
)
SELECT
  la.horse_id,
  la.avg_finish_last3, la.best_finish_last3, la.avg_last3f_last3,
  la.avg_finish_last5, la.best_finish_last5, la.avg_last3f_last5,
  la.avg_corner_last3, la.avg_corner_last5,
  la.avg_last3f_rank_last3, la.avg_last3f_rank_last5,
  la.avg_speed_index_last3, la.avg_speed_index_last5,
  la.prev_distance,
  la.prev_course_type,
  la.prev_jockey_id,
  la.prev_race_condition,
  la.prev_race_date,
  lc.avg_finish_last3_cond, lc.best_finish_last3_cond, lc.avg_last3f_last3_cond,
  lc.avg_finish_last5_cond, lc.best_finish_last5_cond, lc.avg_last3f_last5_cond,
  lc.avg_corner_last3_cond, lc.avg_corner_last5_cond,
  lc.avg_last3f_rank_last3_cond, lc.avg_last3f_rank_last5_cond
FROM latest_all la
LEFT JOIN latest_cond lc ON la.horse_id = lc.horse_id
"""

_JOCKEY_WIN_RATE_QUERY = """
SELECT
  rr.jockey_id,
  SUM(CASE WHEN rr.finishing_position::integer = 1 THEN 1 ELSE 0 END)::float
    / NULLIF(COUNT(*), 0) AS jockey_win_rate_venue_cond
FROM race_results rr
JOIN races r ON rr.race_id = r.race_id
WHERE rr.finishing_position ~ '^[0-9]+$'
  AND rr.jockey_id = ANY(%s)
  AND r.venue = %s
  AND r.course_type = %s
GROUP BY rr.jockey_id
"""

_PRE_RACE_ODDS_QUERY = """
SELECT horse_number, win_odds
FROM pre_race_odds
WHERE race_id = %s
"""

_TRAINER_WIN_RATE_QUERY = """
SELECT
  trainer_id,
  SUM(CASE WHEN finishing_position::integer = 1 THEN 1 ELSE 0 END)::float
    / NULLIF(COUNT(*), 0) AS trainer_win_rate_last30
FROM (
  SELECT
    rr2.trainer_id,
    rr2.finishing_position,
    ROW_NUMBER() OVER (
      PARTITION BY rr2.trainer_id
      ORDER BY TO_DATE(r2.date, 'YYYY/MM/DD') DESC, rr2.race_id DESC
    ) AS rn
  FROM race_results rr2
  JOIN races r2 ON rr2.race_id = r2.race_id
  WHERE rr2.finishing_position ~ '^[0-9]+$'
    AND rr2.trainer_id = ANY(%s)
) sub
WHERE rn <= 30
GROUP BY trainer_id
"""

_TRAINER_PRIOR_WIN_RATE_QUERY = """
SELECT
  trainer_id,
  SUM(CASE WHEN finishing_position::integer = 1 THEN 1 ELSE 0 END)::float
    / NULLIF(COUNT(*), 0) AS trainer_prior_win_rate,
  COUNT(*)::float AS trainer_prior_mounts
FROM race_results rr
JOIN races r ON rr.race_id = r.race_id
WHERE rr.finishing_position ~ '^[0-9]+$'
  AND rr.trainer_id = ANY(%s)
  AND TO_DATE(r.date, 'YYYY/MM/DD') < TO_DATE(%s, 'YYYY/MM/DD')
GROUP BY trainer_id
"""

_JOCKEY_PRIOR_WIN_RATE_QUERY = """
SELECT
  jockey_id,
  SUM(CASE WHEN finishing_position::integer = 1 THEN 1 ELSE 0 END)::float
    / NULLIF(COUNT(*), 0) AS jockey_prior_win_rate,
  COUNT(*)::float AS jockey_prior_mounts
FROM race_results rr
JOIN races r ON rr.race_id = r.race_id
WHERE rr.finishing_position ~ '^[0-9]+$'
  AND rr.jockey_id = ANY(%s)
  AND TO_DATE(r.date, 'YYYY/MM/DD') < TO_DATE(%s, 'YYYY/MM/DD')
GROUP BY jockey_id
"""

_OWNER_PRIOR_WIN_RATE_QUERY = """
SELECT
  owner,
  SUM(CASE WHEN finishing_position::integer = 1 THEN 1 ELSE 0 END)::float
    / NULLIF(COUNT(*), 0) AS owner_prior_win_rate,
  COUNT(*)::float AS owner_prior_mounts
FROM race_results rr
JOIN races r ON rr.race_id = r.race_id
WHERE rr.finishing_position ~ '^[0-9]+$'
  AND rr.owner = ANY(%s)
  AND TO_DATE(r.date, 'YYYY/MM/DD') < TO_DATE(%s, 'YYYY/MM/DD')
GROUP BY owner
"""

_PAYOFFS_QUERY = """
SELECT race_id, bet_type, combination, payout
FROM payoffs
WHERE race_id = ANY(%s)
"""

_GLOBAL_PLACE_RATE_QUERY = """
SELECT AVG(CASE WHEN rr.finishing_position::integer <= 3 THEN 1.0 ELSE 0.0 END) AS global_place_rate
FROM race_results rr
JOIN races r ON rr.race_id = r.race_id
WHERE rr.finishing_position ~ '^[0-9]+$'
  AND TO_DATE(r.date, 'YYYY/MM/DD') < TO_DATE(%s, 'YYYY/MM/DD')
"""

_SIRE_PLACE_RATE_QUERY = """
SELECT
  h.sire,
  (SUM(CASE WHEN rr.finishing_position::integer <= 3 THEN 1 ELSE 0 END)::float
    + %s * %s) / (COUNT(*) + %s) AS sire_place_rate_cond,
  COUNT(*)::float AS sire_progeny_mounts_cond
FROM race_results rr
JOIN races r ON rr.race_id = r.race_id
JOIN horses h ON rr.horse_id = h.horse_id
WHERE rr.finishing_position ~ '^[0-9]+$'
  AND h.sire = ANY(%s)
  AND r.course_type = %s
  AND TO_DATE(r.date, 'YYYY/MM/DD') < TO_DATE(%s, 'YYYY/MM/DD')
GROUP BY h.sire
"""

_SIRE_SPEED_INDEX_QUERY = """
WITH race_time_z AS (
  SELECT
    race_id,
    horse_id,
    CASE WHEN STDDEV(ft) OVER (PARTITION BY race_id) > 0
      THEN (AVG(ft) OVER (PARTITION BY race_id) - ft)
        / STDDEV(ft) OVER (PARTITION BY race_id)
      ELSE NULL
    END AS race_time_zscore
  FROM (
    SELECT
      race_id,
      horse_id,
      CASE
        WHEN finish_time ~ '^[0-9]+:[0-9]+\\.[0-9]+$'
          THEN SPLIT_PART(finish_time, ':', 1)::float * 60
            + SPLIT_PART(finish_time, ':', 2)::float
        WHEN finish_time ~ '^[0-9]+\\.?[0-9]*$'
          THEN finish_time::float
        ELSE NULL
      END AS ft
    FROM race_results
    WHERE finishing_position ~ '^[0-9]+$'
  ) t
)
SELECT
  h.sire,
  SUM(rtz.race_time_zscore) / (COUNT(rtz.race_time_zscore) + %s) AS sire_avg_speed_index_cond
FROM race_results rr
JOIN races r ON rr.race_id = r.race_id
JOIN horses h ON rr.horse_id = h.horse_id
JOIN race_time_z rtz ON rr.race_id = rtz.race_id AND rr.horse_id = rtz.horse_id
WHERE rr.finishing_position ~ '^[0-9]+$'
  AND h.sire = ANY(%s)
  AND r.course_type = %s
  AND TO_DATE(r.date, 'YYYY/MM/DD') < TO_DATE(%s, 'YYYY/MM/DD')
GROUP BY h.sire
"""

_BRACKET_DISTANCE_AVG_QUERY = """
SELECT
  rr.bracket_number AS bracket_number,
  AVG(rr.finishing_position::float) AS bracket_distance_avg_finish
FROM race_results rr
JOIN races r ON rr.race_id = r.race_id
WHERE rr.finishing_position ~ '^[0-9]+$'
  AND rr.bracket_number ~ '^[0-9]+$'
  AND CASE
    WHEN r.distance::integer <= 1400 THEN 0
    WHEN r.distance::integer <= 1800 THEN 1
    WHEN r.distance::integer <= 2200 THEN 2
    ELSE 3
  END = %s
GROUP BY rr.bracket_number
"""


def _get_distance_band(distance: int) -> int:
    """距離をバンド番号に変換する（0=~1400, 1=1401~1800, 2=1801~2200, 3=2201~）。"""
    if distance <= 1400:
        return 0
    elif distance <= 1800:
        return 1
    elif distance <= 2200:
        return 2
    else:
        return 3


def load_payoffs(database_url: str, race_ids: list[str]) -> pd.DataFrame:
    """指定レースの払戻データを DB から読み込む。"""
    if not race_ids:
        return pd.DataFrame(columns=["race_id", "bet_type", "combination", "payout"])
    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(_PAYOFFS_QUERY, (race_ids,))
            rows = cur.fetchall()
            cols = [desc[0] for desc in cur.description]
    return pd.DataFrame(rows, columns=cols)


def load_data(database_url: str) -> pd.DataFrame:
    """PostgreSQL からレース・出走馬データを読み込む（学習用）。"""
    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(_QUERY)
            rows = cur.fetchall()
            cols = [desc[0] for desc in cur.description]
    return pd.DataFrame(rows, columns=cols)


def load_predict_data(database_url: str, race_id: str) -> pd.DataFrame:
    """予測対象レースの出走馬と、SQL ウィンドウ関数で計算した近走成績を読み込む。

    対象レースは finishing_position IS NULL の行を取得し、
    近走成績フィーチャーは SQL ウィンドウ関数で集計して直接返す。
    全件の過去成績を Python に転送しないため、学習時より高速に動作する。
    """
    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(_PREDICT_RACE_QUERY, (race_id,))
            target_rows = cur.fetchall()
            if not target_rows:
                return pd.DataFrame()
            cols = [desc[0] for desc in cur.description]
            target_df = pd.DataFrame(target_rows, columns=cols)

            horse_ids = target_df["horse_id"].dropna().tolist()
            jockey_ids = target_df["jockey_id"].dropna().tolist()
            trainer_ids = target_df["trainer_id"].dropna().tolist()
            owners = target_df["owner"].dropna().tolist()
            sires = target_df["sire"].dropna().tolist()
            venue = target_df["venue"].iloc[0]
            course_type = target_df["course_type"].iloc[0]
            distance = int(target_df["distance"].iloc[0])
            race_date = target_df["date"].iloc[0]

            cur.execute(_RECENT_STATS_QUERY, (horse_ids, course_type, distance))
            stats_rows = cur.fetchall()
            stats_cols = [desc[0] for desc in cur.description]
            stats_df = pd.DataFrame(stats_rows, columns=stats_cols)

            cur.execute(_JOCKEY_WIN_RATE_QUERY, (jockey_ids, venue, course_type))
            jockey_rows = cur.fetchall()
            jockey_cols = [desc[0] for desc in cur.description]
            jockey_df = pd.DataFrame(jockey_rows, columns=jockey_cols)

            cur.execute(_TRAINER_WIN_RATE_QUERY, (trainer_ids,))
            trainer_rows = cur.fetchall()
            trainer_cols = [desc[0] for desc in cur.description]
            trainer_df = pd.DataFrame(trainer_rows, columns=trainer_cols)

            cur.execute(_TRAINER_PRIOR_WIN_RATE_QUERY, (trainer_ids, race_date))
            trainer_prior_rows = cur.fetchall()
            trainer_prior_cols = [desc[0] for desc in cur.description]
            trainer_prior_df = pd.DataFrame(
                trainer_prior_rows, columns=trainer_prior_cols
            )

            cur.execute(_JOCKEY_PRIOR_WIN_RATE_QUERY, (jockey_ids, race_date))
            jockey_prior_rows = cur.fetchall()
            jockey_prior_cols = [desc[0] for desc in cur.description]
            jockey_prior_df = pd.DataFrame(jockey_prior_rows, columns=jockey_prior_cols)

            cur.execute(_OWNER_PRIOR_WIN_RATE_QUERY, (owners, race_date))
            owner_prior_rows = cur.fetchall()
            owner_prior_cols = [desc[0] for desc in cur.description]
            owner_prior_df = pd.DataFrame(owner_prior_rows, columns=owner_prior_cols)

            cur.execute(_GLOBAL_PLACE_RATE_QUERY, (race_date,))
            global_place_rate = cur.fetchone()[0]
            global_place_rate = (
                float(global_place_rate) if global_place_rate is not None else 0.0
            )

            cur.execute(
                _SIRE_PLACE_RATE_QUERY,
                (
                    _PEDIGREE_K_SHRINK,
                    global_place_rate,
                    _PEDIGREE_K_SHRINK,
                    sires,
                    course_type,
                    race_date,
                ),
            )
            sire_place_rows = cur.fetchall()
            sire_place_cols = [desc[0] for desc in cur.description]
            sire_place_df = pd.DataFrame(sire_place_rows, columns=sire_place_cols)

            cur.execute(
                _SIRE_SPEED_INDEX_QUERY,
                (_PEDIGREE_K_SPEED_SHRINK, sires, course_type, race_date),
            )
            sire_speed_rows = cur.fetchall()
            sire_speed_cols = [desc[0] for desc in cur.description]
            sire_speed_df = pd.DataFrame(sire_speed_rows, columns=sire_speed_cols)

            cur.execute(_PRE_RACE_ODDS_QUERY, (race_id,))
            pre_odds_rows = cur.fetchall()
            pre_odds_cols = [desc[0] for desc in cur.description]
            pre_odds_df = pd.DataFrame(pre_odds_rows, columns=pre_odds_cols)

            distance_band = _get_distance_band(distance)
            cur.execute(_BRACKET_DISTANCE_AVG_QUERY, (distance_band,))
            bracket_rows = cur.fetchall()
            bracket_cols = [desc[0] for desc in cur.description]
            bracket_df = pd.DataFrame(bracket_rows, columns=bracket_cols)

    result = (
        target_df.merge(stats_df, on="horse_id", how="left")
        .merge(jockey_df, on="jockey_id", how="left")
        .merge(trainer_df, on="trainer_id", how="left")
        .merge(trainer_prior_df, on="trainer_id", how="left")
        .merge(jockey_prior_df, on="jockey_id", how="left")
        .merge(owner_prior_df, on="owner", how="left")
        .merge(sire_place_df, on="sire", how="left")
        .merge(sire_speed_df, on="sire", how="left")
        .merge(pre_odds_df, on="horse_number", how="left")
        .merge(bracket_df, on="bracket_number", how="left")
    )
    # 産駒実績が0件（=SQLのGROUP BYで該当なし）の場合、学習時の縮小推定が返す値
    # （mounts=0 → 母平均そのもの）と一致させるため明示的に埋める。
    result["sire_place_rate_cond"] = result["sire_place_rate_cond"].fillna(
        global_place_rate
    )
    result["sire_progeny_mounts_cond"] = result["sire_progeny_mounts_cond"].fillna(0.0)
    result["sire_avg_speed_index_cond"] = result["sire_avg_speed_index_cond"].fillna(
        0.0
    )
    return result


def _parse_finish_time(value: object) -> float | None:
    """'1:23.4' 形式のタイムを秒数に変換する。"""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    s = str(value).strip()
    m = re.match(r"^(\d+):(\d+\.\d+)$", s)
    if m:
        return int(m.group(1)) * 60 + float(m.group(2))
    try:
        return float(s)
    except ValueError:
        return None


def _parse_first_corner(value: object) -> int | None:
    """通過順の最初のコーナー順位を返す（例: '03-03-02-02' → 3）。"""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    parts = str(value).split("-")
    try:
        return int(parts[0])
    except (ValueError, IndexError):
        return None


_CLASS_LEVEL_PATTERNS: list[tuple[int, re.Pattern]] = [
    (0, re.compile(r"新馬")),
    (1, re.compile(r"未勝利")),
    (2, re.compile(r"500万下|1勝クラス")),
    (3, re.compile(r"1000万下|2勝クラス")),
    (4, re.compile(r"1600万下|3勝クラス")),
    (5, re.compile(r"オープン")),
]


def _extract_class_level(value: object) -> float | None:
    """race_condition の自由文からクラス（格）レベルを抽出する（0=新馬 〜 5=オープン）。

    新条件名（1勝クラス等）と旧条件名（500万下等）の両方に対応する
    （JRAが2019年に呼称変更したため、収録期間内に両方の表記が混在する）。
    """
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    s = str(value)
    for level, pattern in _CLASS_LEVEL_PATTERNS:
        if pattern.search(s):
            return float(level)
    return None


def preprocess(df: pd.DataFrame, keep_null_position: bool = False) -> pd.DataFrame:
    """生データを機械学習に適した形に変換する。

    keep_null_position=True の場合、finishing_position が NULL の行（未来レース）を
    保持する。predict 時に使用する。
    """
    df = df.copy()

    # 日付
    df["date"] = pd.to_datetime(df["date"], format="%Y/%m/%d", errors="coerce")

    # ターゲット変数
    df["finishing_position"] = pd.to_numeric(df["finishing_position"], errors="coerce")
    if not keep_null_position:
        df = df.dropna(subset=["finishing_position"])
        df["finishing_position"] = df["finishing_position"].astype(int)
    df["is_win"] = (df["finishing_position"] == 1).astype(int)
    df["is_placed"] = (df["finishing_position"] <= 3).astype(int)

    # クラス（格）レベル抽出（新馬〜オープンの序列。前走比較で class_change に使う）
    if "race_condition" in df.columns:
        df["class_level"] = df["race_condition"].apply(_extract_class_level)
        df["class_level"] = df["class_level"].astype(float)

    # 数値変換
    for col in (
        "odds",
        "popularity",
        "weight_carried",
        "last_3f",
        "horse_number",
        "bracket_number",
        "horse_weight",
        "horse_weight_diff",
    ):
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # タイム（秒換算）
    df["finish_time_sec"] = pd.to_numeric(
        df["finish_time"].apply(_parse_finish_time), errors="coerce"
    )

    # 通過順（最初のコーナー位置）
    df["first_corner_pos"] = pd.to_numeric(
        df["passing_order"].apply(_parse_first_corner), errors="coerce"
    )

    # 馬体重のレース内相対値（z-score: レース内で正規化）
    _hw_mean = df.groupby("race_id")["horse_weight"].transform("mean")
    _hw_std = df.groupby("race_id")["horse_weight"].transform("std")
    df["horse_weight_relative"] = (df["horse_weight"] - _hw_mean) / _hw_std.where(
        _hw_std > 0
    )

    # 斤量のレース内相対値（z-score: レース内で正規化）
    _wc_mean = df.groupby("race_id")["weight_carried"].transform("mean")
    _wc_std = df.groupby("race_id")["weight_carried"].transform("std")
    df["weight_carried_relative"] = (df["weight_carried"] - _wc_mean) / _wc_std.where(
        _wc_std > 0
    )

    # last_3f のレース内相対順位（順位1 = 最速）
    df["last_3f_rank"] = df.groupby("race_id")["last_3f"].rank(
        method="min", ascending=True, na_option="keep"
    )

    # タイムのレース内相対値（z-score。正値=レース平均より速い）
    _ft_mean = df.groupby("race_id")["finish_time_sec"].transform("mean")
    _ft_std = df.groupby("race_id")["finish_time_sec"].transform("std")
    df["race_time_zscore"] = (_ft_mean - df["finish_time_sec"]) / _ft_std.where(
        _ft_std > 0
    )

    # 近走成績フィーチャー（predict 時に NULL→object になるため数値化）
    for col in (
        "avg_finish_last3",
        "best_finish_last3",
        "avg_last3f_last3",
        "avg_finish_last5",
        "best_finish_last5",
        "avg_last3f_last5",
        "avg_corner_last3",
        "avg_corner_last5",
        "avg_finish_last3_cond",
        "best_finish_last3_cond",
        "avg_last3f_last3_cond",
        "avg_finish_last5_cond",
        "best_finish_last5_cond",
        "avg_last3f_last5_cond",
        "avg_corner_last3_cond",
        "avg_corner_last5_cond",
        "avg_last3f_rank_last3",
        "avg_last3f_rank_last5",
        "avg_last3f_rank_last3_cond",
        "avg_last3f_rank_last5_cond",
        "avg_speed_index_last3",
        "avg_speed_index_last5",
        "jockey_win_rate_venue_cond",
        "trainer_win_rate_last30",
        "trainer_prior_win_rate",
        "trainer_prior_mounts",
        "jockey_prior_win_rate",
        "jockey_prior_mounts",
        "owner_prior_win_rate",
        "owner_prior_mounts",
        "bracket_distance_avg_finish",
        "sire_place_rate_cond",
        "sire_progeny_mounts_cond",
        "sire_avg_speed_index_cond",
    ):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # 距離変化（前走との距離差）: predict 時は prev_distance が SQL から来る
    if "prev_distance" in df.columns:
        df["distance_change"] = pd.to_numeric(
            df["distance"], errors="coerce"
        ) - pd.to_numeric(df["prev_distance"], errors="coerce")
        df = df.drop(columns=["prev_distance"])

    # コース替わりフラグ（前走との course_type 変更）: predict 時は prev_course_type が SQL から来る
    if "prev_course_type" in df.columns:
        has_prev = df["prev_course_type"].notna()
        df["course_type_change"] = float("nan")
        df.loc[has_prev, "course_type_change"] = (
            df.loc[has_prev, "course_type"].astype(str)
            != df.loc[has_prev, "prev_course_type"].astype(str)
        ).astype(float)
        df = df.drop(columns=["prev_course_type"])

    # 騎手乗り替わりフラグ（前走と騎手が異なるか）: predict 時は prev_jockey_id が SQL から来る
    if "prev_jockey_id" in df.columns:
        has_prev = df["prev_jockey_id"].notna()
        df["jockey_change"] = float("nan")
        df.loc[has_prev, "jockey_change"] = (
            df.loc[has_prev, "jockey_id"].astype(str)
            != df.loc[has_prev, "prev_jockey_id"].astype(str)
        ).astype(float)
        df = df.drop(columns=["prev_jockey_id"])

    # クラス変化（前走との差）: predict 時は prev_race_condition が SQL から来る
    if "prev_race_condition" in df.columns:
        prev_class_level = df["prev_race_condition"].apply(_extract_class_level)
        df["class_change"] = df["class_level"] - prev_class_level
        df = df.drop(columns=["prev_race_condition"])

    # 出走間隔（前走からの経過日数）: predict 時は prev_race_date が SQL から来る
    if "prev_race_date" in df.columns:
        df["days_since_last_race"] = (
            df["date"] - pd.to_datetime(df["prev_race_date"], errors="coerce")
        ).dt.days.astype(float)
        df = df.drop(columns=["prev_race_date"])

    # レース内ペース予想: predict 時は avg_corner_last3 が既に数値化済み
    # （学習時は compute_recent_stats() 側で算出後に同じロジックを適用）
    if "avg_corner_last3" in df.columns:
        df["corner_style_race_rank"] = df.groupby("race_id", observed=True)[
            "avg_corner_last3"
        ].rank(method="min", ascending=True, na_option="bottom")
        df["_is_leader_type"] = (df["avg_corner_last3"] <= 5.0).astype(float)
        df["race_leader_count"] = df.groupby("race_id", observed=True)[
            "_is_leader_type"
        ].transform("sum")
        df = df.drop(columns=["_is_leader_type"])

    # 性別・年齢の分離（例: '牡5' → sex='牡', age=5）
    df["sex"] = df["sex_age"].str.extract(r"^([^\d]+)")
    df["age"] = pd.to_numeric(df["sex_age"].str.extract(r"(\d+)$")[0], errors="coerce")

    # grade 補完: NULL の場合に race_name から (GI)/(GII)/(GIII)/(L) を抽出
    if "race_name" in df.columns:
        missing_grade = df["grade"].isna() | (df["grade"].astype(str).str.strip() == "")
        extracted = df.loc[missing_grade, "race_name"].str.extract(
            r"\((GI{1,3}|L)\)", expand=False
        )
        df.loc[missing_grade, "grade"] = extracted

    # ハンデ戦フラグ
    if "race_condition" in df.columns:
        df["is_handicap"] = (
            df["race_condition"].str.contains("ハンデ", na=False).astype(float)
        )
        df = df.drop(columns=["race_condition"])

    # カテゴリ変数
    cat_cols = [
        "venue",
        "course_type",
        "direction",
        "weather",
        "track_condition",
        "grade",
        "sex",
        "sire",
        "dam",
        "broodmare_sire",
        "jockey_id",
        "trainer_id",
    ]
    for col in cat_cols:
        df[col] = df[col].astype("category")

    # 不要カラムの削除
    df = df.drop(
        columns=["sex_age", "finish_time", "passing_order", "race_name"],
        errors="ignore",
    )

    return df


def compute_recent_stats(df: pd.DataFrame) -> pd.DataFrame:
    """近走成績フィーチャーを集計する（学習時）。

    情報リークを防ぐため当該レース自身を集計から除外する（shift(1)）。
    groupby().rolling() を使って高速化している（apply による Python ループを排除）。
    """
    df = df.copy()
    df["finishing_position"] = df["finishing_position"].astype(float)
    df["last_3f"] = df["last_3f"].astype(float)
    df["first_corner_pos"] = df["first_corner_pos"].astype(float)
    df["last_3f_rank"] = df["last_3f_rank"].astype(float)
    df["race_time_zscore"] = df["race_time_zscore"].astype(float)

    # ── 全レース共通: 直近3走・直近5走 ─────────────────────────────────────
    # 日付順に1回だけソートし、groupby().rolling() が各馬内で時系列順に動作するようにする
    df = df.sort_values(["horse_id", "date", "race_id"]).reset_index(drop=True)

    # 出走間隔（前走からの経過日数）
    df["_date_s"] = df.groupby("horse_id", observed=True)["date"].shift(1)
    df["days_since_last_race"] = (df["date"] - df["_date_s"]).dt.days.astype(float)
    df = df.drop(columns=["_date_s"])

    # 距離変化（前走との距離差）
    df["_dist_s"] = df.groupby("horse_id", observed=True)["distance"].shift(1)
    df["distance_change"] = pd.to_numeric(
        df["distance"], errors="coerce"
    ) - pd.to_numeric(df["_dist_s"], errors="coerce")
    df = df.drop(columns=["_dist_s"])

    # クラス変化（前走との class_level 差）
    if "class_level" in df.columns:
        df["_class_s"] = df.groupby("horse_id", observed=True)["class_level"].shift(1)
        df["class_change"] = df["class_level"] - df["_class_s"]
        df = df.drop(columns=["_class_s"])

    # コース替わりフラグ（前走との course_type 変更）
    df["_course_s"] = df.groupby("horse_id", observed=True)["course_type"].shift(1)
    same_course = df["course_type"] == df["_course_s"]
    df["course_type_change"] = (~same_course).astype(float)
    df.loc[df["_course_s"].isna(), "course_type_change"] = float("nan")
    df = df.drop(columns=["_course_s"])

    # 騎手乗り替わりフラグ（前走と騎手が異なるか）
    df["_jockey_s"] = df.groupby("horse_id", observed=True)["jockey_id"].shift(1)
    same_jockey = df["jockey_id"] == df["_jockey_s"]
    df["jockey_change"] = (~same_jockey).astype(float)
    df.loc[df["_jockey_s"].isna(), "jockey_change"] = float("nan")
    df = df.drop(columns=["_jockey_s"])

    # 直近3走・5走: shift(1..5) をまとめて計算（groupby().rolling() より大幅に高速）
    # rolling(n, min_periods=1).mean/min は shift(1)..shift(n) の mean/min と等価
    _roll_cols = [
        "finishing_position",
        "last_3f",
        "first_corner_pos",
        "last_3f_rank",
        "race_time_zscore",
    ]
    _grp = df.groupby("horse_id", observed=True)
    _all_shifts = pd.concat(
        [_grp[_roll_cols].shift(k).add_suffix(f"__s{k}") for k in range(1, 6)],
        axis=1,
    )
    for n in [3, 5]:
        _sub_pos = _all_shifts[[f"finishing_position__s{k}" for k in range(1, n + 1)]]
        df[f"avg_finish_last{n}"] = _sub_pos.mean(axis=1, skipna=True)
        df[f"best_finish_last{n}"] = _sub_pos.min(axis=1, skipna=True)

        _sub_l3f = _all_shifts[[f"last_3f__s{k}" for k in range(1, n + 1)]]
        df[f"avg_last3f_last{n}"] = _sub_l3f.mean(axis=1, skipna=True)

        _sub_cor = _all_shifts[[f"first_corner_pos__s{k}" for k in range(1, n + 1)]]
        df[f"avg_corner_last{n}"] = _sub_cor.mean(axis=1, skipna=True)

        _sub_rnk = _all_shifts[[f"last_3f_rank__s{k}" for k in range(1, n + 1)]]
        df[f"avg_last3f_rank_last{n}"] = _sub_rnk.mean(axis=1, skipna=True)

        _sub_tz = _all_shifts[[f"race_time_zscore__s{k}" for k in range(1, n + 1)]]
        df[f"avg_speed_index_last{n}"] = _sub_tz.mean(axis=1, skipna=True)

    # ── 同コース種別・同距離: 直近3走・直近5走 ──────────────────────────────
    cond_key = ["horse_id", "course_type", "distance"]
    df_cond = df.sort_values(cond_key + ["date", "race_id"])

    _grp_c = df_cond.groupby(cond_key, observed=True)
    _all_shifts_c = pd.concat(
        [_grp_c[_roll_cols].shift(k).add_suffix(f"__s{k}") for k in range(1, 6)],
        axis=1,
    )
    for n in [3, 5]:
        _sub_pos = _all_shifts_c[[f"finishing_position__s{k}" for k in range(1, n + 1)]]
        df_cond[f"avg_finish_last{n}_cond"] = _sub_pos.mean(axis=1, skipna=True)
        df_cond[f"best_finish_last{n}_cond"] = _sub_pos.min(axis=1, skipna=True)

        _sub_l3f = _all_shifts_c[[f"last_3f__s{k}" for k in range(1, n + 1)]]
        df_cond[f"avg_last3f_last{n}_cond"] = _sub_l3f.mean(axis=1, skipna=True)

        _sub_cor = _all_shifts_c[[f"first_corner_pos__s{k}" for k in range(1, n + 1)]]
        df_cond[f"avg_corner_last{n}_cond"] = _sub_cor.mean(axis=1, skipna=True)

        _sub_rnk = _all_shifts_c[[f"last_3f_rank__s{k}" for k in range(1, n + 1)]]
        df_cond[f"avg_last3f_rank_last{n}_cond"] = _sub_rnk.mean(axis=1, skipna=True)

    cond_stat_cols = [
        f"{stat}_last{n}_cond"
        for stat in [
            "avg_finish",
            "best_finish",
            "avg_last3f",
            "avg_corner",
            "avg_last3f_rank",
        ]
        for n in [3, 5]
    ]
    for col in cond_stat_cols:
        df[col] = df_cond[col]

    # ── 騎手×競馬場×コース種別: 累積勝率 ────────────────────────────────────
    jockey_key = ["jockey_id", "venue", "course_type"]
    df_jockey = df.sort_values(jockey_key + ["date", "race_id"])

    # cumcount() = 当該レース以前に同グループで出走した回数（0-indexed）
    df_jockey["_jockey_race_count"] = df_jockey.groupby(
        jockey_key, observed=True
    ).cumcount()
    # cumsum() = 当該レースを含む累積勝利数
    df_jockey["_jockey_cumwins"] = (
        df_jockey.groupby(jockey_key, observed=True)["is_win"].cumsum().astype(float)
    )
    # shift(1) で当該レースを除いた累積勝利数を取得
    df_jockey["_jockey_prior_wins"] = (
        df_jockey.groupby(jockey_key, observed=True, sort=False)["_jockey_cumwins"]
        .shift(1)
        .fillna(0.0)
    )

    df_jockey["jockey_win_rate_venue_cond"] = df_jockey["_jockey_prior_wins"] / (
        df_jockey["_jockey_race_count"].replace(0, float("nan"))
    )
    df_jockey = df_jockey.drop(
        columns=["_jockey_race_count", "_jockey_cumwins", "_jockey_prior_wins"]
    )
    df["jockey_win_rate_venue_cond"] = df_jockey["jockey_win_rate_venue_cond"]

    # ── 血統適性統計（複勝率ベース + 縮小推定 + スピード指数） ─────────────────
    # 2026-08-09の検証で「父馬×コース種別×距離帯の単勝勝率」はbootstrap有意差なし
    # （win/place_logloss・win_accuracyいずれも95%CIが0を跨ぐ）と判明。単勝は稀事象で
    # 父馬あたりのサンプルが薄いと高分散になるため、(1) 発生率の高い複勝率に変更し、
    # (2) 少サンプルの極端値を抑える縮小推定（shrinkage）を追加し、(3) 連続値である
    # スピード指数（race_time_zscore）ベースの適性指標も別軸として検証する。
    # 日付単位で集計してから1日分ずらす方式（owner_prior_win_rate と同じ）は、
    # 同じ父馬の産駒が同一レースに複数出走する場合のリークを防ぐため必須。
    # 2026-08-10 bootstrap 有意差検定で win_logloss・place_logloss・win_accuracy
    # すべて有意に改善（95%CIが0を跨がない）を確認し採用。母父馬×馬場状態版は
    # 単体・組み合わせとも劣ったため不採用（詳細は docs/experiments.md 参照）。
    _global_place_rate = float(df["is_placed"].mean())

    # パターンD+E: 父馬(sire) × コース種別: 産駒の複勝率（縮小推定）
    sire_place_daily = (
        df.groupby(["sire", "course_type", "date"], observed=True)["is_placed"]
        .agg(_daily_mounts="count", _daily_places="sum")
        .reset_index()
        .sort_values(["sire", "course_type", "date"])
    )
    _grp_sire_place = sire_place_daily.groupby(["sire", "course_type"], observed=True)
    sire_place_daily["sire_progeny_mounts_cond"] = (
        _grp_sire_place["_daily_mounts"].cumsum() - sire_place_daily["_daily_mounts"]
    ).astype(float)
    _sire_prior_places = (
        _grp_sire_place["_daily_places"].cumsum() - sire_place_daily["_daily_places"]
    ).astype(float)
    sire_place_daily["sire_place_rate_cond"] = (
        _sire_prior_places + _PEDIGREE_K_SHRINK * _global_place_rate
    ) / (sire_place_daily["sire_progeny_mounts_cond"] + _PEDIGREE_K_SHRINK)
    df = df.merge(
        sire_place_daily[
            [
                "sire",
                "course_type",
                "date",
                "sire_place_rate_cond",
                "sire_progeny_mounts_cond",
            ]
        ],
        on=["sire", "course_type", "date"],
        how="left",
    )

    # パターンF: 父馬(sire) × コース種別: 産駒の平均スピード指数（縮小推定）
    sire_speed_daily = (
        df.groupby(["sire", "course_type", "date"], observed=True)["race_time_zscore"]
        .agg(_daily_count="count", _daily_sum="sum")
        .reset_index()
        .sort_values(["sire", "course_type", "date"])
    )
    _grp_sire_speed = sire_speed_daily.groupby(["sire", "course_type"], observed=True)
    _sire_speed_prior_count = (
        _grp_sire_speed["_daily_count"].cumsum() - sire_speed_daily["_daily_count"]
    ).astype(float)
    _sire_speed_prior_sum = (
        _grp_sire_speed["_daily_sum"].cumsum() - sire_speed_daily["_daily_sum"]
    ).astype(float)
    # スピード指数（race_time_zscore）はレース内正規化により母平均が0のため、
    # 縮小推定は「0点のダミーサンプルをK_SPEED_SHRINK個混ぜる」の単純な形になる。
    sire_speed_daily["sire_avg_speed_index_cond"] = _sire_speed_prior_sum / (
        _sire_speed_prior_count + _PEDIGREE_K_SPEED_SHRINK
    )
    df = df.merge(
        sire_speed_daily[["sire", "course_type", "date", "sire_avg_speed_index_cond"]],
        on=["sire", "course_type", "date"],
        how="left",
    )

    # ── 調教師: 直近30走勝率 ──────────────────────────────────────────────
    trainer_key = ["trainer_id"]
    df_trainer = df.sort_values(trainer_key + ["date", "race_id"])

    df_trainer["_trainer_is_win_s"] = df_trainer.groupby(trainer_key, observed=True)[
        "is_win"
    ].shift(1)

    df_trainer["trainer_win_rate_last30"] = (
        df_trainer.groupby(trainer_key, observed=True, sort=False)["_trainer_is_win_s"]
        .rolling(30, min_periods=1)
        .mean()
        .reset_index(level=0, drop=True)
    )
    df_trainer = df_trainer.drop(columns=["_trainer_is_win_s"])
    df["trainer_win_rate_last30"] = df_trainer["trainer_win_rate_last30"]

    # ── 調教師: 全期間累積勝率（デビューからそのレース直前まで） ────────────────
    # 同日の複数レースの前後関係は分からないため、日付単位で集計してから
    # 当日分を除く（＝1日分ずらす）ことでリークを防ぐ。
    trainer_daily = (
        df.groupby(["trainer_id", "date"], observed=True)["is_win"]
        .agg(_daily_mounts="count", _daily_wins="sum")
        .reset_index()
        .sort_values(["trainer_id", "date"])
    )
    _grp_trainer_daily = trainer_daily.groupby("trainer_id", observed=True)
    trainer_daily["trainer_prior_mounts"] = (
        _grp_trainer_daily["_daily_mounts"].cumsum() - trainer_daily["_daily_mounts"]
    ).astype(float)
    _trainer_prior_wins = (
        _grp_trainer_daily["_daily_wins"].cumsum() - trainer_daily["_daily_wins"]
    ).astype(float)
    trainer_daily["trainer_prior_win_rate"] = _trainer_prior_wins / trainer_daily[
        "trainer_prior_mounts"
    ].replace(0, float("nan"))
    df = df.merge(
        trainer_daily[
            ["trainer_id", "date", "trainer_prior_win_rate", "trainer_prior_mounts"]
        ],
        on=["trainer_id", "date"],
        how="left",
    )

    # ── 騎手: 全期間累積勝率（デビューからそのレース直前まで） ──────────────────
    jockey_daily = (
        df.groupby(["jockey_id", "date"], observed=True)["is_win"]
        .agg(_daily_mounts="count", _daily_wins="sum")
        .reset_index()
        .sort_values(["jockey_id", "date"])
    )
    _grp_jockey_daily = jockey_daily.groupby("jockey_id", observed=True)
    jockey_daily["jockey_prior_mounts"] = (
        _grp_jockey_daily["_daily_mounts"].cumsum() - jockey_daily["_daily_mounts"]
    ).astype(float)
    _jockey_prior_wins = (
        _grp_jockey_daily["_daily_wins"].cumsum() - jockey_daily["_daily_wins"]
    ).astype(float)
    jockey_daily["jockey_prior_win_rate"] = _jockey_prior_wins / jockey_daily[
        "jockey_prior_mounts"
    ].replace(0, float("nan"))
    df = df.merge(
        jockey_daily[
            ["jockey_id", "date", "jockey_prior_win_rate", "jockey_prior_mounts"]
        ],
        on=["jockey_id", "date"],
        how="left",
    )

    # ── 馬主: 全期間累積勝率（デビューからそのレース直前まで） ──────────────────
    # horses.owner_id は入力率が低いため、race_results.owner（文字列）をキーにする。
    owner_daily = (
        df.groupby(["owner", "date"], observed=True)["is_win"]
        .agg(_daily_mounts="count", _daily_wins="sum")
        .reset_index()
        .sort_values(["owner", "date"])
    )
    _grp_owner_daily = owner_daily.groupby("owner", observed=True)
    owner_daily["owner_prior_mounts"] = (
        _grp_owner_daily["_daily_mounts"].cumsum() - owner_daily["_daily_mounts"]
    ).astype(float)
    _owner_prior_wins = (
        _grp_owner_daily["_daily_wins"].cumsum() - owner_daily["_daily_wins"]
    ).astype(float)
    owner_daily["owner_prior_win_rate"] = _owner_prior_wins / owner_daily[
        "owner_prior_mounts"
    ].replace(0, float("nan"))
    df = df.merge(
        owner_daily[["owner", "date", "owner_prior_win_rate", "owner_prior_mounts"]],
        on=["owner", "date"],
        how="left",
    )

    # ── 枠番 × 距離帯: 累積平均着順 ────────────────────────────────────────
    df["_distance_band"] = pd.cut(
        pd.to_numeric(df["distance"], errors="coerce"),
        bins=[0, 1400, 1800, 2200, 10000],
        labels=[0, 1, 2, 3],
    )
    bracket_key = ["bracket_number", "_distance_band"]
    df_bracket = df.sort_values(bracket_key + ["date", "race_id"])

    df_bracket["_bracket_cumcount"] = df_bracket.groupby(
        bracket_key, observed=True
    ).cumcount()
    df_bracket["_bracket_cumsum"] = (
        df_bracket.groupby(bracket_key, observed=True)["finishing_position"]
        .cumsum()
        .astype(float)
    )
    df_bracket["_bracket_prior_sum"] = df_bracket.groupby(
        bracket_key, observed=True, sort=False
    )["_bracket_cumsum"].shift(1)
    df_bracket["bracket_distance_avg_finish"] = df_bracket[
        "_bracket_prior_sum"
    ] / df_bracket["_bracket_cumcount"].replace(0, float("nan"))

    df["bracket_distance_avg_finish"] = df_bracket["bracket_distance_avg_finish"]
    df = df.drop(columns=["_distance_band"])

    # ── レース内ペース予想: レース内の相対脚質順位・先行馬（逃げ・先行）頭数 ──────────
    df["corner_style_race_rank"] = df.groupby("race_id", observed=True)[
        "avg_corner_last3"
    ].rank(method="min", ascending=True, na_option="bottom")
    df["_is_leader_type"] = (df["avg_corner_last3"] <= 5.0).astype(float)
    df["race_leader_count"] = df.groupby("race_id", observed=True)[
        "_is_leader_type"
    ].transform("sum")
    df = df.drop(columns=["_is_leader_type"])

    return df


def compute_time_decay_weight(
    race_date: pd.Series,
    reference_date: pd.Timestamp,
    half_life_days: float,
) -> np.ndarray:
    """レース日付からの経過日数に応じた指数減衰サンプルウェイトを計算する。

    ``reference_date`` から ``half_life_days`` 日離れるごとにウェイトが半減する。
    直近レースほど大きい重みになる（非定常性への対処）。

    Parameters
    ----------
    race_date : pd.Series
        datetime64 型の日付列。
    reference_date : pd.Timestamp
        基準日（通常は学習データの最新レース日）。
    half_life_days : float
        重みが半減するまでの日数。

    Returns
    -------
    np.ndarray
        各行に対応するサンプルウェイト（``reference_date`` の行が 1.0 で最大）。
    """
    days_from_reference = (reference_date - race_date).dt.days
    return (0.5 ** (days_from_reference / half_life_days)).to_numpy()


def get_feature_columns(extra_columns: list[str] | None = None) -> list[str]:
    """学習・推論に使う特徴量カラム名の一覧を返す。

    Parameters
    ----------
    extra_columns : list[str] | None
        末尾に追加する特徴量カラム名（Embedding特徴量統合用）。``None``
        （デフォルト）の場合は従来どおりの一覧をそのまま返す。
    """
    cols = [
        # レース条件
        "venue",
        "course_type",
        "distance",
        "direction",
        "weather",
        "track_condition",
        "grade",
        "head_count",
        "is_handicap",
        "class_level",
        # 出走馬情報
        "horse_number",
        "bracket_number",
        "sex",
        "age",
        "weight_carried",
        "weight_carried_relative",
        "horse_weight",
        "horse_weight_diff",
        "horse_weight_relative",
        # 前走との比較
        "distance_change",
        "course_type_change",
        "jockey_change",
        "class_change",
        "days_since_last_race",
        # 近走成績（全レース・直近3走）
        "avg_finish_last3",
        "best_finish_last3",
        "avg_last3f_last3",
        # 近走成績（全レース・直近5走）
        "avg_finish_last5",
        "best_finish_last5",
        "avg_last3f_last5",
        # 近走成績（同コース種別・同距離・直近3走）
        "avg_finish_last3_cond",
        "best_finish_last3_cond",
        "avg_last3f_last3_cond",
        # 近走成績（同コース種別・同距離・直近5走）
        "avg_finish_last5_cond",
        "best_finish_last5_cond",
        "avg_last3f_last5_cond",
        # 先行指数（全レース）
        "avg_corner_last3",
        "avg_corner_last5",
        # 先行指数（同コース種別・同距離）
        "avg_corner_last3_cond",
        "avg_corner_last5_cond",
        # レース内ペース予想
        "corner_style_race_rank",
        "race_leader_count",
        # 上がり3ハロン相対順位（全レース）
        "avg_last3f_rank_last3",
        "avg_last3f_rank_last5",
        # 上がり3ハロン相対順位（同コース種別・同距離）
        "avg_last3f_rank_last3_cond",
        "avg_last3f_rank_last5_cond",
        # タイム偏差値（スピード指数）
        "avg_speed_index_last3",
        "avg_speed_index_last5",
        # 血統
        "sire",
        # ADR-0030 により除外: permutation importance検定で有意な寄与が確認できず、
        # 除外後の方がwin_logloss/place_logloss/win_accuracyが有意に改善
        # "dam",
        "broodmare_sire",
        # 血統適性統計（父馬×コース種別の産駒複勝率・平均スピード指数、縮小推定）
        "sire_place_rate_cond",
        "sire_progeny_mounts_cond",
        "sire_avg_speed_index_cond",
        # 騎手統計
        "jockey_win_rate_venue_cond",
        "jockey_prior_win_rate",
        "jockey_prior_mounts",
        # 調教師統計
        "trainer_win_rate_last30",
        "trainer_prior_win_rate",
        "trainer_prior_mounts",
        # 馬主統計
        "owner_prior_win_rate",
        "owner_prior_mounts",
        # 騎手・調教師
        "jockey_id",
        "trainer_id",
        # 枠番 × 距離帯
        "bracket_distance_avg_finish",
    ]
    if extra_columns:
        cols = cols + list(extra_columns)
    return cols


def split_by_date(
    df: pd.DataFrame,
    val_ratio: float = VAL_RATIO,
    test_ratio: float = TEST_RATIO,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """時系列分割でトレーニング・バリデーション・テストデータに3分割する。

    直近 ``test_ratio`` 割をテストデータ、その直前 ``val_ratio`` 割を
    バリデーションデータ（較正用）、残りをトレーニングデータとする。

    Returns
    -------
    tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]
        (train_df, val_df, test_df)
    """
    dates = df["date"].dropna().sort_values().unique()
    val_idx = int(len(dates) * (1 - val_ratio - test_ratio))
    test_idx = int(len(dates) * (1 - test_ratio))
    val_date = dates[val_idx]
    test_date = dates[test_idx]

    train_df = df[df["date"] < val_date].copy()
    val_df = df[(df["date"] >= val_date) & (df["date"] < test_date)].copy()
    test_df = df[df["date"] >= test_date].copy()

    return train_df, val_df, test_df


def walk_forward_splits(
    df: pd.DataFrame,
    n_splits: int = 5,
) -> list[tuple[pd.DataFrame, pd.DataFrame]]:
    """Walk-forward（expanding window）時系列交差検証の分割を生成する。

    全期間を ``n_splits + 1`` に均等分割し、n_splits 個の (train_df, test_df) ペアを返す。
    フォールド i では 0..i 期間の累積データで学習し、i+1 期間をテストする
    （expanding window 方式）。

    Parameters
    ----------
    df : pd.DataFrame
        date カラムを持つデータ
    n_splits : int
        分割数。デフォルト 5。

    Returns
    -------
    list of tuple[pd.DataFrame, pd.DataFrame]
        (train_df, test_df) のリスト。長さ最大 n_splits。
        学習データが空のフォールドはスキップされる。
    """
    dates = df["date"].dropna().sort_values().unique()
    n = len(dates)

    if n < n_splits + 1:
        raise ValueError(
            f"日付数 ({n}) が n_splits + 1 ({n_splits + 1}) より少ないため分割できません"
        )

    # n_splits + 1 個の境界インデックスを等間隔で計算
    split_points = [int(n * i / (n_splits + 1)) for i in range(1, n_splits + 2)]

    splits = []
    for i in range(n_splits):
        train_end_idx = split_points[i]
        test_end_idx = split_points[i + 1]

        train_end_date = dates[train_end_idx]
        test_start_date = dates[train_end_idx]
        test_end_date = dates[test_end_idx - 1]

        train_df = df[df["date"] < train_end_date].copy()
        test_df = df[
            (df["date"] >= test_start_date) & (df["date"] <= test_end_date)
        ].copy()

        if len(train_df) > 0 and len(test_df) > 0:
            splits.append((train_df, test_df))

    return splits

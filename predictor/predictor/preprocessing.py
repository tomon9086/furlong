"""データ前処理モジュール"""

from __future__ import annotations

import re

import pandas as pd
import psycopg

# テストデータに使う直近の割合
TEST_RATIO = 0.2

_SELECT_COLS = """
    r.race_id,
    r.date,
    r.venue,
    r.course_type,
    r.distance,
    r.direction,
    r.weather,
    r.track_condition,
    r.grade,
    r.head_count,
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
history AS (
  SELECT
    rr.horse_id,
    TO_DATE(r.date, 'YYYY/MM/DD') AS race_date,
    r.race_id,
    r.course_type,
    r.distance,
    rr.finishing_position::integer AS finishing_pos,
    CASE WHEN rr.last_3f ~ '^\\d+\\.?\\d*$' THEN rr.last_3f::float ELSE NULL END AS last_3f_num,
    CASE WHEN rr.passing_order ~ '^\\d' THEN SPLIT_PART(rr.passing_order, '-', 1)::integer ELSE NULL END AS first_corner_pos,
    rl.last_3f_rank
  FROM race_results rr
  JOIN races r ON rr.race_id = r.race_id
  LEFT JOIN race_last3f rl ON rr.race_id = rl.race_id AND rr.horse_id = rl.horse_id
  WHERE rr.finishing_position ~ '^[0-9]+$'
    AND rr.horse_id = ANY(%s)
),
windowed AS (
  SELECT
    horse_id,
    course_type,
    distance,
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
    avg_last3f_rank_last3, avg_last3f_rank_last5
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
  lc.avg_finish_last3_cond, lc.best_finish_last3_cond, lc.avg_last3f_last3_cond,
  lc.avg_finish_last5_cond, lc.best_finish_last5_cond, lc.avg_last3f_last5_cond,
  lc.avg_corner_last3_cond, lc.avg_corner_last5_cond,
  lc.avg_last3f_rank_last3_cond, lc.avg_last3f_rank_last5_cond
FROM latest_all la
LEFT JOIN latest_cond lc ON la.horse_id = lc.horse_id
"""


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
            course_type = target_df["course_type"].iloc[0]
            distance = int(target_df["distance"].iloc[0])

            cur.execute(_RECENT_STATS_QUERY, (horse_ids, course_type, distance))
            stats_rows = cur.fetchall()
            stats_cols = [desc[0] for desc in cur.description]
            stats_df = pd.DataFrame(stats_rows, columns=stats_cols)

    return target_df.merge(stats_df, on="horse_id", how="left")


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

    # 数値変換
    for col in (
        "odds",
        "popularity",
        "weight_carried",
        "last_3f",
        "horse_number",
        "bracket_number",
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

    # last_3f のレース内相対順位（順位1 = 最速）
    df["last_3f_rank"] = df.groupby("race_id")["last_3f"].rank(
        method="min", ascending=True, na_option="keep"
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
    ):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # 性別・年齢の分離（例: '牡5' → sex='牡', age=5）
    df["sex"] = df["sex_age"].str.extract(r"^([^\d]+)")
    df["age"] = pd.to_numeric(df["sex_age"].str.extract(r"(\d+)$")[0], errors="coerce")

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
    df = df.drop(columns=["sex_age", "finish_time", "passing_order"])

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

    # ── 全レース共通: 直近3走・直近5走 ─────────────────────────────────────
    # 日付順に1回だけソートし、groupby().rolling() が各馬内で時系列順に動作するようにする
    df = df.sort_values(["horse_id", "date", "race_id"]).reset_index(drop=True)

    # 当該レースを除くため1つシフト（group 境界を超えない）
    df["_pos_s"] = df.groupby("horse_id", observed=True)["finishing_position"].shift(1)
    df["_last3f_s"] = df.groupby("horse_id", observed=True)["last_3f"].shift(1)
    df["_corner_s"] = df.groupby("horse_id", observed=True)["first_corner_pos"].shift(1)
    df["_last3f_rank_s"] = df.groupby("horse_id", observed=True)["last_3f_rank"].shift(1)

    for n, suffix in [(3, ""), (5, "")]:
        grp = df.groupby("horse_id", observed=True, sort=False)
        df[f"avg_finish_last{n}{suffix}"] = (
            grp["_pos_s"]
            .rolling(n, min_periods=1)
            .mean()
            .reset_index(level=0, drop=True)
        )
        df[f"best_finish_last{n}{suffix}"] = (
            grp["_pos_s"]
            .rolling(n, min_periods=1)
            .min()
            .reset_index(level=0, drop=True)
        )
        df[f"avg_last3f_last{n}{suffix}"] = (
            grp["_last3f_s"]
            .rolling(n, min_periods=1)
            .mean()
            .reset_index(level=0, drop=True)
        )
        df[f"avg_corner_last{n}{suffix}"] = (
            grp["_corner_s"]
            .rolling(n, min_periods=1)
            .mean()
            .reset_index(level=0, drop=True)
        )
        df[f"avg_last3f_rank_last{n}"] = (
            grp["_last3f_rank_s"]
            .rolling(n, min_periods=1)
            .mean()
            .reset_index(level=0, drop=True)
        )

    df = df.drop(columns=["_pos_s", "_last3f_s", "_corner_s", "_last3f_rank_s"])

    # ── 同コース種別・同距離: 直近3走・直近5走 ──────────────────────────────
    cond_key = ["horse_id", "course_type", "distance"]
    df_cond = df.sort_values(cond_key + ["date", "race_id"])

    df_cond = df_cond.assign(
        _pos_s_c=df_cond.groupby(cond_key, observed=True)["finishing_position"].shift(
            1
        ),
        _last3f_s_c=df_cond.groupby(cond_key, observed=True)["last_3f"].shift(1),
        _corner_s_c=df_cond.groupby(cond_key, observed=True)["first_corner_pos"].shift(1),
        _last3f_rank_s_c=df_cond.groupby(cond_key, observed=True)["last_3f_rank"].shift(1),
    )

    for n, suffix in [(3, "_cond"), (5, "_cond")]:
        grp_c = df_cond.groupby(cond_key, observed=True, sort=False)
        df_cond[f"avg_finish_last{n}{suffix}"] = (
            grp_c["_pos_s_c"]
            .rolling(n, min_periods=1)
            .mean()
            .reset_index(level=[0, 1, 2], drop=True)
        )
        df_cond[f"best_finish_last{n}{suffix}"] = (
            grp_c["_pos_s_c"]
            .rolling(n, min_periods=1)
            .min()
            .reset_index(level=[0, 1, 2], drop=True)
        )
        df_cond[f"avg_last3f_last{n}{suffix}"] = (
            grp_c["_last3f_s_c"]
            .rolling(n, min_periods=1)
            .mean()
            .reset_index(level=[0, 1, 2], drop=True)
        )
        df_cond[f"avg_corner_last{n}{suffix}"] = (
            grp_c["_corner_s_c"]
            .rolling(n, min_periods=1)
            .mean()
            .reset_index(level=[0, 1, 2], drop=True)
        )
        df_cond[f"avg_last3f_rank_last{n}{suffix}"] = (
            grp_c["_last3f_rank_s_c"]
            .rolling(n, min_periods=1)
            .mean()
            .reset_index(level=[0, 1, 2], drop=True)
        )

    cond_stat_cols = [
        f"{stat}_last{n}_cond"
        for stat in ["avg_finish", "best_finish", "avg_last3f", "avg_corner", "avg_last3f_rank"]
        for n in [3, 5]
    ]
    for col in cond_stat_cols:
        df[col] = df_cond[col]

    return df


def get_feature_columns() -> list[str]:
    """学習・推論に使う特徴量カラム名の一覧を返す。"""
    return [
        # レース条件
        "venue",
        "course_type",
        "distance",
        "direction",
        "weather",
        "track_condition",
        "grade",
        "head_count",
        # 出走馬情報
        "horse_number",
        "bracket_number",
        "sex",
        "age",
        "weight_carried",
        "horse_weight",
        "horse_weight_diff",
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
        # 上がり3ハロン相対順位（全レース）
        "avg_last3f_rank_last3",
        "avg_last3f_rank_last5",
        # 上がり3ハロン相対順位（同コース種別・同距離）
        "avg_last3f_rank_last3_cond",
        "avg_last3f_rank_last5_cond",
        # 血統
        "sire",
        "dam",
        "broodmare_sire",
        # 騎手・調教師
        "jockey_id",
        "trainer_id",
    ]


def split_by_date(
    df: pd.DataFrame, test_ratio: float = TEST_RATIO
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """時系列分割でトレーニング・テストデータに分割する。

    直近 ``test_ratio`` 割のレースをテストデータとする。
    """
    dates = df["date"].dropna().sort_values().unique()
    split_idx = int(len(dates) * (1 - test_ratio))
    split_date = dates[split_idx]

    train_df = df[df["date"] < split_date].copy()
    test_df = df[df["date"] >= split_date].copy()

    return train_df, test_df

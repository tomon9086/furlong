"""データ前処理モジュール"""

from __future__ import annotations

import re

import pandas as pd
import psycopg

# テストデータに使う直近の割合
TEST_RATIO = 0.2

_QUERY = """
SELECT
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
    rr.sex_age,
    rr.weight_carried,
    rr.jockey_id,
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
    h.broodmare_sire
FROM races r
JOIN race_results rr ON r.race_id = rr.race_id
LEFT JOIN horses h ON rr.horse_id = h.horse_id
WHERE rr.finishing_position ~ '^[0-9]+$'
ORDER BY TO_DATE(r.date, 'YYYY/MM/DD'), r.race_id, rr.horse_number::integer
"""


def load_data(database_url: str) -> pd.DataFrame:
    """PostgreSQL からレース・出走馬データを読み込む。"""
    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(_QUERY)
            rows = cur.fetchall()
            cols = [desc[0] for desc in cur.description]
    return pd.DataFrame(rows, columns=cols)


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


def preprocess(df: pd.DataFrame) -> pd.DataFrame:
    """生データを機械学習に適した形に変換する。"""
    df = df.copy()

    # 日付
    df["date"] = pd.to_datetime(df["date"], format="%Y/%m/%d", errors="coerce")

    # ターゲット変数
    df["finishing_position"] = pd.to_numeric(df["finishing_position"], errors="coerce")
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
    df["finish_time_sec"] = df["finish_time"].apply(_parse_finish_time)

    # 通過順（最初のコーナー位置）
    df["first_corner_pos"] = df["passing_order"].apply(_parse_first_corner)

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
        # 市場評価
        "odds",
        "popularity",
        # 血統
        "sire",
        "dam",
        "broodmare_sire",
        # 騎手・調教師
        "jockey_id",
        "trainer_id",
        # レースパフォーマンス（学習時のみ利用可）
        "last_3f",
        "finish_time_sec",
        "first_corner_pos",
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

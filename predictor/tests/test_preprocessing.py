"""predictor.preprocessing の単体テスト."""

import numpy as np
import pandas as pd
import pytest

from predictor.preprocessing import (
    _extract_class_level,
    _parse_finish_time,
    _parse_first_corner,
    compute_recent_stats,
    compute_time_decay_weight,
    preprocess,
    split_by_date,
    walk_forward_splits,
)

# ──────────────────────────────────────────────
# _parse_finish_time
# ──────────────────────────────────────────────


class TestParseFinishTime:
    def test_minutes_seconds(self):
        assert _parse_finish_time("1:23.4") == pytest.approx(83.4)

    def test_seconds_only(self):
        assert _parse_finish_time("65.2") == pytest.approx(65.2)

    def test_none(self):
        assert _parse_finish_time(None) is None

    def test_nan(self):
        assert _parse_finish_time(float("nan")) is None

    def test_invalid_string(self):
        assert _parse_finish_time("abc") is None


# ──────────────────────────────────────────────
# _parse_first_corner
# ──────────────────────────────────────────────


class TestParseFirstCorner:
    def test_multi_corner(self):
        assert _parse_first_corner("03-03-02-02") == 3

    def test_single_value(self):
        assert _parse_first_corner("05") == 5

    def test_none(self):
        assert _parse_first_corner(None) is None

    def test_nan(self):
        assert _parse_first_corner(float("nan")) is None

    def test_invalid(self):
        assert _parse_first_corner("abc") is None


# ──────────────────────────────────────────────
# _extract_class_level
# ──────────────────────────────────────────────


class TestExtractClassLevel:
    def test_shinba(self):
        assert _extract_class_level("4回中山7日目 2歳新馬　[指](馬齢)") == 0.0

    def test_mishoori(self):
        assert _extract_class_level("2回中山2日目 3歳未勝利　[指](馬齢)") == 1.0

    def test_old_naming_500man(self):
        assert _extract_class_level("1回中山2日目 4歳以上500万下　[指](定量)") == 2.0

    def test_new_naming_1shou_class(self):
        assert _extract_class_level("3回中山7日目 4歳以上1勝クラス　(混)(定量)") == 2.0

    def test_old_naming_1000man(self):
        assert _extract_class_level("5回京都2日目 3歳以上1000万下　(定量)") == 3.0

    def test_new_naming_2shou_class(self):
        assert _extract_class_level("1回中京9日目 4歳以上2勝クラス　(定量)") == 3.0

    def test_old_naming_1600man(self):
        assert _extract_class_level("2回東京12日目 4歳以上1600万下　(ハンデ)") == 4.0

    def test_new_naming_3shou_class(self):
        assert _extract_class_level("5回中山2日目 3歳以上3勝クラス　(ハンデ)") == 4.0

    def test_open(self):
        assert _extract_class_level("3回中山7日目 4歳以上オープン　(ハンデ)") == 5.0

    def test_none(self):
        assert _extract_class_level(None) is None

    def test_nan(self):
        assert _extract_class_level(float("nan")) is None

    def test_no_match(self):
        assert _extract_class_level("よくわからない条件") is None


# ──────────────────────────────────────────────
# 共通フィクスチャ
# ──────────────────────────────────────────────


def _make_raw_df(n: int = 3) -> pd.DataFrame:
    """最小限のレースデータを作成する（preprocess テスト用）。"""
    return pd.DataFrame(
        {
            "race_id": [f"R{i}" for i in range(n)],
            "date": ["2024/01/01"] * n,
            "venue": ["東京"] * n,
            "course_type": ["芝"] * n,
            "distance": ["1600"] * n,
            "direction": ["右"] * n,
            "weather": ["晴"] * n,
            "track_condition": ["良"] * n,
            "grade": ["G1"] * n,
            "head_count": [16] * n,
            "horse_number": [str(i + 1) for i in range(n)],
            "finishing_position": [str(i + 1) for i in range(n)],
            "bracket_number": [str(i + 1) for i in range(n)],
            "horse_id": [f"H{i}" for i in range(n)],
            "horse_name": [f"Horse{i}" for i in range(n)],
            "sex_age": ["牡4"] * n,
            "weight_carried": ["57.0"] * n,
            "jockey_id": [f"J{i}" for i in range(n)],
            "jockey_name": [f"Jockey{i}" for i in range(n)],
            "finish_time": ["1:33.4"] * n,
            "passing_order": ["04-04-03-02"] * n,
            "last_3f": ["34.5"] * n,
            "odds": ["5.2"] * n,
            "popularity": ["2"] * n,
            "horse_weight": ["480"] * n,
            "horse_weight_diff": ["0"] * n,
            "trainer_id": [f"T{i}" for i in range(n)],
            "sire": ["Sire"] * n,
            "dam": ["Dam"] * n,
            "broodmare_sire": ["BMS"] * n,
        }
    )


def _make_multi_race_raw_df() -> pd.DataFrame:
    """複数馬・複数レースのデータを作成する（compute_recent_stats テスト用）。"""
    rows = []
    for race_num in range(5):
        for horse_idx in range(2):
            rows.append(
                {
                    "race_id": f"R{race_num}",
                    "date": f"2024/01/{race_num + 1:02d}",
                    "venue": "東京",
                    "course_type": "芝",
                    "distance": "1600",
                    "direction": "右",
                    "weather": "晴",
                    "track_condition": "良",
                    "grade": "G1",
                    "head_count": 10,
                    "horse_number": str(horse_idx + 1),
                    "finishing_position": str(horse_idx + 1),
                    "bracket_number": str(horse_idx + 1),
                    "horse_id": f"H{horse_idx}",
                    "horse_name": f"Horse{horse_idx}",
                    "sex_age": "牡4",
                    "weight_carried": "57.0",
                    "jockey_id": f"J{horse_idx}",
                    "jockey_name": f"Jockey{horse_idx}",
                    "finish_time": "1:33.4",
                    "passing_order": "04-04-03-02",
                    "last_3f": "34.5",
                    "odds": "5.2",
                    "popularity": "2",
                    "horse_weight": "480",
                    "horse_weight_diff": "0",
                    "trainer_id": f"T{horse_idx}",
                    "owner": f"O{horse_idx}",
                    "sire": "Sire",
                    "dam": "Dam",
                    "broodmare_sire": "BMS",
                }
            )
    return pd.DataFrame(rows)


# ──────────────────────────────────────────────
# preprocess
# ──────────────────────────────────────────────


class TestPreprocess:
    def test_is_win(self):
        df = preprocess(_make_raw_df())
        assert list(df["is_win"]) == [1, 0, 0]

    def test_is_placed(self):
        df = preprocess(_make_raw_df())
        assert list(df["is_placed"]) == [1, 1, 1]

    def test_sex_age_split(self):
        df = preprocess(_make_raw_df())
        assert (df["sex"] == "牡").all()
        assert (df["age"] == 4).all()

    def test_finish_time_sec(self):
        df = preprocess(_make_raw_df())
        assert df["finish_time_sec"].iloc[0] == pytest.approx(93.4)

    def test_drop_original_columns(self):
        df = preprocess(_make_raw_df())
        assert "sex_age" not in df.columns
        assert "finish_time" not in df.columns
        assert "passing_order" not in df.columns

    def test_invalid_finishing_position_dropped(self):
        raw = _make_raw_df(3)
        raw.loc[0, "finishing_position"] = "取消"
        df = preprocess(raw)
        assert len(df) == 2

    def test_prev_course_type_creates_change_flag(self):
        """prev_course_type が与えられた場合、course_type_change が生成されること。"""
        raw = _make_raw_df(2)
        raw["prev_course_type"] = [
            "ダート",
            "芝",
        ]  # idx0: ダート→芝(変化), idx1: 芝→芝(変化なし)
        df = preprocess(raw)
        assert "course_type_change" in df.columns
        assert "prev_course_type" not in df.columns
        assert df["course_type_change"].iloc[0] == pytest.approx(1.0)
        assert df["course_type_change"].iloc[1] == pytest.approx(0.0)

    def test_prev_course_type_none_is_nan(self):
        """prev_course_type が NULL の場合、course_type_change は NaN であること。"""
        raw = _make_raw_df(1)
        raw["prev_course_type"] = [None]
        df = preprocess(raw)
        assert pd.isna(df["course_type_change"].iloc[0])

    def test_class_level_extracted_from_race_condition(self):
        """race_condition から class_level が抽出されること。"""
        raw = _make_raw_df(1)
        raw["race_condition"] = ["2回中山2日目 3歳未勝利　[指](馬齢)"]
        df = preprocess(raw)
        assert df["class_level"].iloc[0] == pytest.approx(1.0)

    def test_prev_race_condition_creates_class_change(self):
        """prev_race_condition が与えられた場合、class_change が生成されること。"""
        raw = _make_raw_df(1)
        raw["race_condition"] = ["3回中山7日目 4歳以上1勝クラス　(混)(定量)"]  # =2
        raw["prev_race_condition"] = ["2回中山2日目 3歳未勝利　[指](馬齢)"]  # =1
        df = preprocess(raw)
        assert "class_change" in df.columns
        assert "prev_race_condition" not in df.columns
        assert df["class_change"].iloc[0] == pytest.approx(1.0)  # 1勝クラスへ昇級

    def test_prev_race_condition_none_is_nan(self):
        """prev_race_condition が NULL の場合、class_change は NaN であること。"""
        raw = _make_raw_df(1)
        raw["race_condition"] = ["2回中山2日目 3歳未勝利　[指](馬齢)"]
        raw["prev_race_condition"] = [None]
        df = preprocess(raw)
        assert pd.isna(df["class_change"].iloc[0])

    def test_prev_race_date_creates_days_since_last_race(self):
        """prev_race_date が与えられた場合、days_since_last_race が計算されること。"""
        raw = _make_raw_df(2)
        raw["date"] = ["2024/01/10", "2024/01/10"]
        raw["prev_race_date"] = [pd.Timestamp("2023-12-20"), pd.Timestamp("2024-01-01")]
        df = preprocess(raw)
        assert "days_since_last_race" in df.columns
        assert "prev_race_date" not in df.columns
        assert df["days_since_last_race"].iloc[0] == pytest.approx(21.0)
        assert df["days_since_last_race"].iloc[1] == pytest.approx(9.0)

    def test_prev_race_date_none_is_nan(self):
        """prev_race_date が NULL の場合、days_since_last_race は NaN であること。"""
        raw = _make_raw_df(1)
        raw["prev_race_date"] = [None]
        df = preprocess(raw)
        assert pd.isna(df["days_since_last_race"].iloc[0])

    def test_race_time_zscore_computed_within_race(self):
        """race_time_zscore がレース内のタイム分布から z-score として計算されること。"""
        raw = _make_raw_df(3)
        raw["race_id"] = "R0"  # 3頭とも同一レースにする
        raw["finish_time"] = ["1:33.0", "1:34.0", "1:35.0"]
        df = preprocess(raw)
        assert df["race_time_zscore"].iloc[0] == pytest.approx(1.0)  # 最速
        assert df["race_time_zscore"].iloc[1] == pytest.approx(0.0)  # 平均
        assert df["race_time_zscore"].iloc[2] == pytest.approx(-1.0)  # 最遅

    def test_race_time_zscore_nan_when_all_same_time(self):
        """全馬同タイムで標準偏差が0の場合、race_time_zscore は NaN であること。"""
        raw = _make_raw_df(3)
        raw["race_id"] = "R0"  # 3頭とも同一レース、finish_time はデフォルトで全馬同じ
        df = preprocess(raw)
        assert df["race_time_zscore"].isna().all()


# ──────────────────────────────────────────────
# compute_recent_stats
# ──────────────────────────────────────────────


class TestComputeRecentStats:
    def test_no_leak_first_race(self):
        """1走目の近走成績はすべて NaN になること（過去データなし）。"""
        df = preprocess(_make_multi_race_raw_df())
        result = compute_recent_stats(df)
        first_races = result[result["race_id"] == "R0"]
        assert first_races["avg_finish_last3"].isna().all()

    def test_rolling_uses_past_only(self):
        """2走目は直前の1走だけを使って集計すること（情報リーク防止）。"""
        df = preprocess(_make_multi_race_raw_df())
        result = compute_recent_stats(df)
        # H0 は全レースで finishing_position=1
        h0_r1 = result[(result["horse_id"] == "H0") & (result["race_id"] == "R1")]
        assert h0_r1["avg_finish_last3"].iloc[0] == pytest.approx(1.0)

    def test_feature_columns_added(self):
        """近走成績カラムが追加されること。"""
        df = preprocess(_make_multi_race_raw_df())
        result = compute_recent_stats(df)
        expected_cols = [
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
            "bracket_distance_avg_finish",
        ]
        for col in expected_cols:
            assert col in result.columns, f"{col} が結果に含まれていません"

    def test_bracket_distance_avg_finish_no_leak_first_race(self):
        """1走目の bracket_distance_avg_finish は NaN になること（過去データなし）。"""
        df = preprocess(_make_multi_race_raw_df())
        result = compute_recent_stats(df)
        first_races = result[result["race_id"] == "R0"]
        assert first_races["bracket_distance_avg_finish"].isna().all()

    def test_bracket_distance_avg_finish_uses_past_only(self):
        """2走目以降は過去レースのみを使って平均着順を計算すること。"""
        df = preprocess(_make_multi_race_raw_df())
        result = compute_recent_stats(df)
        # bracket_number=1 の馬(H0)は全レースで finishing_position=1 なので
        # 2走目以降の bracket_distance_avg_finish は 1.0 に収束するはず
        h0_r4 = result[(result["horse_id"] == "H0") & (result["race_id"] == "R4")]
        assert h0_r4["bracket_distance_avg_finish"].iloc[0] == pytest.approx(1.0)

    def test_corner_style_race_rank_and_leader_count(self):
        """avg_corner_last3 に基づくレース内相対順位・先行馬頭数が正しいこと。"""
        rows = []
        # R0: 3頭が異なる先行度（H0=先頭寄り, H1=中団, H2=後方）で走る
        _corner_positions = [(0, "01-01-01-01"), (1, "05-05-05-05"), (2, "10-10-10-10")]
        for horse_idx, corner_pos in _corner_positions:
            rows.append(
                {
                    "race_id": "R0",
                    "date": "2024/01/01",
                    "venue": "東京",
                    "course_type": "芝",
                    "distance": "1600",
                    "direction": "右",
                    "weather": "晴",
                    "track_condition": "良",
                    "grade": "G1",
                    "head_count": 3,
                    "horse_number": str(horse_idx + 1),
                    "finishing_position": str(horse_idx + 1),
                    "bracket_number": str(horse_idx + 1),
                    "horse_id": f"H{horse_idx}",
                    "horse_name": f"Horse{horse_idx}",
                    "sex_age": "牡4",
                    "weight_carried": "57.0",
                    "jockey_id": f"J{horse_idx}",
                    "jockey_name": f"Jockey{horse_idx}",
                    "finish_time": "1:33.4",
                    "passing_order": corner_pos,
                    "last_3f": "34.5",
                    "odds": "5.2",
                    "popularity": "2",
                    "horse_weight": "480",
                    "horse_weight_diff": "0",
                    "trainer_id": f"T{horse_idx}",
                    "owner": f"O{horse_idx}",
                    "sire": "Sire",
                    "dam": "Dam",
                    "broodmare_sire": "BMS",
                }
            )
        # R1: 同じ3頭が再度出走（R0の脚質実績が avg_corner_last3 に反映される）
        for horse_idx in range(3):
            row = dict(rows[horse_idx])
            row["race_id"] = "R1"
            row["date"] = "2024/01/02"
            rows.append(row)
        raw = pd.DataFrame(rows)
        df = preprocess(raw)
        result = compute_recent_stats(df)
        r1 = result[result["race_id"] == "R1"].set_index("horse_id")
        # H0(avg_corner=1)が最も先行 → rank1、H2(avg_corner=10)が最も後方 → rank3
        assert r1.loc["H0", "corner_style_race_rank"] == pytest.approx(1.0)
        assert r1.loc["H1", "corner_style_race_rank"] == pytest.approx(2.0)
        assert r1.loc["H2", "corner_style_race_rank"] == pytest.approx(3.0)
        # 閾値5.0以下（H0=1, H1=5）の2頭が先行馬としてカウントされる
        assert r1.loc["H0", "race_leader_count"] == pytest.approx(2.0)

    def test_avg_speed_index_first_race_is_nan(self):
        """1走目のタイム偏差値（スピード指数）は NaN であること（過去データなし）。"""
        df = preprocess(_make_multi_race_raw_df())
        result = compute_recent_stats(df)
        first_races = result[result["race_id"] == "R0"]
        assert first_races["avg_speed_index_last3"].isna().all()

    def test_avg_speed_index_uses_past_only(self):
        """過去に速いタイムで走った馬ほど avg_speed_index_last3 が高くなること。"""
        raw = _make_multi_race_raw_df()
        # R0: H0が93秒（速い）、H1が95秒（遅い）
        raw.loc[(raw["horse_id"] == "H0") & (raw["race_id"] == "R0"), "finish_time"] = (
            "1:33.0"
        )
        raw.loc[(raw["horse_id"] == "H1") & (raw["race_id"] == "R0"), "finish_time"] = (
            "1:35.0"
        )
        df = preprocess(raw)
        result = compute_recent_stats(df)
        h0_r1 = result[(result["horse_id"] == "H0") & (result["race_id"] == "R1")]
        h1_r1 = result[(result["horse_id"] == "H1") & (result["race_id"] == "R1")]
        assert (
            h0_r1["avg_speed_index_last3"].iloc[0]
            > h1_r1["avg_speed_index_last3"].iloc[0]
        )

    def test_course_type_change_first_race_is_nan(self):
        """1走目のコース替わりフラグは NaN であること（前走なし）。"""
        df = preprocess(_make_multi_race_raw_df())
        result = compute_recent_stats(df)
        first_races = result[result["race_id"] == "R0"]
        assert first_races["course_type_change"].isna().all()

    def test_course_type_change_same_course_is_zero(self):
        """2走目以降、コースが変わらない場合はフラグは0であること。"""
        df = preprocess(_make_multi_race_raw_df())
        result = compute_recent_stats(df)
        later_races = result[result["race_id"] != "R0"]
        assert (later_races["course_type_change"] == 0.0).all()

    def test_class_change_first_race_is_nan(self):
        """1走目のクラス変化は NaN であること（前走なし）。"""
        raw = _make_multi_race_raw_df()
        raw["race_condition"] = "3歳未勝利"
        df = preprocess(raw)
        result = compute_recent_stats(df)
        first_races = result[result["race_id"] == "R0"]
        assert first_races["class_change"].isna().all()

    def test_class_change_computed_correctly(self):
        """2走目以降はクラスレベルの前走差になること（昇級で正の値）。"""
        raw = _make_multi_race_raw_df()
        raw["race_condition"] = "3歳未勝利"  # class_level=1
        # H0 の R1 を 1勝クラス（class_level=2）に変更 → 前走比 +1
        raw.loc[
            (raw["horse_id"] == "H0") & (raw["race_id"] == "R1"), "race_condition"
        ] = "4歳以上1勝クラス"
        df = preprocess(raw)
        result = compute_recent_stats(df)
        h0_r1 = result[(result["horse_id"] == "H0") & (result["race_id"] == "R1")]
        assert h0_r1["class_change"].iloc[0] == pytest.approx(1.0)

    def test_days_since_last_race_first_race_is_nan(self):
        """1走目の出走間隔は NaN であること（前走なし）。"""
        df = preprocess(_make_multi_race_raw_df())
        result = compute_recent_stats(df)
        first_races = result[result["race_id"] == "R0"]
        assert first_races["days_since_last_race"].isna().all()

    def test_days_since_last_race_computed_correctly(self):
        """2走目以降は前走との日数差になること。"""
        df = preprocess(_make_multi_race_raw_df())
        result = compute_recent_stats(df)
        # H0: R0=2024/01/01, R1=2024/01/02 -> 1日
        h0_r1 = result[(result["horse_id"] == "H0") & (result["race_id"] == "R1")]
        assert h0_r1["days_since_last_race"].iloc[0] == pytest.approx(1.0)

    def test_course_type_change_different_course_is_one(self):
        """2走目のコースが前走と異なる場合、フラグは1であること。"""
        raw = _make_multi_race_raw_df()
        # H0 の R1 を ダート に変更（R0 は芝 → R1 はダート）
        raw.loc[(raw["horse_id"] == "H0") & (raw["race_id"] == "R1"), "course_type"] = (
            "ダート"
        )
        df = preprocess(raw)
        result = compute_recent_stats(df)
        h0_r1 = result[(result["horse_id"] == "H0") & (result["race_id"] == "R1")]
        assert h0_r1["course_type_change"].iloc[0] == pytest.approx(1.0)

    def test_trainer_prior_win_rate_first_race_is_nan(self):
        """調教師の1走目は全期間累積勝率が NaN になること（過去騎乗数0）。"""
        df = preprocess(_make_multi_race_raw_df())
        result = compute_recent_stats(df)
        first_races = result[result["race_id"] == "R0"]
        assert first_races["trainer_prior_win_rate"].isna().all()
        assert (first_races["trainer_prior_mounts"] == 0.0).all()

    def test_trainer_prior_win_rate_accumulates_across_all_history(self):
        """調教師の全期間累積勝率は、直近30走に限らず過去全レースを使うこと。"""
        df = preprocess(_make_multi_race_raw_df())
        result = compute_recent_stats(df)
        # T0（H0の調教師）は全レースで1着なので、R4時点の累積勝率は1.0、累積騎乗数は4
        h0_r4 = result[(result["horse_id"] == "H0") & (result["race_id"] == "R4")]
        assert h0_r4["trainer_prior_win_rate"].iloc[0] == pytest.approx(1.0)
        assert h0_r4["trainer_prior_mounts"].iloc[0] == pytest.approx(4.0)

    def test_jockey_prior_win_rate_first_race_is_nan(self):
        """騎手の1走目は全期間累積勝率が NaN になること（過去騎乗数0）。"""
        df = preprocess(_make_multi_race_raw_df())
        result = compute_recent_stats(df)
        first_races = result[result["race_id"] == "R0"]
        assert first_races["jockey_prior_win_rate"].isna().all()
        assert (first_races["jockey_prior_mounts"] == 0.0).all()

    def test_jockey_prior_win_rate_accumulates_across_all_history(self):
        """騎手の全期間累積勝率は、venue×course_type に絞らず過去全レースを使うこと。"""
        df = preprocess(_make_multi_race_raw_df())
        result = compute_recent_stats(df)
        # J0（H0の騎手）は全レースで1着なので、R4時点の累積勝率は1.0、累積騎乗数は4
        h0_r4 = result[(result["horse_id"] == "H0") & (result["race_id"] == "R4")]
        assert h0_r4["jockey_prior_win_rate"].iloc[0] == pytest.approx(1.0)
        assert h0_r4["jockey_prior_mounts"].iloc[0] == pytest.approx(4.0)

    def test_prior_win_rate_same_day_races_excluded(self):
        """同日の複数レースは、互いの結果を「前情報」として使わないこと。"""
        raw = _make_multi_race_raw_df()
        # H0 の R1 を R0 と同じ日付にする（同日2レース目という扱い）
        raw.loc[raw["race_id"] == "R1", "date"] = raw.loc[
            raw["race_id"] == "R0", "date"
        ].iloc[0]
        df = preprocess(raw)
        result = compute_recent_stats(df)
        h0_r1 = result[(result["horse_id"] == "H0") & (result["race_id"] == "R1")]
        # R0 と同日なので、R0 の結果はまだ「前情報」に含まれない
        assert h0_r1["trainer_prior_mounts"].iloc[0] == pytest.approx(0.0)
        assert h0_r1["jockey_prior_mounts"].iloc[0] == pytest.approx(0.0)
        assert h0_r1["owner_prior_mounts"].iloc[0] == pytest.approx(0.0)

    def test_owner_prior_win_rate_first_race_is_nan(self):
        """馬主の1走目は全期間累積勝率が NaN になること（過去騎乗数0）。"""
        df = preprocess(_make_multi_race_raw_df())
        result = compute_recent_stats(df)
        first_races = result[result["race_id"] == "R0"]
        assert first_races["owner_prior_win_rate"].isna().all()
        assert (first_races["owner_prior_mounts"] == 0.0).all()

    def test_owner_prior_win_rate_accumulates_across_all_history(self):
        """馬主の全期間累積勝率は、過去全レースを使うこと。"""
        df = preprocess(_make_multi_race_raw_df())
        result = compute_recent_stats(df)
        # O0（H0の馬主）は全レースで1着なので、R4時点の累積勝率は1.0、累積騎乗数は4
        h0_r4 = result[(result["horse_id"] == "H0") & (result["race_id"] == "R4")]
        assert h0_r4["owner_prior_win_rate"].iloc[0] == pytest.approx(1.0)
        assert h0_r4["owner_prior_mounts"].iloc[0] == pytest.approx(4.0)


# ──────────────────────────────────────────────
# compute_time_decay_weight
# ──────────────────────────────────────────────


class TestComputeTimeDecayWeight:
    def test_reference_date_weight_is_one(self):
        """reference_date と同じ日付の行はウェイト1.0になること。"""
        dates = pd.Series(pd.to_datetime(["2024-01-01"]))
        w = compute_time_decay_weight(dates, pd.Timestamp("2024-01-01"), 365)
        assert w[0] == pytest.approx(1.0)

    def test_half_life_halves_weight(self):
        """half_life_days 経過した行はウェイトがちょうど半分になること。"""
        dates = pd.Series(pd.to_datetime(["2023-01-01"]))
        w = compute_time_decay_weight(dates, pd.Timestamp("2024-01-01"), 365)
        assert w[0] == pytest.approx(0.5, rel=1e-3)

    def test_older_dates_get_smaller_weight(self):
        """古い日付ほどウェイトが小さくなること（単調減少）。"""
        dates = pd.Series(pd.to_datetime(["2020-01-01", "2022-01-01", "2024-01-01"]))
        w = compute_time_decay_weight(dates, pd.Timestamp("2024-01-01"), 365)
        assert w[0] < w[1] < w[2]

    def test_returns_ndarray(self):
        dates = pd.Series(pd.to_datetime(["2024-01-01", "2023-06-01"]))
        w = compute_time_decay_weight(dates, pd.Timestamp("2024-01-01"), 1095)
        assert isinstance(w, np.ndarray)
        assert len(w) == 2


# ──────────────────────────────────────────────
# split_by_date
# ──────────────────────────────────────────────


class TestSplitByDate:
    def test_split_ratio(self):
        dates = pd.date_range("2020-01-01", periods=20, freq="D")
        df = pd.DataFrame({"date": dates, "x": range(20)})
        train, val, test = split_by_date(df, val_ratio=0.1, test_ratio=0.2)
        assert len(test) == 4  # 20 * 0.2
        assert len(val) == 2  # 20 * 0.1
        assert len(train) == 14  # 残り

    def test_no_future_leak(self):
        """train < val < test の日付順序が守られること。"""
        dates = pd.date_range("2020-01-01", periods=20, freq="D")
        df = pd.DataFrame({"date": dates, "x": range(20)})
        train, val, test = split_by_date(df, val_ratio=0.1, test_ratio=0.2)
        assert train["date"].max() < val["date"].min()
        assert val["date"].max() < test["date"].min()


# ──────────────────────────────────────────────
# walk_forward_splits
# ──────────────────────────────────────────────


class TestWalkForwardSplits:
    def _make_df(self, n_dates: int) -> pd.DataFrame:
        dates = pd.date_range("2020-01-01", periods=n_dates, freq="D")
        return pd.DataFrame({"date": dates, "x": range(n_dates)})

    def test_split_count(self):
        """n_splits 個の (train, test) ペアが返ること。"""
        df = self._make_df(30)
        splits = walk_forward_splits(df, n_splits=5)
        assert len(splits) == 5

    def test_no_future_leak(self):
        """各フォールドで train の最大日付 < test の最小日付であること。"""
        df = self._make_df(30)
        for train, test in walk_forward_splits(df, n_splits=5):
            assert train["date"].max() < test["date"].min()

    def test_expanding_window(self):
        """フォールドが進むにつれ学習データが単調増加すること（expanding window）。"""
        df = self._make_df(60)
        splits = walk_forward_splits(df, n_splits=5)
        train_sizes = [len(tr) for tr, _ in splits]
        assert train_sizes == sorted(train_sizes)
        assert len(set(train_sizes)) == len(train_sizes)  # 全フォールドで異なるサイズ

    def test_test_periods_non_overlapping(self):
        """各フォールドのテスト期間が重複しないこと。"""
        df = self._make_df(60)
        splits = walk_forward_splits(df, n_splits=5)
        test_dates = [set(test["date"].tolist()) for _, test in splits]
        for i in range(len(test_dates)):
            for j in range(i + 1, len(test_dates)):
                assert test_dates[i].isdisjoint(test_dates[j])

    def test_raises_if_too_few_dates(self):
        """日付数が n_splits + 1 未満の場合 ValueError が出ること。"""
        df = self._make_df(3)
        with pytest.raises(ValueError):
            walk_forward_splits(df, n_splits=5)

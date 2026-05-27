"""predictor.preprocessing の単体テスト."""

import pandas as pd
import pytest

from predictor.preprocessing import (
    _parse_finish_time,
    _parse_first_corner,
    compute_recent_stats,
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
# 共通フィクスチャ
# ──────────────────────────────────────────────


def _make_raw_df(n: int = 3) -> pd.DataFrame:
    """最小限のレースデータを作成する（preprocess テスト用）。"""
    return pd.DataFrame({
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
    })


def _make_multi_race_raw_df() -> pd.DataFrame:
    """複数馬・複数レースのデータを作成する（compute_recent_stats テスト用）。"""
    rows = []
    for race_num in range(5):
        for horse_idx in range(2):
            rows.append({
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
                "sire": "Sire",
                "dam": "Dam",
                "broodmare_sire": "BMS",
            })
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
        raw["prev_course_type"] = ["ダート", "芝"]  # idx0: ダート→芝(変化), idx1: 芝→芝(変化なし)
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
            "avg_finish_last3", "best_finish_last3", "avg_last3f_last3",
            "avg_finish_last5", "best_finish_last5", "avg_last3f_last5",
            "avg_corner_last3", "avg_corner_last5",
            "avg_finish_last3_cond", "best_finish_last3_cond", "avg_last3f_last3_cond",
            "avg_finish_last5_cond", "best_finish_last5_cond", "avg_last3f_last5_cond",
            "avg_corner_last3_cond", "avg_corner_last5_cond",
        ]
        for col in expected_cols:
            assert col in result.columns, f"{col} が結果に含まれていません"

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

    def test_course_type_change_different_course_is_one(self):
        """2走目のコースが前走と異なる場合、フラグは1であること。"""
        raw = _make_multi_race_raw_df()
        # H0 の R1 を ダート に変更（R0 は芝 → R1 はダート）
        raw.loc[(raw["horse_id"] == "H0") & (raw["race_id"] == "R1"), "course_type"] = "ダート"
        df = preprocess(raw)
        result = compute_recent_stats(df)
        h0_r1 = result[(result["horse_id"] == "H0") & (result["race_id"] == "R1")]
        assert h0_r1["course_type_change"].iloc[0] == pytest.approx(1.0)


# ──────────────────────────────────────────────
# split_by_date
# ──────────────────────────────────────────────


class TestSplitByDate:
    def test_split_ratio(self):
        dates = pd.date_range("2020-01-01", periods=10, freq="D")
        df = pd.DataFrame({"date": dates, "x": range(10)})
        train, test = split_by_date(df, test_ratio=0.2)
        assert len(test) == 2
        assert len(train) == 8

    def test_no_future_leak(self):
        """訓練データの最大日付 < テストデータの最小日付であること。"""
        dates = pd.date_range("2020-01-01", periods=10, freq="D")
        df = pd.DataFrame({"date": dates, "x": range(10)})
        train, test = split_by_date(df, test_ratio=0.2)
        assert train["date"].max() < test["date"].min()


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

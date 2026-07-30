"""predictor.model の単体テスト（時間減衰ウェイト統合まわり）。"""

import numpy as np
import pandas as pd

from predictor import model


def _make_synthetic_df() -> pd.DataFrame:
    """weight 統合テスト用の最小限のレースデータ（2レース×2頭）。"""
    return pd.DataFrame(
        {
            "race_id": ["R0", "R0", "R1", "R1"],
            "horse_number": [2, 1, 1, 2],
            "finishing_position": [2, 1, 1, 2],
            "is_placed": [1, 1, 1, 1],
            "venue": pd.Categorical(["東京", "東京", "阪神", "阪神"]),
            "distance": [1600.0, 1600.0, 2000.0, 2000.0],
            "date": pd.to_datetime(
                ["2024-01-01", "2024-01-01", "2024-06-01", "2024-06-01"]
            ),
        }
    )


class TestBuildDataset:
    def test_weight_passed_through(self):
        df = _make_synthetic_df()
        weight = np.array([0.5, 1.0, 0.25, 0.75])
        ds = model._build_dataset(df, "is_placed", weight=weight)
        ds.construct()
        np.testing.assert_allclose(ds.get_weight(), weight)

    def test_no_weight_defaults_to_none(self):
        df = _make_synthetic_df()
        ds = model._build_dataset(df, "is_placed")
        ds.construct()
        assert ds.get_weight() is None


class TestBuildRankDataset:
    def test_weight_reordered_to_match_sorted_rows(self):
        """weight は入力 df の行順で渡し、内部でソート後の順に並び替わること。"""
        df = _make_synthetic_df()
        # 元の行順: (R0,2) (R0,1) (R1,1) (R1,2)
        weight = np.array([10.0, 20.0, 30.0, 40.0])
        ds = model._build_rank_dataset(df, weight=weight)
        ds.construct()
        # ソート後の行順: (R0,1)->20 (R0,2)->10 (R1,1)->30 (R1,2)->40
        np.testing.assert_allclose(ds.get_weight(), [20.0, 10.0, 30.0, 40.0])

    def test_no_weight_defaults_to_none(self):
        df = _make_synthetic_df()
        ds = model._build_rank_dataset(df)
        ds.construct()
        assert ds.get_weight() is None


class TestTrainWithHalfLifeDays:
    def test_train_runs_without_half_life(self):
        """half_life_days=None（デフォルト）で従来どおり学習できること。"""
        df = _make_synthetic_df()
        models = model.train(df)
        assert models.win is not None
        assert models.place is not None

    def test_train_runs_with_half_life(self):
        """half_life_days 指定時も学習が成功すること。"""
        df = _make_synthetic_df()
        models = model.train(df, half_life_days=365)
        assert models.win is not None
        assert models.place is not None

    def test_train_accepts_param_overrides(self):
        """win_params / place_params でハイパーパラメータを上書きできること。"""
        df = _make_synthetic_df()
        models = model.train(
            df,
            win_params={"num_leaves": 7},
            place_params={"num_leaves": 7},
        )
        assert models.win.params["num_leaves"] == 7
        assert models.place.params["num_leaves"] == 7

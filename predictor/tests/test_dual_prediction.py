"""predictor.dual_prediction と、2パターン出力の単体テスト."""

import tomllib

import lightgbm as lgb
import numpy as np
import pandas as pd
import pytest

from predictor import dual_prediction, output


def _race_frame() -> pd.DataFrame:
    """2レース分の出走馬。R2 は単勝オッズが1頭欠けている。"""
    return pd.DataFrame(
        {
            "race_id": ["R1"] * 5 + ["R2"] * 4,
            "horse_number": ["1", "2", "3", "4", "5", "1", "2", "3", "4"],
            "x": [0.9, 0.5, 0.1, -0.3, -0.8, 0.2, 0.0, -0.1, 0.4],
            "win_odds": [2.0, 4.0, 8.0, 15.0, 30.0, 3.0, np.nan, 6.0, 5.0],
            "finishing_position": [np.nan] * 9,
        }
    )


def _booster() -> lgb.Booster:
    """特徴量 x が大きいほどスコアが高い、小さなブースター。"""
    rng = np.random.default_rng(0)
    x = rng.normal(size=500)
    data = lgb.Dataset(pd.DataFrame({"x": x}), label=x)
    return lgb.train(
        {"objective": "regression", "verbosity": -1, "min_data_in_leaf": 5},
        data,
        num_boost_round=20,
    )


class TestMarketWinProb:
    def test_normalized_and_nan_when_odds_missing(self):
        df = _race_frame()
        q = dual_prediction.market_win_prob(df, "win_odds")
        assert q[:5].sum() == pytest.approx(1.0)
        assert q[0] > q[4]
        assert np.isnan(q[5:]).all()


class TestTopTrios:
    def test_sorted_by_probability_with_ascending_horse_numbers(self):
        group = _race_frame().iloc[:5].assign(p=[0.4, 0.3, 0.15, 0.1, 0.05])
        trios = dual_prediction.top_trios(group, "p", 1.0, 1.0, n=3)
        assert trios[0][0] == [1, 2, 3]
        probs = [p for _, p in trios]
        assert probs == sorted(probs, reverse=True)
        assert all(hn == sorted(hn) for hn, _ in trios)


class TestAddDualProbabilities:
    def test_adds_both_patterns(self):
        target = _race_frame()
        pred = target[["race_id", "horse_number", "win_odds"]].assign(
            win_prob=0.2, place_prob=0.5, predicted_rank=1
        )
        out = dual_prediction.add_dual_probabilities(
            pred, target, _booster(), (0.8, 0.8)
        )
        by_race = out.groupby("race_id")
        np.testing.assert_allclose(by_race["win_prob"].sum(), 1.0)
        np.testing.assert_allclose(by_race["top3_prob"].sum(), 3.0)
        r1 = out[out["race_id"] == "R1"]
        assert r1["win_prob_odds"].sum() == pytest.approx(1.0)
        assert r1["top3_prob_odds"].sum() == pytest.approx(3.0)
        # x が最大の馬が PL 勝ちモデルで1位になる
        assert r1.loc[r1["win_prob"].idxmax(), "horse_number"] == "1"
        assert (r1["predicted_rank"] == r1["win_prob"].rank(ascending=False)).all()
        # オッズが欠けたレースはオッズありの確率を出さない
        assert out[out["race_id"] == "R2"]["win_prob_odds"].isna().all()


class TestBettingTomlTrioCandidates:
    def test_trio_candidates_are_written_and_parseable(self):
        target = _race_frame().iloc[:5]
        pred = target[["race_id", "horse_number", "win_odds"]].assign(
            win_prob=0.2, place_prob=0.5, predicted_rank=1
        )
        out = dual_prediction.add_dual_probabilities(
            pred, target, _booster(), (0.8, 0.8)
        )
        df = output._mark_recommended(out)
        parsed = tomllib.loads(output._format_betting_toml(df, (0.8, 0.8)))
        candidates = parsed["race"][0]["trio_candidates"]
        assert len(candidates["no_odds"]) == dual_prediction.TOP_TRIOS
        assert len(candidates["with_odds"]) == dual_prediction.TOP_TRIOS
        assert candidates["with_odds"][0]["horses"] == [1, 2, 3]

    def test_no_trio_candidates_without_discount(self):
        target = _race_frame().iloc[:5]
        pred = target[["race_id", "horse_number", "win_odds"]].assign(
            win_prob=[0.4, 0.3, 0.15, 0.1, 0.05], place_prob=0.5, predicted_rank=1
        )
        df = output._mark_recommended(pred)
        parsed = tomllib.loads(output._format_betting_toml(df))
        assert "trio_candidates" not in parsed["race"][0]


class TestSaveLoadPlBooster:
    def test_round_trip_keeps_predictions(self, tmp_path):
        """自作目的関数で学習したモデルをテキスト形式で保存・読込しても予測が変わらない。"""
        from predictor import pl_model

        rng = np.random.default_rng(1)
        rows = []
        for r in range(60):
            x = rng.normal(size=6)
            order = np.argsort(-(x + rng.normal(scale=0.5, size=6)))
            pos = np.empty(6)
            pos[order] = np.arange(1, 7)
            for h in range(6):
                rows.append(
                    {
                        "race_id": f"R{r}",
                        "horse_number": str(h + 1),
                        "x": x[h],
                        "finishing_position": pos[h],
                    }
                )
        df = pd.DataFrame(rows)
        layout = pl_model.RaceLayout.from_frame(df)
        booster = lgb.train(
            {
                "objective": pl_model.make_objective(layout, 3, None),
                "verbosity": -1,
                "min_data_in_leaf": 5,
            },
            lgb.Dataset(df[["x"]], label=df["finishing_position"]),
            num_boost_round=30,
        )
        dual_prediction.save_pl_win(booster, tmp_path)
        dual_prediction.save_market_discount(0.8, 0.9, tmp_path)
        loaded, discount = dual_prediction.load_dual_models(tmp_path)

        assert discount == (0.8, 0.9)
        np.testing.assert_allclose(
            pl_model.predict_win_prob(loaded, df),
            pl_model.predict_win_prob(booster, df),
        )
        # 特徴量 x が大きい馬ほど勝率が高く学習されている
        p = pl_model.predict_win_prob(loaded, df)
        assert np.corrcoef(df["x"], p)[0, 1] > 0.5

    def test_missing_files_return_none(self, tmp_path):
        assert dual_prediction.load_dual_models(tmp_path) is None


class TestModelVersion:
    def test_model_version_written_to_toml(self):
        target = _race_frame().iloc[:5]
        pred = target[["race_id", "horse_number", "win_odds"]].assign(
            win_prob=[0.4, 0.3, 0.15, 0.1, 0.05], place_prob=0.5, predicted_rank=1
        )
        df = output._mark_recommended(pred)
        parsed = tomllib.loads(
            output._format_betting_toml(df, model_version="20261017_152611")
        )
        assert parsed["model_version"] == "20261017_152611"

    def test_find_calibrated_model_dir_skips_dirs_without_calibration(self, tmp_path):
        from predictor import model

        (tmp_path / "20261017_100000").mkdir()
        for name in ("win_calibrated.pkl", "place_calibrated.pkl"):
            (tmp_path / "20261017_100000" / name).write_bytes(b"")
        # より新しいが較正済みファイルの無いディレクトリは選ばない
        (tmp_path / "20261017_120000").mkdir()
        assert model.find_calibrated_model_dir(tmp_path).name == "20261017_100000"
        assert model.latest_model_dir(tmp_path).name == "20261017_120000"

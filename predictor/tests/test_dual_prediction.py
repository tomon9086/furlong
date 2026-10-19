"""predictor.dual_prediction と、2パターン出力の単体テスト."""

import json
import tomllib
from itertools import combinations

import lightgbm as lgb
import numpy as np
import pandas as pd
import pytest

from predictor import dual_prediction, output
from predictor.dual_prediction import MarketParams

PARAMS = MarketParams(0.8, 0.8, 1.06)


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


def _trio_odds_r1() -> dict[str, float]:
    """R1（5頭）の全10組の三連複オッズ。4-5 を含む組ほど高い。"""
    return {
        "".join(f"{h:02d}" for h in c): 5.0 + 10.0 * (4 in c) + 20.0 * (5 in c)
        for c in combinations(range(1, 6), 3)
    }


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


def _pred(target: pd.DataFrame) -> pd.DataFrame:
    return target[["race_id", "horse_number", "win_odds"]].assign(
        win_prob=0.2, place_prob=0.5, predicted_rank=1
    )


class TestMarketWinProb:
    def test_normalized_and_nan_when_odds_missing(self):
        df = _race_frame()
        q = dual_prediction.market_win_prob(df, "win_odds")
        assert q[:5].sum() == pytest.approx(1.0)
        assert q[0] > q[4]
        assert np.isnan(q[5:]).all()


class TestTrioOddsFromPayload:
    def test_reads_trio_and_skips_unsold_and_flattened(self):
        payload = json.dumps(
            {
                "status": "middle",
                "data": {
                    "odds": {
                        "7": {
                            "1": ["11.3", "0.0", "1", "030712"],
                            "2": ["17.2", "0.0", "2", "010312"],
                            # 発売されなかった組は1要素にまとめて並ぶことがある
                            "3": [
                                "-3.0",
                                "0.0",
                                "9999",
                                "010203",
                                "0.0",
                                "0.0",
                                "9999",
                                "010204",
                            ],
                        }
                    }
                },
            }
        )
        assert dual_prediction.trio_odds_from_payload(payload) == {
            "030712": 11.3,
            "010312": 17.2,
        }

    def test_forecast_odds_are_ignored(self):
        payload = json.dumps(
            {
                "status": "yoso",
                "data": {"odds": {"7": {"1": ["9.9", "0", "1", "010203"]}}},
            }
        )
        assert dual_prediction.trio_odds_from_payload(payload) == {}


class TestAddDualProbabilities:
    def test_adds_both_patterns_using_trio_odds(self):
        target = _race_frame()
        out = dual_prediction.add_dual_probabilities(
            _pred(target), target, _booster(), PARAMS, {"R1": _trio_odds_r1()}
        )
        by_race = out.groupby("race_id")
        np.testing.assert_allclose(by_race["win_prob"].sum(), 1.0)
        np.testing.assert_allclose(by_race["top3_prob"].sum(), 3.0)
        r1 = out[out["race_id"] == "R1"]
        assert r1["win_prob_odds"].sum() == pytest.approx(1.0)
        assert r1["top3_prob_odds"].sum() == pytest.approx(3.0)
        # 三連複オッズでは 4・5番を含む組が高い（=確率が低い）ので、3着内率も低い
        top3 = r1.set_index("horse_number")["top3_prob_odds"]
        assert top3["5"] < top3["4"] < top3["1"]
        # x が最大の馬が PL 勝ちモデルで1位になる
        assert r1.loc[r1["win_prob"].idxmax(), "horse_number"] == "1"
        # オッズが欠けたレースはオッズありの確率を出さない
        assert out[out["race_id"] == "R2"]["win_prob_odds"].isna().all()

    def test_falls_back_to_win_odds_without_trio_odds(self):
        target = _race_frame().iloc[:5]
        out = dual_prediction.add_dual_probabilities(
            _pred(target), target, _booster(), PARAMS
        )
        assert out["top3_prob_odds"].sum() == pytest.approx(3.0)


class TestTrioCandidates:
    def test_sources_and_order(self):
        target = _race_frame().iloc[:5]
        out = dual_prediction.add_dual_probabilities(
            _pred(target), target, _booster(), PARAMS, {"R1": _trio_odds_r1()}
        )
        cands = dual_prediction.trio_candidates(out, PARAMS, _trio_odds_r1(), n=3)
        assert cands["オッズなし"]["source"] == "モデル"
        assert cands["オッズあり"]["source"] == "三連複オッズ"
        assert cands["オッズあり"]["combos"][0][0] == [1, 2, 3]
        probs = [p for _, p in cands["オッズなし"]["combos"]]
        assert probs == sorted(probs, reverse=True)

        fallback = dual_prediction.trio_candidates(out, PARAMS, None, n=3)
        assert fallback["オッズあり"]["source"] == "単勝オッズ+補正"
        assert fallback["オッズあり"]["combos"][0][0] == [1, 2, 3]


class TestBettingToml:
    def _df_and_candidates(self):
        target = _race_frame().iloc[:5]
        out = dual_prediction.add_dual_probabilities(
            _pred(target), target, _booster(), PARAMS, {"R1": _trio_odds_r1()}
        )
        cands = {"R1": dual_prediction.trio_candidates(out, PARAMS, _trio_odds_r1())}
        return output._mark_recommended(out), cands

    def test_trio_candidates_are_written_and_parseable(self):
        df, cands = self._df_and_candidates()
        parsed = tomllib.loads(output._format_betting_toml(df, cands))
        race = parsed["race"][0]["trio_candidates"]
        assert len(race["no_odds"]) == dual_prediction.TOP_TRIOS
        assert race["with_odds"][0]["horses"] == [1, 2, 3]
        assert race["with_odds_source"] == "三連複オッズ"
        assert race["no_odds_source"] == "モデル"

    def test_no_trio_candidates_without_candidates(self):
        df, _ = self._df_and_candidates()
        parsed = tomllib.loads(output._format_betting_toml(df))
        assert "trio_candidates" not in parsed["race"][0]

    def test_model_version_written_to_toml(self):
        df, _ = self._df_and_candidates()
        parsed = tomllib.loads(
            output._format_betting_toml(df, model_version="20261017_152611")
        )
        assert parsed["model_version"] == "20261017_152611"


class TestSaveLoad:
    def test_round_trip_keeps_predictions_and_params(self, tmp_path):
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
        dual_prediction.save_market_params(PARAMS, tmp_path)
        loaded, params = dual_prediction.load_dual_models(tmp_path)

        assert params == PARAMS
        np.testing.assert_allclose(
            pl_model.predict_win_prob(loaded, df),
            pl_model.predict_win_prob(booster, df),
        )

    def test_old_params_without_trio_alpha(self, tmp_path):
        """trio_alpha が無い（ADR-0037 以前の）モデルは三連複オッズを使わない。"""
        _booster().save_model(str(tmp_path / dual_prediction.PL_WIN_MODEL_FILE))
        (tmp_path / dual_prediction.MARKET_DISCOUNT_FILE).write_text(
            json.dumps({"lam2": 0.77, "lam3": 0.81})
        )
        _, params = dual_prediction.load_dual_models(tmp_path)
        assert params == MarketParams(0.77, 0.81, None)

        target = _race_frame().iloc[:5]
        out = dual_prediction.add_dual_probabilities(
            _pred(target), target, _booster(), params, {"R1": _trio_odds_r1()}
        )
        cands = dual_prediction.trio_candidates(out, params, _trio_odds_r1())
        assert cands["オッズあり"]["source"] == "単勝オッズ+補正"

    def test_missing_files_return_none(self, tmp_path):
        assert dual_prediction.load_dual_models(tmp_path) is None


class TestDualTable:
    def test_percent_and_market_rank(self):
        target = _race_frame().iloc[:5]
        pred = _pred(target).assign(horse_name="テスト")
        out = dual_prediction.add_dual_probabilities(pred, target, _booster(), PARAMS)
        text = output._format_dual_table(out.sort_values("predicted_rank"))
        lines = text.splitlines()
        assert "勝率[モデル]" in lines[0] and "3着内[市場]" in lines[0]
        assert "%" in lines[1]
        row = next(line for line in lines[1:] if line.split()[0] == "1")
        assert row.split()[3] == "1"

    def test_display_width_counts_fullwidth_as_two(self):
        assert output._display_width("エンネ") == 6
        assert output._display_width("ab") == 2


class TestFindCalibratedModelDir:
    def test_skips_dirs_without_calibration(self, tmp_path):
        from predictor import model

        (tmp_path / "20261017_100000").mkdir()
        for name in ("win_calibrated.pkl", "place_calibrated.pkl"):
            (tmp_path / "20261017_100000" / name).write_bytes(b"")
        (tmp_path / "20261017_120000").mkdir()
        assert model.find_calibrated_model_dir(tmp_path).name == "20261017_100000"
        assert model.latest_model_dir(tmp_path).name == "20261017_120000"

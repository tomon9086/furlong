"""predictor.trio_ev_experiment の単体テスト."""

import numpy as np
import pandas as pd
import pytest

from predictor import trio_ev_experiment as ev


def _table(race_id: str, actual: int, probs: list[float], odds: list[float]) -> dict:
    keys = ["010203", "010204", "020304"][: len(probs)]
    market = 1.0 / np.array(odds)
    return {
        "race_id": race_id,
        "現行": np.array(probs),
        "案A": np.array(probs),
        "案B": np.array(probs),
        "市場": market / market.sum(),
        "odds": np.array(odds),
        "keys": keys,
        "actual": actual,
    }


class TestEvReturns:
    def test_buys_combos_over_threshold_and_pays_actual(self):
        """EV>=閾値の組だけを買い、実際の組を買っていれば実配当を回収する。"""
        tables = [
            # EV: 0.5*3=1.5, 0.3*2=0.6, 0.2*10=2.0
            # -> 閾値1.0で2点、実際の組(010203)を的中
            _table("R1", 0, [0.5, 0.3, 0.2], [3.0, 2.0, 10.0]),
            # EV: 0.6, 1.2, 0.8 -> 閾値1.0で1点、実際の組(020304)は買っていない
            _table("R2", 2, [0.3, 0.4, 0.3], [2.0, 3.0, 2.7]),
        ]
        payoff_map = {"R1": {"1-2-3": 3.1}, "R2": {"2-3-4": 2.7}}
        result = ev._ev_returns(tables, payoff_map)
        stakes, returns = result[("現行", 1.0)]
        np.testing.assert_array_equal(stakes, [2, 1])
        np.testing.assert_array_equal(returns, [3.1, 0.0])

        stakes_15, _ = result[("現行", 1.5)]
        np.testing.assert_array_equal(stakes_15, [2, 0])


class TestBootstrapRecovery:
    def test_point_estimate_is_total_return_over_total_stake(self):
        ev_arrays = {
            ("現行", 1.0): (np.array([2.0, 1.0, 0.0]), np.array([3.1, 0.0, 0.0]))
        }
        df = ev._bootstrap_recovery(ev_arrays, n_bootstrap=200, random_state=0)
        row = df.iloc[0]
        assert row["recovery_rate"] == pytest.approx(3.1 / 3)
        assert row["races_bet"] == 2
        assert row["bets"] == 3
        assert row["ci_lower"] <= row["recovery_rate"] <= row["ci_upper"]


class TestCombinedNll:
    def test_alpha_one_beta_zero_equals_market(self):
        tables = [_table("R1", 1, [0.5, 0.3, 0.2], [3.0, 2.0, 10.0])]
        nll = ev._combined_nll(tables, "現行", 1.0, 0.0)
        assert nll[0] == pytest.approx(-np.log(tables[0]["市場"][1]))

    def test_edge_test_runs_and_reports_both_comparisons(self):
        rng = np.random.default_rng(0)
        tables, dates = [], {}
        for i in range(40):
            probs = rng.dirichlet(np.ones(3))
            odds = 0.75 / rng.dirichlet(np.ones(3))
            actual = int(rng.integers(0, 3))
            tables.append(_table(f"R{i}", actual, list(probs), list(odds)))
            dates[f"R{i}"] = pd.Timestamp("2025-01-01") + pd.Timedelta(days=i)
        df = ev._edge_test(tables, pd.Series(dates), n_bootstrap=100, random_state=0)
        assert set(df["compare"]) == {"モデル - 市場", "市場+モデル - 市場"}
        assert len(df) == 2 * len(ev.MODEL_METHODS)

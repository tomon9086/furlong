"""predictor.trio_market_experiment の単体テスト."""

from itertools import combinations

import numpy as np
import pandas as pd
import pytest

from predictor import trio_market_experiment as tm


def _race(race_id: str, positions: list[int], win_odds: list[float]):
    df = pd.DataFrame(
        {
            "race_id": race_id,
            "horse_number": [str(i + 1) for i in range(len(positions))],
            "finishing_position": positions,
            "odds": win_odds,
        }
    )
    rows = []
    for c in combinations(range(len(positions)), 3):
        key = "".join(f"{i + 1:02d}" for i in c)
        rows.append({"race_id": race_id, "combination": key, "odds": 10.0 + sum(c)})
    return df, pd.DataFrame(rows)


class TestRaceTables:
    def test_builds_table_and_actual_combo(self):
        df, odds = _race("R1", [3, 1, 5, 2, 4], [3.0, 2.0, 9.0, 5.0, 20.0])
        tables = tm.race_tables(df, odds)
        assert len(tables) == 1
        t = tables[0]
        assert set(t["combos"][t["actual"]].tolist()) == {0, 1, 3}
        assert t["win_q"].sum() == pytest.approx(1.0)

    def test_skips_race_with_missing_trio_odds(self):
        df, odds = _race("R1", [3, 1, 5, 2, 4], [3.0, 2.0, 9.0, 5.0, 20.0])
        tables = tm.race_tables(df, odds.iloc[1:])
        assert tables == []

    def test_methods_produce_distributions(self):
        df, odds = _race("R1", [3, 1, 5, 2, 4], [3.0, 2.0, 9.0, 5.0, 20.0])
        t = tm.race_tables(df, odds)[0]
        for probs in (tm._win_based(t, 0.8, 0.8), tm._trio_based(t, 1.2)):
            assert probs.sum() == pytest.approx(1.0)
            assert len(probs) == 10
        # 三連複オッズが低い組ほど確率が高い
        p = tm._trio_based(t, 1.0)
        assert np.argmax(p) == 0

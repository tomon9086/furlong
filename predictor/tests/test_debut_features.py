"""predictor.debut_features の単体テスト."""

import numpy as np
import pandas as pd
import pytest

from predictor import debut_features as dfeat


def _frame() -> pd.DataFrame:
    # 兄 A（母 M）が2回走って2回とも3着内、その後に妹 B（母 M）がデビュー
    return pd.DataFrame(
        {
            "race_id": ["R1", "R1", "R2", "R2", "R3", "R3"],
            "horse_id": ["A", "X", "A", "Y", "B", "Z"],
            "dam": ["M", "N", "M", "N", "M", "O"],
            "sire": ["S", "T", "S", "T", "S", "T"],
            "trainer_id": ["t1", "t2", "t1", "t2", "t1", "t2"],
            "date": pd.to_datetime(
                [
                    "2020-01-01",
                    "2020-01-01",
                    "2020-02-01",
                    "2020-02-01",
                    "2020-03-01",
                    "2020-03-01",
                ]
            ),
            "is_placed": [1, 0, 1, 0, 0, 1],
        }
    )


def test_dam_progeny_excludes_self_and_future():
    out = dfeat.add_debut_features(_frame()).set_index(["race_id", "horse_id"])
    # A の2戦目: 母 M の他の産駒はまだ走っていない（本人の1戦目は除く）
    assert out.loc[("R2", "A"), "dam_progeny_starts"] == 0
    # B のデビュー戦: 兄 A の2戦（2回とも3着内）が入る
    assert out.loc[("R3", "B"), "dam_progeny_starts"] == 2
    g = _frame()["is_placed"].mean()
    expected = (2 + dfeat.SHRINKAGE * g) / (2 + dfeat.SHRINKAGE)
    assert out.loc[("R3", "B"), "dam_progeny_place_rate"] == pytest.approx(expected)
    # 最初のレースの時点では誰の実績も無い
    assert (out.loc["R1", "dam_progeny_starts"] == 0).all()


def test_trainer_debut_rate_uses_only_previous_debuts():
    out = dfeat.add_debut_features(_frame()).set_index(["race_id", "horse_id"])
    r1 = out.loc[("R1", "A"), "trainer_debut_place_rate"]
    r3 = out.loc[("R3", "B"), "trainer_debut_place_rate"]
    # t1 の管理馬のデビュー戦は R1 の A（3着内）だけ → R3 の時点で率が上がっている
    assert r3 > r1
    assert not np.isnan(r1)

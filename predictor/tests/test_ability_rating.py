"""predictor.ability_rating の単体テスト."""

import numpy as np
import pandas as pd
import pytest

from predictor import ability_rating


def _full_order_nll(r_ordered: np.ndarray) -> float:
    nll = 0.0
    for k in range(len(r_ordered)):
        rest = r_ordered[k:]
        nll -= rest[0] - np.log(np.exp(rest).sum())
    return nll


def test_gradient_matches_numerical():
    r = np.array([0.3, -0.2, 0.8, 0.0, -0.5])
    grad = ability_rating._pl_full_order_grad(r)
    eps = 1e-6
    numerical = np.array(
        [
            -(_full_order_nll(r + eps * e) - _full_order_nll(r - eps * e)) / (2 * eps)
            for e in np.eye(len(r))
        ]
    )
    np.testing.assert_allclose(grad, numerical, atol=1e-6)


def test_ratings_use_only_past_races_and_reward_winners():
    df = pd.DataFrame(
        {
            "race_id": ["R1", "R1", "R1", "R2", "R2", "R2"],
            "horse_id": ["A", "B", "C", "A", "B", "D"],
            "date": pd.to_datetime(["2020-01-01"] * 3 + ["2020-02-01"] * 3),
            "finishing_position": [1, 2, 3, 3, 1, 2],
        }
    )
    out = ability_rating.compute_ability_ratings(df, lr=0.5)
    r1 = out[out["race_id"] == "R1"]
    # 最初のレースの前は全員 0（未来の結果が入っていない）
    assert (r1["ability_rating"] == 0).all()
    assert (r1["ability_rating_n"] == 0).all()
    r2 = out[out["race_id"] == "R2"].set_index("horse_id")
    # R1 の勝ち馬 A は B より高く、初出走の D は 0
    assert r2.loc["A", "ability_rating"] > r2.loc["B", "ability_rating"]
    assert r2.loc["A", "ability_rating"] > 0
    assert r2.loc["D", "ability_rating"] == 0
    assert r2.loc["A", "ability_rating_n"] == 1
    assert r2["ability_rating_rel"].sum() == pytest.approx(0.0)

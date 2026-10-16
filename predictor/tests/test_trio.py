"""predictor.trio の単体テスト."""

import numpy as np
import pytest

from predictor import simulation, trio


@pytest.fixture
def p() -> np.ndarray:
    return np.random.default_rng(0).dirichlet(np.ones(8))


class TestTrioSetProbabilities:
    def test_probabilities_sum_to_one(self, p: np.ndarray):
        combos, probs = trio.trio_set_probabilities(p, lam2=0.8, lam3=0.7)
        assert combos.shape == (56, 3)
        assert probs.sum() == pytest.approx(1.0)

    def test_matches_monte_carlo(self, p: np.ndarray):
        """ディスカウントなしなら simulation.py の Plackett-Luce MC と一致する。"""
        combos, probs = trio.trio_set_probabilities(p)
        orders = simulation.simulate_finishing_orders(
            p, n_iter=200_000, rng=np.random.default_rng(1)
        )
        mc = simulation.trifecta_box_probability(orders)
        mc_probs = np.array([mc[a, b, c] for a, b, c in combos])
        assert np.abs(mc_probs - probs).max() < 0.003

    def test_marginals_sum_to_three(self, p: np.ndarray):
        assert trio.top3_marginals(p, 0.9, 0.8).sum() == pytest.approx(3.0)


class TestActualTrioProbability:
    def test_matches_enumeration(self, p: np.ndarray):
        combos, probs = trio.trio_set_probabilities(p, 0.8, 0.7)
        target = (1, 4, 6)
        expected = probs[[tuple(c) for c in combos].index(target)]
        actual = trio.actual_trio_probability(
            [p / p.sum()], np.array([[6, 1, 4]]), 0.8, 0.7
        )
        assert actual[0] == pytest.approx(expected)


class TestStrengthsMatchingMarginals:
    def test_marginals_match_target(self, p: np.ndarray):
        target = np.array([0.8, 0.6, 0.5, 0.4, 0.3, 0.2, 0.1, 0.1])
        s = trio.strengths_matching_marginals(target, init=p, n_iter=50)
        np.testing.assert_allclose(trio.top3_marginals(s), target, atol=1e-3)


class TestFitDiscount:
    def test_recovers_discount_from_simulated_races(self):
        """ディスカウントありで生成した着順から lam2, lam3 をおおよそ推定できる。"""
        rng = np.random.default_rng(2)
        true_lam2, true_lam3 = 0.7, 0.6
        strengths, top3 = [], []
        for _ in range(3000):
            p = rng.dirichlet(np.full(12, 0.7))
            combos, probs = trio.trio_set_probabilities(p, true_lam2, true_lam3)
            combo = combos[rng.choice(len(combos), p=probs / probs.sum())]
            strengths.append(p)
            top3.append(combo)
        lam2, lam3 = trio.fit_discount(strengths, np.array(top3))
        # 三連複は順不同なので lam2 と lam3 は個別には識別しにくい。平均で確認する
        assert (lam2 + lam3) / 2 == pytest.approx((true_lam2 + true_lam3) / 2, abs=0.1)

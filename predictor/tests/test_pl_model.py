"""predictor.pl_model の単体テスト."""

import numpy as np
import pandas as pd
import pytest

from predictor import pl_model, trio


def _races(n_races: int, n_horses: int, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for r in range(n_races):
        order = rng.permutation(n_horses) + 1
        for h in range(n_horses):
            rows.append({"race_id": f"R{r:03d}", "finishing_position": order[h]})
    # 行順をレース単位で混ぜても添字が正しく扱えることを確認するためにシャッフル
    return pd.DataFrame(rows).sample(frac=1.0, random_state=seed).reset_index(drop=True)


class TestPlGradient:
    @pytest.mark.parametrize("top_k", [1, 3])
    def test_gradient_matches_numerical(self, top_k: int):
        df = _races(4, 6)
        layout = pl_model.RaceLayout.from_frame(df)
        rng = np.random.default_rng(1)
        preds = rng.normal(size=len(df))

        def total_nll(p: np.ndarray) -> float:
            _, _, nll = pl_model._pl_grad_hess_nll(layout, layout.to_matrix(p), top_k)
            return float(nll.sum())

        grad, _ = pl_model.make_objective(layout, top_k, None)(preds, None)
        eps = 1e-6
        numerical = np.array(
            [
                (total_nll(preds + eps * e) - total_nll(preds - eps * e)) / (2 * eps)
                for e in np.eye(len(df))
            ]
        )
        np.testing.assert_allclose(grad, numerical, atol=1e-5)

    def test_top3_nll_matches_trio_ordered_probability(self):
        """top_k=3 の -対数尤度は、1〜3着の順番どおりの Plackett-Luce 確率の -log。"""
        df = pd.DataFrame(
            {"race_id": ["R"] * 5, "finishing_position": [2, 1, 5, 3, 4]}
        )
        layout = pl_model.RaceLayout.from_frame(df)
        scores = np.log(np.array([0.3, 0.25, 0.2, 0.15, 0.1]))
        _, _, nll = pl_model._pl_grad_hess_nll(layout, layout.to_matrix(scores), 3)
        p = np.exp(scores) / np.exp(scores).sum()
        # 1着=行1, 2着=行0, 3着=行3
        expected = p[1] * p[0] / (1 - p[1]) * p[3] / (1 - p[1] - p[0])
        assert nll[0] == pytest.approx(-np.log(expected))
        # 参考: trio の順不同の確率は順番どおりの確率以上
        unordered = trio.actual_trio_probability([p], np.array([[1, 0, 3]]))
        assert unordered[0] >= expected


class TestPredictWinProb:
    def test_probabilities_sum_to_one_per_race(self):
        df = _races(3, 5)
        layout = pl_model.RaceLayout.from_frame(df)
        probs = pl_model._masked_softmax(
            layout.to_matrix(np.random.default_rng(2).normal(size=len(df))),
            layout.mask,
        )
        sums = layout.to_rows(probs, len(df))
        frame = df.assign(p=sums)
        np.testing.assert_allclose(frame.groupby("race_id")["p"].sum(), 1.0)

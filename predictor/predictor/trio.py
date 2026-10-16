"""三連複（3頭が1〜3着に入る組）の確率を Plackett-Luce で解析的に計算する。

``simulation.py`` のモンテカルロ（Gumbel max trick）と同じ Plackett-Luce を、
サンプリングせずに厳密に計算する。実際に来た組がサンプルに1回も出ないと
確率0になって対数尤度が計算できないため、評価には解析解を使う。

着順別ディスカウント（Benter/Henery 型）:
    1着は強さ p、2着は p**lam2、3着は p**lam3 に比例して残りの馬から選ぶ。
    lam2 = lam3 = 1 が通常の Plackett-Luce（Harville）。lam < 1 にすると
    2・3着の選択で強さの差が縮み、人気薄が2・3着に来る確率が上がる
    （逆に Harville が人気薄の2・3着を過大評価している場合は lam > 1 になる）。
"""

from __future__ import annotations

from itertools import combinations, permutations

import numpy as np
import pandas as pd
from scipy.optimize import minimize

_EPS = 1e-300

# 3頭の並べ方（1着, 2着, 3着）
_PERMS = list(permutations(range(3)))


def _normalize(p: np.ndarray) -> np.ndarray:
    p = np.clip(np.asarray(p, dtype=float), 0.0, None)
    total = p.sum()
    return p / total if total > 0 else np.full_like(p, 1.0 / len(p))


def trio_set_probabilities(
    p: np.ndarray, lam2: float = 1.0, lam3: float = 1.0
) -> tuple[np.ndarray, np.ndarray]:
    """1レース分の全三連複組の確率を返す。

    Parameters
    ----------
    p : np.ndarray, shape (n,)
        各馬の強さ（勝率）。内部で合計1に正規化する。
    lam2, lam3 : float
        2着・3着のディスカウント指数。

    Returns
    -------
    (combos, probs)
        combos: shape (m, 3) の馬インデックス（昇順）。probs: shape (m,)。
        n < 3 の場合は空配列。
    """
    p = _normalize(p)
    n = len(p)
    if n < 3:
        return np.empty((0, 3), dtype=int), np.empty(0)

    combos = np.array(list(combinations(range(n), 3)), dtype=int)
    s2 = p**lam2
    s3 = p**lam3
    total2 = s2.sum()
    total3 = s3.sum()

    probs = np.zeros(len(combos))
    for order in _PERMS:
        i = combos[:, order[0]]
        j = combos[:, order[1]]
        k = combos[:, order[2]]
        probs += (
            p[i]
            * s2[j] / np.maximum(total2 - s2[i], _EPS)
            * s3[k] / np.maximum(total3 - s3[i] - s3[j], _EPS)
        )
    return combos, probs


def top3_marginals(
    p: np.ndarray, lam2: float = 1.0, lam3: float = 1.0
) -> np.ndarray:
    """1レース分の各馬の3着内確率（三連複組の確率の周辺和）を返す。"""
    combos, probs = trio_set_probabilities(p, lam2, lam3)
    marg = np.zeros(len(p))
    for col in range(3):
        np.add.at(marg, combos[:, col], probs)
    return marg


def strengths_matching_marginals(
    target: np.ndarray, init: np.ndarray, n_iter: int = 30, step: float = 1.0
) -> np.ndarray:
    """Plackett-Luce の3着内確率が target に一致するよう、各馬の強さを反復調整する。

    target は合計3（3頭分）に正規化してから使う。乗法的に
    ``s <- s * (target / 現在の3着内確率) ** step`` を繰り返す。
    """
    target = np.clip(np.asarray(target, dtype=float), 1e-6, None)
    n = len(target)
    if n <= 3:
        return _normalize(init)
    target = target / target.sum() * 3.0
    target = np.clip(target, 1e-6, 1.0 - 1e-6)
    s = _normalize(np.clip(init, 1e-9, None))
    for _ in range(n_iter):
        marg = np.clip(top3_marginals(s), 1e-12, None)
        s = _normalize(s * (target / marg) ** step)
    return s


def actual_trio_probability(
    p_by_race: list[np.ndarray],
    top3_idx: np.ndarray,
    lam2: float = 1.0,
    lam3: float = 1.0,
) -> np.ndarray:
    """各レースで実際に1〜3着に来た3頭の組の確率を返す（全組を列挙せずに計算）。

    Parameters
    ----------
    p_by_race : list[np.ndarray]
        レースごとの各馬の強さ（合計1に正規化済みであること）。
    top3_idx : np.ndarray, shape (n_races, 3)
        各レースの1〜3着の馬インデックス（p_by_race 内の位置）。
    """
    n_races = len(p_by_race)
    p3 = np.empty((n_races, 3))
    total2 = np.empty(n_races)
    total3 = np.empty(n_races)
    for r, p in enumerate(p_by_race):
        p3[r] = p[top3_idx[r]]
        total2[r] = (p**lam2).sum()
        total3[r] = (p**lam3).sum()

    s2 = p3**lam2
    s3 = p3**lam3
    probs = np.zeros(n_races)
    for a, b, c in _PERMS:
        probs += (
            p3[:, a]
            * s2[:, b] / np.maximum(total2 - s2[:, a], _EPS)
            * s3[:, c] / np.maximum(total3 - s3[:, a] - s3[:, b], _EPS)
        )
    return probs


def fit_discount(
    p_by_race: list[np.ndarray], top3_idx: np.ndarray
) -> tuple[float, float]:
    """実際の三連複組の対数尤度を最大化する (lam2, lam3) を推定する。"""

    def nll(params: np.ndarray) -> float:
        probs = actual_trio_probability(p_by_race, top3_idx, params[0], params[1])
        return float(-np.log(np.clip(probs, _EPS, None)).mean())

    result = minimize(
        nll, x0=np.array([1.0, 1.0]), method="L-BFGS-B", bounds=[(0.2, 2.0)] * 2
    )
    return float(result.x[0]), float(result.x[1])


def race_arrays(
    test_df: pd.DataFrame, pred_df: pd.DataFrame, prob_cols: list[str]
) -> tuple[list[str], list[pd.DataFrame]]:
    """test_df と pred_df を結合し、1〜3着が確定している（同着なし）レースごとに分ける。

    Returns
    -------
    (race_ids, frames)
        frames の各要素は horse_number・finishing_position・odds・確率列を持つ
        1レース分の DataFrame（馬番順）。
    """
    merged = test_df[["race_id", "horse_number", "finishing_position", "odds"]].merge(
        pred_df[["race_id", "horse_number", *prob_cols]],
        on=["race_id", "horse_number"],
    )
    merged["odds"] = pd.to_numeric(merged["odds"], errors="coerce")
    merged["hn_int"] = pd.to_numeric(merged["horse_number"], errors="coerce")

    race_ids: list[str] = []
    frames: list[pd.DataFrame] = []
    for race_id, g in merged.groupby("race_id", sort=True):
        g = g.sort_values("hn_int").reset_index(drop=True)
        top3 = g[g["finishing_position"] <= 3]
        # 同着で3着内が3頭でないレースは三連複の組が1つに決まらないため除く
        positions = sorted(top3["finishing_position"])
        if len(g) < 4 or positions != [1, 2, 3]:
            continue
        race_ids.append(str(race_id))
        frames.append(g)
    return race_ids, frames

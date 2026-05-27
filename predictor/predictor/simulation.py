"""モンテカルロ着順シミュレーション

サンプリング方式: Plackett-Luce（Gumbel max trick）
  score_i = log(win_prob_i) + Gumbel(0,1)_i
  降順ソートで着順を決定する。
"""

from __future__ import annotations

import numpy as np

DEFAULT_N_ITER = 10_000


def simulate_finishing_orders(
    win_probs: np.ndarray,
    n_iter: int = DEFAULT_N_ITER,
    rng: np.random.Generator | None = None,
) -> np.ndarray:
    """Plackett-Luce（Gumbel max trick）で着順をシミュレートする。

    Parameters
    ----------
    win_probs : np.ndarray, shape (n_horses,)
        各馬の勝率（正規化済みでなくてもよい。内部で正規化する）。
    n_iter : int
        シミュレーション試行回数。デフォルト DEFAULT_N_ITER。
    rng : np.random.Generator or None
        乱数生成器。None の場合は再現性なしで新規生成する。
        再現性が必要な場合は ``np.random.default_rng(seed)`` を渡す。

    Returns
    -------
    np.ndarray, shape (n_iter, n_horses)
        ``orders[i, j]`` = i 回目のシミュレーションにおける j 番目の馬の着順（1始まり）。
    """
    win_probs = np.asarray(win_probs, dtype=np.float64)
    if win_probs.ndim != 1:
        raise ValueError("win_probs は 1 次元配列でなければなりません")
    if np.any(win_probs < 0):
        raise ValueError("win_probs に負の値が含まれています")

    total = win_probs.sum()
    if total <= 0:
        raise ValueError("win_probs の合計が 0 以下です")
    win_probs = win_probs / total

    if rng is None:
        rng = np.random.default_rng()

    n_horses = len(win_probs)
    log_probs = np.log(win_probs)  # shape (n_horses,)

    # Gumbel(0,1) サンプリング: -log(-log(U)), U ~ Uniform(0,1)
    # shape: (n_iter, n_horses)
    uniform = rng.uniform(0.0, 1.0, size=(n_iter, n_horses))
    gumbel = -np.log(-np.log(uniform))

    scores = log_probs + gumbel  # broadcast: (n_iter, n_horses)

    # scores の降順 argsort → 馬インデックスの着順配列
    # argsort は昇順なので [:, ::-1] で降順にし、1始まりの着順に変換
    sorted_idx = np.argsort(-scores, axis=1)  # shape (n_iter, n_horses)

    # orders[i, j] = j 番目の馬の i 回目の着順（1始まり）
    orders = np.empty_like(sorted_idx)
    rows = np.arange(n_iter)[:, np.newaxis]
    rank_positions = np.arange(1, n_horses + 1)[np.newaxis, :]  # shape (1, n_horses)
    orders[rows, sorted_idx] = rank_positions

    return orders


def win_probability(
    orders: np.ndarray,
) -> np.ndarray:
    """MC サンプルから単勝確率（1着になる確率）を算出する。

    Parameters
    ----------
    orders : np.ndarray, shape (n_iter, n_horses)
        ``simulate_finishing_orders`` の出力。

    Returns
    -------
    np.ndarray, shape (n_horses,)
        各馬の単勝確率（[0, 1]）。
    """
    return (orders == 1).mean(axis=0)


def place_probability(
    orders: np.ndarray,
    n_place: int = 3,
) -> np.ndarray:
    """MC サンプルから複勝確率（n_place 着以内に入る確率）を算出する。

    Parameters
    ----------
    orders : np.ndarray, shape (n_iter, n_horses)
        ``simulate_finishing_orders`` の出力。
    n_place : int
        複勝圏の着順数。デフォルト 3（3着以内）。

    Returns
    -------
    np.ndarray, shape (n_horses,)
        各馬の複勝確率（[0, 1]）。
    """
    return (orders <= n_place).mean(axis=0)

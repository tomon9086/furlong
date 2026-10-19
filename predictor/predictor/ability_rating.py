"""相手の強さを考慮した馬の能力レーティング。

多頭数の Elo（全着順の Plackett-Luce のオンライン更新）。

レースを日付順にたどり、各レースの全着順の Plackett-Luce 尤度が上がる方向に、
出走馬のレーティング r を学習率 lr で1回だけ勾配更新する。強い相手に先着すれば
大きく上がり、弱い相手に負ければ大きく下がる。初出走の馬は 0 から始まる。

全着順の Plackett-Luce の対数尤度の勾配は、着順で並べた e = exp(r) について
D_k = sum_{j>=k} e_j（k 着以下の馬の合計）とすると
    d logL / d r_(k) = 1 - e_(k) * sum_{m<=k} 1/D_m
と閉じた形で書ける（k は着順の位置）。

特徴量（いずれもそのレースの前の時点の値なので、未来の情報は入らない）:
    ability_rating     : レーティング
    ability_rating_rel : 同じレースの出走馬の平均との差
    ability_rating_n   : これまでに更新された回数（レーティングの当てになり具合）
"""

from __future__ import annotations

import numpy as np
import pandas as pd

RATING_COLUMNS = ["ability_rating", "ability_rating_rel", "ability_rating_n"]


def _pl_full_order_grad(r_ordered: np.ndarray) -> np.ndarray:
    """着順で並べたレーティングに対する、全着順の PL 対数尤度の勾配。"""
    shifted = r_ordered - r_ordered.max()
    e = np.exp(shifted)
    denom = np.cumsum(e[::-1])[::-1]
    return 1.0 - e * np.cumsum(1.0 / denom)


def compute_ability_ratings(df: pd.DataFrame, lr: float = 0.1) -> pd.DataFrame:
    """各行（1頭1レース）にレース前のレーティング特徴量を付けた DataFrame を返す。

    df は race_id・horse_id・date・finishing_position を含む（着順の決まった行）。
    同じ日のレースは race_id 順に処理する（同じ馬が同じ日に2回走ることはない）。
    """
    data = df[["race_id", "horse_id", "date", "finishing_position"]].copy()
    data["_row"] = np.arange(len(df))
    data = data.sort_values(["date", "race_id", "finishing_position"], kind="stable")

    horse_codes, _ = pd.factorize(data["horse_id"])
    ratings = np.zeros(horse_codes.max() + 1)
    counts = np.zeros(horse_codes.max() + 1)

    rows = data["_row"].to_numpy()
    out_rating = np.empty(len(df))
    out_rel = np.empty(len(df))
    out_n = np.empty(len(df))

    race_codes, _ = pd.factorize(data["race_id"], sort=False)
    boundaries = np.flatnonzero(np.diff(race_codes)) + 1
    for idx in np.split(np.arange(len(data)), boundaries):
        horses = horse_codes[idx]
        r = ratings[horses]
        out_rating[rows[idx]] = r
        out_rel[rows[idx]] = r - r.mean()
        out_n[rows[idx]] = counts[horses]
        if len(idx) >= 2:
            # data は着順で並んでいるので、そのまま全着順の勾配を取れる
            ratings[horses] = r + lr * _pl_full_order_grad(r)
            counts[horses] += 1

    out = df.copy()
    out["ability_rating"] = out_rating
    out["ability_rating_rel"] = out_rel
    out["ability_rating_n"] = out_n
    return out


def rating_only_win_nll(df: pd.DataFrame) -> float:
    """レーティングだけの勝率（レース内 softmax）での、勝ち馬の -log の平均。"""
    nll = []
    for _, g in df.groupby("race_id", sort=False):
        r = g["ability_rating"].to_numpy()
        is_win = g["finishing_position"].to_numpy() == 1
        if is_win.sum() != 1:
            continue
        log_p = r - r.max() - np.log(np.exp(r - r.max()).sum())
        nll.append(-log_p[is_win][0])
    return float(np.mean(nll))

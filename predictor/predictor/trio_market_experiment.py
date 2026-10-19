"""「オッズあり」の三連複確率の作り方の比較実験。

predict の「オッズあり」の三連複確率は、単勝オッズから逆算した市場の勝率に
2・3着の着順別ディスカウントをかけた Plackett-Luce で作っている（dual_prediction.py）。
三連複の確定オッズ（final_odds、bet_type=7）がそろったので、三連複オッズから
直接逆算した確率の方が実際の組をよく当てるかを確かめる。

比較する三連複確率（全方法で同じレース集合）:
    A: 単勝オッズ + ディスカウント（現行の「オッズあり」。lam2, lam3 は較正期間で推定）
    B: 三連複オッズ（1/オッズ をレース内の全組で正規化）
    C: 三連複オッズ + べき補正（B を q**alpha にして正規化。alpha は較正期間で推定）

評価: テスト期間の三連複対数尤度と、各方法の三連複確率から出した3着内率の logloss。
A との差をレース単位ペアード bootstrap で検定する。

注意: どちらも締切後の確定オッズ。predict では発走前のオッズを使う。
"""

from __future__ import annotations

import logging
from datetime import datetime
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize_scalar

from predictor import trio
from predictor.preprocessing import split_by_date

logger = logging.getLogger(__name__)

_OUTPUT_DIR = Path(__file__).parent.parent.parent / "output"
METHODS = ["A: 単勝+補正", "B: 三連複", "C: 三連複+べき補正"]


def _race_tables(df: pd.DataFrame, trio_odds: pd.DataFrame) -> list[dict]:
    """全馬の単勝オッズと全組の三連複オッズがそろい、同着なしのレースをまとめる。"""
    odds_by_race = {
        rid: dict(zip(g["combination"], g["odds"], strict=True))
        for rid, g in trio_odds.groupby("race_id")
    }
    tables = []
    for race_id, g in df.groupby("race_id", sort=False):
        race_odds = odds_by_race.get(race_id)
        if race_odds is None or len(g) < 4:
            continue
        win_odds = pd.to_numeric(g["odds"], errors="coerce").to_numpy()
        positions = g["finishing_position"].to_numpy()
        if not (win_odds > 0).all():
            continue
        if sorted(positions[positions <= 3].tolist()) != [1, 2, 3]:
            continue
        horse_numbers = pd.to_numeric(g["horse_number"]).to_numpy(dtype=int)
        combos = np.array(list(combinations(range(len(g)), 3)))
        keys = [
            "".join(f"{h:02d}" for h in sorted(horse_numbers[c])) for c in combos
        ]
        trio_values = np.array([race_odds.get(k, np.nan) for k in keys])
        # 0倍（発売されなかった組）も欠けとして扱う
        if np.isnan(trio_values).any() or (trio_values <= 0).any():
            continue
        top3 = set(np.argsort(positions, kind="stable")[:3].tolist())
        actual = next(i for i, c in enumerate(combos) if set(c.tolist()) == top3)
        win_q = (1.0 / win_odds) / (1.0 / win_odds).sum()
        tables.append(
            {
                "race_id": race_id,
                "combos": combos,
                "placed": (positions <= 3).astype(float),
                "win_q": win_q,
                "trio_inv": 1.0 / trio_values,
                "actual": actual,
            }
        )
    return tables


def _win_based(t: dict, lam2: float, lam3: float) -> np.ndarray:
    # trio_set_probabilities は combinations と同じ順で組を返す
    _, probs = trio.trio_set_probabilities(t["win_q"], lam2, lam3)
    return probs


def _trio_based(t: dict, alpha: float) -> np.ndarray:
    q = t["trio_inv"] ** alpha
    return q / q.sum()


def _nll(probs: np.ndarray, actual: int) -> float:
    return -float(np.log(max(probs[actual], 1e-300)))


def _place_nll(t: dict, probs: np.ndarray) -> float:
    marg = np.zeros(len(t["placed"]))
    for col in range(3):
        np.add.at(marg, t["combos"][:, col], probs)
    marg = np.clip(marg, 1e-12, 1 - 1e-12)
    placed = t["placed"]
    return float(-(placed * np.log(marg) + (1 - placed) * np.log(1 - marg)).mean())


def _fit_alpha(tables: list[dict]) -> float:
    def objective(alpha: float) -> float:
        nll = [_nll(_trio_based(t, alpha), t["actual"]) for t in tables]
        return float(np.mean(nll))

    return float(minimize_scalar(objective, bounds=(0.5, 2.0), method="bounded").x)


def run(
    df: pd.DataFrame,
    trio_odds_loader,
    n_bootstrap: int = 2000,
    random_state: int | None = 42,
) -> dict[str, pd.DataFrame]:
    """較正期間で lam・alpha を推定し、テスト期間で A・B・C を比べる。

    Parameters
    ----------
    df : pd.DataFrame
        ``preprocess()`` 済みの JRA データ（race_id, horse_number, odds,
        finishing_position, date を含む）。特徴量は使わない。
    trio_odds_loader : Callable[[list[str]], pd.DataFrame]
        race_id のリストから三連複の確定オッズを読み込む関数。
    """
    _, val_df, test_df = split_by_date(df)
    parts = {}
    for name, part in (("val", val_df), ("test", test_df)):
        race_ids = part["race_id"].unique().tolist()
        parts[name] = _race_tables(part, trio_odds_loader(race_ids))
        logger.info(f"{name}: {len(parts[name]):,}レース（全オッズあり・同着なし）")

    val = parts["val"]
    lam = trio.fit_discount(
        [t["win_q"] for t in val],
        np.array([t["combos"][t["actual"]] for t in val]),
    )
    alpha = _fit_alpha(val)
    logger.info(
        f"較正期間で推定: lam2={lam[0]:.3f} lam3={lam[1]:.3f} / alpha={alpha:.3f}"
    )

    test = parts["test"]
    per_race = {m: {"trio_nll": [], "place_nll": []} for m in METHODS}
    for t in test:
        for m, probs in (
            (METHODS[0], _win_based(t, *lam)),
            (METHODS[1], _trio_based(t, 1.0)),
            (METHODS[2], _trio_based(t, alpha)),
        ):
            per_race[m]["trio_nll"].append(_nll(probs, t["actual"]))
            per_race[m]["place_nll"].append(_place_nll(t, probs))

    rng = np.random.default_rng(random_state)
    rows = []
    base = METHODS[0]
    for m in METHODS:
        for metric in ("trio_nll", "place_nll"):
            values = np.array(per_race[m][metric])
            diff = values - np.array(per_race[base][metric])
            boot = np.array(
                [
                    diff[rng.integers(0, len(diff), size=len(diff))].mean()
                    for _ in range(n_bootstrap)
                ]
            )
            lo, hi = np.percentile(boot, [2.5, 97.5])
            rows.append(
                {
                    "method": m,
                    "metric": metric,
                    "value": float(values.mean()),
                    "diff_vs_A": float(diff.mean()),
                    "diff_ci_lower": float(lo),
                    "diff_ci_upper": float(hi),
                    "diff_significant": m != base and not (lo <= 0 <= hi),
                }
            )
    params = pd.DataFrame(
        [{"lam2": lam[0], "lam3": lam[1], "alpha": alpha, "test_races": len(test)}]
    )
    return {"summary": pd.DataFrame(rows), "params": params}


def save_results(
    results: dict[str, pd.DataFrame], output_dir: Path = _OUTPUT_DIR
) -> list[Path]:
    """結果を CSV に保存し、保存先パスを返す。"""
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    paths = []
    for name, frame in results.items():
        path = output_dir / f"trio_market_{name}_{timestamp}.csv"
        frame.to_csv(path, index=False)
        paths.append(path)
    return paths

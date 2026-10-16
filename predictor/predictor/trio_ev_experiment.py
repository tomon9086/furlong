"""三連複 EV のゲート判定（docs/plan/trio-probability.md のフェーズ3）。

三連複の確定オッズ（final_odds、bet_type=7）を取得済みのテスト期間のレースで、
次を測る。

1. EV ルールの回収率: EV = モデルの三連複確率 × 確定オッズ が閾値以上の組を
   1点ずつ全部買ったときの回収率。回収額は payoffs の実配当で計算する。
2. モデル vs 市場: 実際に来た組の対数尤度を、モデルの確率と、三連複オッズから
   逆算した市場の確率（1/オッズ をレース内で合計1に正規化）で比べる。
3. 市場＋モデル: ``市場**alpha × モデル**beta`` を正規化した確率が市場単独より
   良いか（モデルが市場の持っていない情報を持っているか）。alpha・beta は
   レースを日付順に前半・後半に分けた2分割の交差検証で推定・評価する。

注意:
    - 確定オッズは締切後の最終オッズで、実際に買うときの発走前オッズより
      有利な条件になる（単勝の評価と同じ前提）。
    - 同着で1〜3着が決まらないレースは評価から除く（``trio.race_arrays``）。
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from predictor import trio
from predictor.trio_baseline_experiment import (
    _top3_idx,
    _trio_payoff_map,
    build_methods,
)

logger = logging.getLogger(__name__)

_OUTPUT_DIR = Path(__file__).parent.parent.parent / "output"

EV_THRESHOLDS = [1.0, 1.2, 1.5]
# EV 判定に使うモデル側の方法（市場系の方法はオッズそのものなので除く）
MODEL_METHODS = ["現行", "案A", "案B"]


def _combo_keys(horse_numbers: np.ndarray, combos: np.ndarray) -> list[str]:
    """馬インデックスの組を final_odds の combination 形式（'010307'）にする。"""
    return ["".join(f"{h:02d}" for h in sorted(horse_numbers[c])) for c in combos]


def _race_tables(
    race_ids: list[str],
    frames: list[pd.DataFrame],
    methods: dict,
    odds_df: pd.DataFrame,
) -> list[dict]:
    """レースごとに、オッズのある組について各方法の確率・市場の確率をまとめる。"""
    odds_by_race = {
        rid: dict(zip(g["combination"], g["odds"], strict=True))
        for rid, g in odds_df.groupby("race_id")
    }
    top3_idx = _top3_idx(frames)

    tables = []
    for r, (race_id, g) in enumerate(zip(race_ids, frames, strict=True)):
        horse_numbers = g["hn_int"].to_numpy(dtype=int)
        race_odds = odds_by_race.get(race_id, {})
        actual_key = "".join(f"{h:02d}" for h in sorted(horse_numbers[top3_idx[r]]))

        table = {"race_id": race_id}
        keys = None
        for name in MODEL_METHODS:
            strengths, lam2, lam3 = methods[name]
            combos, probs = trio.trio_set_probabilities(strengths[r], lam2, lam3)
            if keys is None:
                keys = _combo_keys(horse_numbers, combos)
                has_odds = np.array([k in race_odds for k in keys])
                odds = np.array([race_odds.get(k, np.nan) for k in keys])[has_odds]
                kept_keys = [k for k, h in zip(keys, has_odds, strict=True) if h]
            table[name] = probs[has_odds]
        if keys is None or len(kept_keys) == 0 or actual_key not in kept_keys:
            continue
        market = 1.0 / odds
        table["市場"] = market / market.sum()
        table["odds"] = odds
        table["keys"] = kept_keys
        table["actual"] = kept_keys.index(actual_key)
        tables.append(table)
    return tables


def _ev_returns(
    tables: list[dict], payoff_map: dict[str, dict[str, float]]
) -> dict[tuple[str, float], tuple[np.ndarray, np.ndarray]]:
    """方法 × 閾値ごとに、レースごとの (賭け点数, 回収額) の配列を返す。"""
    out = {}
    for name in MODEL_METHODS:
        for threshold in EV_THRESHOLDS:
            stakes = np.zeros(len(tables))
            returns = np.zeros(len(tables))
            for r, t in enumerate(tables):
                bets = t[name] * t["odds"] >= threshold
                stakes[r] = bets.sum()
                if bets[t["actual"]]:
                    key = t["keys"][t["actual"]]
                    payout_key = "-".join(
                        str(int(key[i : i + 2])) for i in range(0, 6, 2)
                    )
                    returns[r] = payoff_map.get(t["race_id"], {}).get(payout_key, 0.0)
            out[(name, threshold)] = (stakes, returns)
    return out


def _bootstrap_recovery(
    ev: dict[tuple[str, float], tuple[np.ndarray, np.ndarray]],
    n_bootstrap: int,
    random_state: int | None,
) -> pd.DataFrame:
    """回収率（総回収額 / 総賭け点数）のレース単位 bootstrap 95%CI。"""
    n_races = len(next(iter(ev.values()))[0])
    rng = np.random.default_rng(random_state)
    boot = {k: np.empty(n_bootstrap) for k in ev}
    chunk = 500
    for start in range(0, n_bootstrap, chunk):
        size = min(chunk, n_bootstrap - start)
        idx = rng.integers(0, n_races, size=(size, n_races), dtype=np.int32)
        for k, (stakes, returns) in ev.items():
            total = stakes[idx].sum(axis=1)
            boot[k][start : start + size] = np.where(
                total > 0, returns[idx].sum(axis=1) / np.maximum(total, 1), np.nan
            )

    rows = []
    for (name, threshold), (stakes, returns) in ev.items():
        lo, hi = np.nanpercentile(boot[(name, threshold)], [2.5, 97.5])
        rows.append(
            {
                "method": name,
                "ev_threshold": threshold,
                "races_bet": int((stakes > 0).sum()),
                "bets": int(stakes.sum()),
                "hits": int((returns > 0).sum()),
                "recovery_rate": float(returns.sum() / max(stakes.sum(), 1)),
                "ci_lower": float(lo),
                "ci_upper": float(hi),
                "significant_over_100": bool(lo > 1.0),
            }
        )
    return pd.DataFrame(rows)


def _combined_nll(
    tables: list[dict], name: str, alpha: float, beta: float
) -> np.ndarray:
    """``市場**alpha × モデル**beta`` を正規化した確率での、実際の組の -log。"""
    out = np.empty(len(tables))
    for r, t in enumerate(tables):
        logit = alpha * np.log(np.clip(t["市場"], 1e-300, None)) + beta * np.log(
            np.clip(t[name], 1e-300, None)
        )
        logit -= logit.max()
        out[r] = -(logit[t["actual"]] - np.log(np.exp(logit).sum()))
    return out


def _edge_test(
    tables: list[dict],
    dates: pd.Series,
    n_bootstrap: int,
    random_state: int | None,
) -> pd.DataFrame:
    """モデル vs 市場、市場＋モデル vs 市場の対数尤度をペアード bootstrap で比べる。"""
    race_dates = np.array([dates.get(t["race_id"]) for t in tables])
    order = np.argsort(race_dates, kind="stable")
    half = len(tables) // 2
    folds = [order[:half], order[half:]]

    market_nll = np.array(
        [-np.log(max(t["市場"][t["actual"]], 1e-300)) for t in tables]
    )
    rng = np.random.default_rng(random_state)
    rows = []
    for name in MODEL_METHODS:
        model_nll = np.array(
            [-np.log(max(t[name][t["actual"]], 1e-300)) for t in tables]
        )
        combined_nll = np.empty(len(tables))
        params = []
        # 前半で推定 -> 後半で評価、後半で推定 -> 前半で評価
        for fit_idx, eval_idx in ((folds[0], folds[1]), (folds[1], folds[0])):
            fit_tables = [tables[i] for i in fit_idx]

            def objective(x: np.ndarray, fit_tables=fit_tables) -> float:
                return float(_combined_nll(fit_tables, name, x[0], x[1]).mean())

            res = minimize(
                objective,
                x0=np.array([1.0, 0.0]),
                method="L-BFGS-B",
                bounds=[(0.0, 3.0), (-1.0, 3.0)],
            )
            params.append(res.x)
            eval_tables = [tables[i] for i in eval_idx]
            combined_nll[eval_idx] = _combined_nll(eval_tables, name, *res.x)

        for label, nll in (("モデル", model_nll), ("市場+モデル", combined_nll)):
            diff = nll - market_nll
            boot = np.empty(n_bootstrap)
            for i in range(n_bootstrap):
                idx = rng.integers(0, len(diff), size=len(diff))
                boot[i] = diff[idx].mean()
            lo, hi = np.percentile(boot, [2.5, 97.5])
            rows.append(
                {
                    "method": name,
                    "compare": f"{label} - 市場",
                    "market_nll": float(market_nll.mean()),
                    "nll": float(nll.mean()),
                    "diff": float(diff.mean()),
                    "ci_lower": float(lo),
                    "ci_upper": float(hi),
                    # 負なら市場より良い（実際の組により高い確率を付けている）
                    "significant_better_than_market": bool(hi < 0),
                    "alpha_beta": (
                        "; ".join(f"a={a:.3f} b={b:.3f}" for a, b in params)
                        if label == "市場+モデル"
                        else ""
                    ),
                }
            )
    return pd.DataFrame(rows)


def run(
    df: pd.DataFrame,
    payoffs_loader,
    trio_odds_loader,
    half_life_days: float | None = 1095.0,
    n_bootstrap: int = 10_000,
    random_state: int | None = 42,
) -> dict[str, pd.DataFrame]:
    """三連複オッズ取得済みのテスト期間レースで、EV ルールの回収率とエッジの有無を測る。

    Parameters
    ----------
    payoffs_loader, trio_odds_loader : Callable[[list[str]], pd.DataFrame]
        race_id のリストから払戻・三連複の確定オッズを読み込む関数。
    """
    odds_cache: dict[str, pd.DataFrame] = {}

    def has_trio_odds(race_ids: list[str]) -> set[str]:
        odds_cache["df"] = trio_odds_loader(race_ids)
        return set(odds_cache["df"]["race_id"].unique())

    built = build_methods(df, half_life_days, race_filter=has_trio_odds)
    race_ids, frames = built["race_ids"], built["frames"]
    if not race_ids:
        raise ValueError("三連複の確定オッズを取得済みのテスト期間レースがありません")

    tables = _race_tables(race_ids, frames, built["methods"], odds_cache["df"])
    dates = built["dates"]
    logger.info(
        f"EV 判定の対象: {len(tables):,}レース"
        f"（{min(dates[t['race_id']] for t in tables).date()}〜"
        f"{max(dates[t['race_id']] for t in tables).date()}）"
    )
    payoff_map = _trio_payoff_map(payoffs_loader([t["race_id"] for t in tables]))

    recovery = _bootstrap_recovery(
        _ev_returns(tables, payoff_map), n_bootstrap, random_state
    )
    edge = _edge_test(tables, dates, min(n_bootstrap, 2000), random_state)
    return {"recovery": recovery, "edge": edge, "discount": built["discount"]}


def save_results(
    results: dict[str, pd.DataFrame], output_dir: Path = _OUTPUT_DIR
) -> list[Path]:
    """結果を CSV に保存し、保存先パスを返す。"""
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    paths = []
    for name, frame in results.items():
        path = output_dir / f"trio_ev_{name}_{timestamp}.csv"
        frame.to_csv(path, index=False)
        paths.append(path)
    return paths

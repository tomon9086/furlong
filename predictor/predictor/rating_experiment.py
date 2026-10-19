"""馬の能力レーティング（ability_rating.py）を特徴量に足す効果の検定。

gap-analysis で、モデルは市場にほぼ全区切りで均等に負けており、人気馬の過小評価も
大きいと分かった（相手の強さを考慮した能力の見積もりが弱い）。そこで、全着順の
Plackett-Luce をオンライン更新する多頭数 Elo のレーティングを特徴量に足し、
オッズなしのモデル（P3、ADR-0036）が良くなるかを調べる。

- 学習率 lr は候補の中から、較正期間で「レーティングだけで勝率を出したとき」の
  対数尤度が最も良いものを選ぶ（テスト期間は見ない）。
- レーティングは全 JRA レースを日付順にたどって作り、各レースの前の値だけを使う。
- P3（レーティングなし）と P3+レーティングを同じ条件で学習し、テスト期間の
  勝率・三連複・3着内率の対数尤度をレース単位ペアード bootstrap で比べる。
  参考に市場（単勝オッズ）の値と、市場との差がどれだけ縮んだかも出す。
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from predictor import ability_rating, pl_model
from predictor.market_residual_experiment import _complete_races, _market_log_prob
from predictor.preprocessing import (
    compute_recent_stats,
    compute_time_decay_weight,
    split_by_date,
)
from predictor.sharpness_experiment import _race_groups, _trio_and_place, _win_nll

logger = logging.getLogger(__name__)

_OUTPUT_DIR = Path(__file__).parent.parent.parent / "output"
LR_CANDIDATES = [0.05, 0.1, 0.2, 0.4]


def run(
    df: pd.DataFrame,
    half_life_days: float | None = 1095.0,
    n_bootstrap: int = 2000,
    random_state: int | None = 42,
) -> dict[str, pd.DataFrame]:
    featured = compute_recent_stats(df)
    _, val_all, _ = split_by_date(featured)
    val_start, val_end = val_all["date"].min(), val_all["date"].max()

    lr_rows = []
    for lr in LR_CANDIDATES:
        rated = ability_rating.compute_ability_ratings(featured, lr=lr)
        in_val = (rated["date"] >= val_start) & (rated["date"] <= val_end)
        nll = ability_rating.rating_only_win_nll(rated[in_val])
        lr_rows.append({"lr": lr, "val_rating_only_win_nll": nll})
        logger.info(f"lr={lr}: 較正期間のレーティングだけの勝率の対数尤度 {nll:.4f}")
    lr_table = pd.DataFrame(lr_rows)
    best_lr = float(lr_table.loc[lr_table["val_rating_only_win_nll"].idxmin(), "lr"])
    logger.info(f"採用する学習率: lr={best_lr}")

    rated = ability_rating.compute_ability_ratings(featured, lr=best_lr)
    rated = _complete_races(rated)
    train_df, val_df, test_df = split_by_date(rated)
    weight = (
        compute_time_decay_weight(
            train_df["date"], train_df["date"].max(), half_life_days
        )
        if half_life_days is not None
        else None
    )

    test = test_df.sort_values(["race_id", "horse_number"]).reset_index(drop=True)
    variants = (("P3", None), ("P3+レーティング", ability_rating.RATING_COLUMNS))
    for name, extra in variants:
        logger.info(f"{name} を学習中...")
        booster = pl_model.train_pl(
            train_df, val_df, top_k=3, weight=weight, extra_features=extra
        )
        test[name] = pl_model.predict_win_prob(booster, test)
        logger.info(f"{name}: 木の本数 {booster.best_iteration}")
    test["市場"] = np.exp(_market_log_prob(test))

    groups = _race_groups(test)
    is_win = test["is_win"].to_numpy()
    per_race = {}
    for m in ("P3", "P3+レーティング", "市場"):
        trio_nll, place_nll, _ = _trio_and_place(test, m, groups)
        per_race[m] = {
            "win_nll": _win_nll(test[m].to_numpy(), is_win, groups),
            "trio_nll": trio_nll,
            "place_nll": place_nll,
        }

    rng = np.random.default_rng(random_state)
    rows = []
    for metric in ("win_nll", "trio_nll", "place_nll"):
        base = per_race["P3"][metric]
        new = per_race["P3+レーティング"][metric]
        market = per_race["市場"][metric]
        valid = ~np.isnan(base) & ~np.isnan(new)
        diff = (new - base)[valid]
        boot = np.array(
            [
                diff[rng.integers(0, len(diff), size=len(diff))].mean()
                for _ in range(n_bootstrap)
            ]
        )
        lo, hi = np.percentile(boot, [2.5, 97.5])
        gap_before = np.nanmean(base) - np.nanmean(market)
        rows.append(
            {
                "metric": metric,
                "P3": float(np.nanmean(base)),
                "P3+レーティング": float(np.nanmean(new)),
                "市場": float(np.nanmean(market)),
                "diff": float(diff.mean()),
                "diff_ci_lower": float(lo),
                "diff_ci_upper": float(hi),
                "diff_significant": not (lo <= 0 <= hi),
                "市場との差の縮小率": float(-diff.mean() / gap_before)
                if gap_before > 0
                else float("nan"),
            }
        )
    logger.info(f"評価対象: テスト期間 {len(groups):,}レース")
    return {"summary": pd.DataFrame(rows), "lr": lr_table}


def save_results(
    results: dict[str, pd.DataFrame], output_dir: Path = _OUTPUT_DIR
) -> list[Path]:
    """結果を CSV に保存し、保存先パスを返す。"""
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    paths = []
    for name, frame in results.items():
        path = output_dir / f"rating_{name}_{timestamp}.csv"
        frame.to_csv(path, index=False)
        paths.append(path)
    return paths

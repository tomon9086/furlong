"""初出走・キャリアの浅い馬向けの特徴量（debut_features.py）を足す効果の検定。

P3（ADR-0036）と P3+初出走向け特徴量を同じ条件で学習し、テスト期間で比べる。
全体に加えて、狙いの新馬戦（レース単位）と初出走の馬（馬単位の3着内率）に絞った
差も、レース単位ペアード bootstrap で出す。
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from predictor import debut_features, pl_model, trio
from predictor.market_residual_experiment import _complete_races, _market_log_prob
from predictor.preprocessing import (
    compute_recent_stats,
    compute_time_decay_weight,
    split_by_date,
)

logger = logging.getLogger(__name__)

_OUTPUT_DIR = Path(__file__).parent.parent.parent / "output"
METHODS = ["P3", "P3+初出走向け", "市場"]


def _per_race_and_horse(test: pd.DataFrame, col: str) -> tuple[pd.Series, np.ndarray]:
    """レースごとの勝ち馬の -log と、馬ごとの3着内率の logloss。"""
    win_nll = {}
    place_nll = np.empty(len(test))
    for race_id, idx in test.groupby("race_id", sort=False).indices.items():
        p = test[col].to_numpy()[idx]
        p = p / p.sum()
        is_win = test["is_win"].to_numpy()[idx] == 1
        if is_win.sum() == 1:
            win_nll[race_id] = -np.log(max(p[is_win][0], 1e-300))
        marg = np.clip(trio.top3_marginals(p), 1e-12, 1 - 1e-12)
        placed = test["is_placed"].to_numpy(dtype=float)[idx]
        place_nll[idx] = -(placed * np.log(marg) + (1 - placed) * np.log(1 - marg))
    return pd.Series(win_nll), place_nll


def _paired(
    diff: np.ndarray, race_codes: np.ndarray, n_bootstrap: int, rng
) -> tuple[float, float, float]:
    """値の差（行ごと）を、レース単位で復元抽出したときの平均の95%CI。"""
    n_races = race_codes.max() + 1
    race_sum = np.bincount(race_codes, weights=diff, minlength=n_races)
    race_cnt = np.bincount(race_codes, minlength=n_races).astype(float)
    boot = []
    for _ in range(n_bootstrap):
        s = rng.integers(0, n_races, size=n_races)
        boot.append(race_sum[s].sum() / max(race_cnt[s].sum(), 1))
    lo, hi = np.percentile(boot, [2.5, 97.5])
    return float(diff.mean()), float(lo), float(hi)


def run(
    df: pd.DataFrame,
    half_life_days: float | None = 1095.0,
    n_bootstrap: int = 2000,
    random_state: int | None = 42,
) -> dict[str, pd.DataFrame]:
    featured = debut_features.add_debut_features(compute_recent_stats(df))
    featured = featured.sort_values(["date", "race_id"])
    featured["_career"] = featured.groupby("horse_id", observed=True).cumcount()
    featured = _complete_races(featured)
    train_df, val_df, test_df = split_by_date(featured)
    weight = (
        compute_time_decay_weight(
            train_df["date"], train_df["date"].max(), half_life_days
        )
        if half_life_days is not None
        else None
    )

    test = test_df.sort_values(["race_id", "horse_number"]).reset_index(drop=True)
    variants = (("P3", None), ("P3+初出走向け", debut_features.DEBUT_COLUMNS))
    for name, extra in variants:
        logger.info(f"{name} を学習中...")
        booster = pl_model.train_pl(
            train_df, val_df, top_k=3, weight=weight, extra_features=extra
        )
        test[name] = pl_model.predict_win_prob(booster, test)
        logger.info(f"{name}: 木の本数 {booster.best_iteration}")
    test["市場"] = np.exp(_market_log_prob(test))

    race_codes, race_ids = pd.factorize(test["race_id"])
    races = test.drop_duplicates("race_id").set_index("race_id")
    is_newcomer_race = (races["class_level"] == 0).reindex(race_ids).to_numpy()
    is_debut_horse = (test["_career"] == 0).to_numpy()

    results = {}
    for m in METHODS:
        results[m] = _per_race_and_horse(test, m)

    rng = np.random.default_rng(random_state)
    rows = []
    for subset, race_mask, horse_mask in (
        ("全体", np.ones(len(race_ids), bool), np.ones(len(test), bool)),
        ("新馬戦 / 初出走の馬", is_newcomer_race, is_debut_horse),
    ):
        win_base = results["P3"][0].reindex(race_ids).to_numpy()
        win_new = results["P3+初出走向け"][0].reindex(race_ids).to_numpy()
        win_mkt = results["市場"][0].reindex(race_ids).to_numpy()
        ok = race_mask & ~np.isnan(win_base) & ~np.isnan(win_new)
        # レース単位の値なので、各行が1レース（番号は 0..件数-1 の連番）
        mean, lo, hi = _paired(
            (win_new - win_base)[ok], np.arange(int(ok.sum())), n_bootstrap, rng
        )
        rows.append(
            {
                "対象": subset,
                "指標": "勝率（レース単位）",
                "件数": int(ok.sum()),
                "P3": float(np.nanmean(win_base[ok])),
                "P3+初出走向け": float(np.nanmean(win_new[ok])),
                "市場": float(np.nanmean(win_mkt[ok])),
                "差": mean,
                "差_CI下限": lo,
                "差_CI上限": hi,
                "有意": not (lo <= 0 <= hi),
            }
        )
        base_p = results["P3"][1][horse_mask]
        new_p = results["P3+初出走向け"][1][horse_mask]
        mkt_p = results["市場"][1][horse_mask]
        codes = pd.factorize(race_codes[horse_mask])[0]
        mean, lo, hi = _paired(new_p - base_p, codes, n_bootstrap, rng)
        rows.append(
            {
                "対象": subset,
                "指標": "3着内率（馬単位）",
                "件数": int(horse_mask.sum()),
                "P3": float(base_p.mean()),
                "P3+初出走向け": float(new_p.mean()),
                "市場": float(mkt_p.mean()),
                "差": mean,
                "差_CI下限": lo,
                "差_CI上限": hi,
                "有意": not (lo <= 0 <= hi),
            }
        )
    logger.info(f"評価対象: テスト期間 {len(race_ids):,}レース")
    return {"summary": pd.DataFrame(rows)}


def save_results(
    results: dict[str, pd.DataFrame], output_dir: Path = _OUTPUT_DIR
) -> list[Path]:
    """結果を CSV に保存し、保存先パスを返す。"""
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    paths = []
    for name, frame in results.items():
        path = output_dir / f"debut_{name}_{timestamp}.csv"
        frame.to_csv(path, index=False)
        paths.append(path)
    return paths

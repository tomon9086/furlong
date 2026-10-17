"""オッズなしモデルとオッズ起点モデルの比較実験。

人気帯別の較正（ADR-0035）で、モデルの確率が人気薄を大きく過大評価しており、
その原因は確率の作り方ではなく「市場が持っていてモデルに無い情報」だと分かった。
そこで、市場（単勝オッズ）を出発点にしてモデルは補正だけを学ぶ「オッズ起点モデル」と、
これまでどおりオッズを使わない「オッズなしモデル」を同じ条件で学習して比べる。
2つは役割が違う（市場と独立した見立て / 市場込みの確率）ので、
運用では両方を並べて出す想定。

比較する勝率:
    V0  : 現行（lambdarank → isotonic → レース内で割り戻し）
    P1  : Plackett-Luce（勝ち馬だけ）・オッズなし
    P3  : Plackett-Luce（1〜3着の順番まで）・オッズなし
    M3  : Plackett-Luce（1〜3着の順番まで）・市場の勝率の log を init_score にした補正
    市場: 単勝オッズから逆算した勝率（1/オッズ をレース内で正規化）

注意:
    - 学習・評価のオッズは確定オッズ（race_results.odds）。実際の予測では発走前の
      オッズを使うため、M3 は本番では評価より少し悪くなる見込み。
    - 全馬の単勝オッズがあり、同着なしで1〜3着が決まったレースに揃える（全方法共通）。
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from predictor import calibration, evaluation, model, pl_model
from predictor.preprocessing import (
    compute_recent_stats,
    compute_time_decay_weight,
    split_by_date,
)
from predictor.sharpness_experiment import _race_groups, _trio_and_place, _win_nll

logger = logging.getLogger(__name__)

_OUTPUT_DIR = Path(__file__).parent.parent.parent / "output"
METHODS = ["V0", "P1", "P3", "M3", "市場"]


def _complete_races(df: pd.DataFrame) -> pd.DataFrame:
    """全馬の単勝オッズ・人気があり、同着なしで1〜3着が決まったレースに絞る。"""
    df = df.copy()
    df["odds"] = pd.to_numeric(df["odds"], errors="coerce")
    df["popularity"] = pd.to_numeric(df["popularity"], errors="coerce")
    g = df.groupby("race_id")
    odds_ok = g["odds"].transform(lambda c: (c > 0).all())
    pop_ok = g["popularity"].transform(lambda c: c.notna().all())
    top3_ok = g["finishing_position"].transform(
        lambda c: sorted(c[c <= 3].tolist()) == [1, 2, 3]
    )
    size_ok = g["race_id"].transform("size") >= 4
    return df[odds_ok & pop_ok & top3_ok & size_ok].reset_index(drop=True)


def _market_log_prob(df: pd.DataFrame) -> np.ndarray:
    inv = 1.0 / df["odds"].to_numpy(dtype=float)
    total = pd.Series(inv).groupby(df["race_id"].to_numpy()).transform("sum")
    return np.log(inv / total.to_numpy())


def _paired(
    per_race: dict[str, dict[str, np.ndarray]],
    baseline: str,
    n_bootstrap: int,
    rng: np.random.Generator,
) -> pd.DataFrame:
    rows = []
    for m, metrics in per_race.items():
        for metric, values in metrics.items():
            base = per_race[baseline][metric]
            diff = values - base
            boot = np.empty(n_bootstrap)
            for i in range(n_bootstrap):
                boot[i] = diff[rng.integers(0, len(diff), size=len(diff))].mean()
            lo, hi = np.percentile(boot, [2.5, 97.5])
            rows.append(
                {
                    "baseline": baseline,
                    "method": m,
                    "metric": metric,
                    "value": float(values.mean()),
                    "diff": float(diff.mean()),
                    "diff_ci_lower": float(lo),
                    "diff_ci_upper": float(hi),
                    "diff_significant": m != baseline and not (lo <= 0 <= hi),
                }
            )
    return pd.DataFrame(rows)


def run(
    df: pd.DataFrame,
    half_life_days: float | None = 1095.0,
    n_bootstrap: int = 2000,
    random_state: int | None = 42,
) -> dict[str, pd.DataFrame]:
    """標準 split で V0・P1・P3・M3・市場を比較する。"""
    featured = _complete_races(compute_recent_stats(df))
    train_df, val_df, test_df = split_by_date(featured)
    logger.info(
        f"学習 {train_df['race_id'].nunique():,} / "
        f"較正 {val_df['race_id'].nunique():,} / "
        f"テスト {test_df['race_id'].nunique():,} レース（全馬オッズあり・同着なし）"
    )
    weight = (
        compute_time_decay_weight(
            train_df["date"], train_df["date"].max(), half_life_days
        )
        if half_life_days is not None
        else None
    )

    keep_cols = ["race_id", "horse_number", "finishing_position", "popularity"]
    test = test_df[keep_cols + ["is_win", "is_placed"]].copy()

    logger.info("V0（現行）を学習中...")
    models = model.train(train_df, half_life_days=half_life_days)
    calibrated = calibration.calibrate_models(models, val_df)
    v0 = model.predict(calibrated, test_df)[["race_id", "horse_number", "win_prob"]]
    test = test.merge(
        v0.rename(columns={"win_prob": "V0"}), on=["race_id", "horse_number"]
    )

    init_train = _market_log_prob(train_df)
    init_val = _market_log_prob(val_df)
    init_test = _market_log_prob(test_df)

    rounds = {}
    variants = (("P1", 1, False), ("P3", 3, False), ("M3", 3, True))
    for name, top_k, use_market in variants:
        logger.info(f"{name} を学習中...（top_k={top_k}, オッズ起点={use_market}）")
        booster = pl_model.train_pl(
            train_df,
            val_df,
            top_k=top_k,
            init_train=init_train if use_market else None,
            init_val=init_val if use_market else None,
            weight=weight,
        )
        rounds[name] = booster.best_iteration
        probs = pl_model.predict_win_prob(
            booster, test_df, init=init_test if use_market else None
        )
        test = test.merge(
            test_df[["race_id", "horse_number"]].assign(**{name: probs}),
            on=["race_id", "horse_number"],
        )
        logger.info(f"{name}: 木の本数 {booster.best_iteration}")

    test = test.merge(
        test_df[["race_id", "horse_number"]].assign(市場=np.exp(init_test)),
        on=["race_id", "horse_number"],
    )
    test = test.sort_values(["race_id", "horse_number"]).reset_index(drop=True)
    groups = _race_groups(test)
    is_win = test["is_win"].to_numpy()

    per_race: dict[str, dict[str, np.ndarray]] = {}
    for m in METHODS:
        logger.info(f"評価中: {m}")
        trio_nll, place_nll, marg = _trio_and_place(test, m, groups)
        test[f"{m}_top3"] = marg
        per_race[m] = {
            "win_nll": _win_nll(test[m].to_numpy(), is_win, groups),
            "trio_nll": trio_nll,
            "place_nll": place_nll,
        }

    rng = np.random.default_rng(random_state)
    summary = pd.concat(
        [
            _paired(per_race, "V0", n_bootstrap, rng),
            _paired(per_race, "市場", n_bootstrap, rng),
        ],
        ignore_index=True,
    )

    prob_cols = {}
    for m in METHODS:
        prob_cols[f"勝率 {m}"] = m
        prob_cols[f"3着内 {m}"] = f"{m}_top3"
    by_popularity = evaluation.calibration_by_popularity(
        test, prob_cols, n_bootstrap=500, random_state=random_state
    )

    # M3 が市場からどれだけ離れたか（勝率の log 比の絶対値の平均）
    shift = float(np.abs(np.log(test["M3"] / test["市場"])).mean())
    info = pd.DataFrame(
        [{"method": k, "best_iteration": v} for k, v in rounds.items()]
        + [{"method": "M3 の市場からの平均 |log(p/q)|", "best_iteration": shift}]
    )
    return {"summary": summary, "by_popularity": by_popularity, "info": info}


def save_results(
    results: dict[str, pd.DataFrame], output_dir: Path = _OUTPUT_DIR
) -> list[Path]:
    """結果を CSV に保存し、保存先パスを返す。"""
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    paths = []
    for name, frame in results.items():
        path = output_dir / f"market_residual_{name}_{timestamp}.csv"
        frame.to_csv(path, index=False)
        paths.append(path)
    return paths

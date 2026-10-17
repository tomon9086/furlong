"""勝率の鋭さ（レース単位の温度）調整の比較実験。

人気帯別の較正（``calibration-by-popularity``）で、モデルの確率が全体に平らすぎ、
人気薄を大きく過大評価していることが分かった。現行の勝率は
「lambdarank の生スコア → 馬ごとの isotonic 較正 → レース内で合計1に割り戻し」で
作っているが、lambdarank のスコアはレース内の相対的な強さにしか意味がないため、
レースと無関係に馬ごとに確率へ変換する isotonic がずれの原因になっている可能性がある。

比較する勝率:
    V0（現行）: 上記の作り方
    V1        : V0 を p**gamma で鋭くしてレース内で正規化（gamma は較正期間で推定）
    V2        : isotonic を使わず、生スコアのレース内 softmax を p**k で鋭くする
                （= softmax(k × スコア)。k は較正期間で推定。レース単位の温度調整）

評価（テスト期間、全方法で同じレース集合）:
    - 勝率の対数尤度: 勝ち馬に付けた確率の -log（レース内で正規化した多項分布として）
    - 三連複の対数尤度: 勝率を Plackett-Luce に入れたときの、実際の3頭の組の -log
    - 3着内率の logloss: 同じく Plackett-Luce の周辺確率と is_placed の logloss
    - 人気帯別のずれ（``evaluation.calibration_by_popularity``）
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize_scalar

from predictor import calibration, evaluation, model, trio
from predictor.model import Models
from predictor.preprocessing import compute_recent_stats, split_by_date

logger = logging.getLogger(__name__)

_OUTPUT_DIR = Path(__file__).parent.parent.parent / "output"
BASELINE = "V0（現行）"


def _race_groups(df: pd.DataFrame) -> list[np.ndarray]:
    indices = df.groupby("race_id", sort=False).indices
    return [np.asarray(idx) for idx in indices.values()]


def _sharpen(p: np.ndarray, groups: list[np.ndarray], power: float) -> np.ndarray:
    out = np.empty_like(p)
    for idx in groups:
        q = np.clip(p[idx], 1e-12, None) ** power
        out[idx] = q / q.sum()
    return out


def _win_nll(p: np.ndarray, is_win: np.ndarray, groups: list[np.ndarray]) -> np.ndarray:
    """レースごとの -log(勝ち馬の確率)。勝ち馬が1頭でないレースは NaN。"""
    out = np.full(len(groups), np.nan)
    for r, idx in enumerate(groups):
        winners = idx[is_win[idx] == 1]
        if len(winners) == 1:
            out[r] = -np.log(max(p[winners[0]], 1e-300))
    return out


def _fit_power(p: np.ndarray, is_win: np.ndarray, groups: list[np.ndarray]) -> float:
    def objective(power: float) -> float:
        return float(np.nanmean(_win_nll(_sharpen(p, groups, power), is_win, groups)))

    return float(minimize_scalar(objective, bounds=(0.3, 4.0), method="bounded").x)


def _prepare(featured_part: pd.DataFrame, models: Models, calibrated) -> pd.DataFrame:
    """現行の較正済み勝率と、isotonic を通さない生スコアの softmax 勝率を並べる。"""
    cal = model.predict(calibrated, featured_part)
    raw = model.predict(models, featured_part)
    cols = ["race_id", "horse_number", "finishing_position", "popularity", "odds"]
    out = featured_part[cols + ["is_win", "is_placed"]].merge(
        cal[["race_id", "horse_number", "win_prob"]], on=["race_id", "horse_number"]
    )
    out = out.merge(
        raw[["race_id", "horse_number", "win_prob"]].rename(
            columns={"win_prob": "raw_softmax"}
        ),
        on=["race_id", "horse_number"],
    )
    out["popularity"] = pd.to_numeric(out["popularity"], errors="coerce")
    out["odds"] = pd.to_numeric(out["odds"], errors="coerce")
    # 全馬の人気がそろい、同着なしで1〜3着が決まったレースに揃える
    ok = out.groupby("race_id")["popularity"].transform(lambda c: c.notna().all())
    top3 = out.groupby("race_id")["finishing_position"].transform(
        lambda c: sorted(c[c <= 3].tolist()) == [1, 2, 3]
    )
    size = out.groupby("race_id")["race_id"].transform("size")
    return out[ok & top3 & (size >= 4)].reset_index(drop=True)


def _trio_and_place(
    data: pd.DataFrame, prob_col: str, groups: list[np.ndarray]
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Plackett-Luce での三連複 -log・3着内 logloss（レースごと）と3着内の周辺確率。"""
    p_all = data[prob_col].to_numpy()
    pos = data["finishing_position"].to_numpy()
    strengths, top3_idx = [], []
    marg_all = np.empty(len(data))
    place_nll = np.empty(len(groups))
    for r, idx in enumerate(groups):
        p = p_all[idx] / p_all[idx].sum()
        strengths.append(p)
        top3_idx.append(np.argsort(pos[idx], kind="stable")[:3])
        marg = np.clip(trio.top3_marginals(p), 1e-12, 1 - 1e-12)
        marg_all[idx] = marg
        placed = (pos[idx] <= 3).astype(float)
        place_nll[r] = float(
            -(placed * np.log(marg) + (1 - placed) * np.log(1 - marg)).mean()
        )
    actual = trio.actual_trio_probability(strengths, np.array(top3_idx))
    trio_nll = -np.log(np.clip(actual, 1e-300, None))
    return trio_nll, place_nll, marg_all


def run(
    df: pd.DataFrame,
    half_life_days: float | None = 1095.0,
    n_bootstrap: int = 10_000,
    random_state: int | None = 42,
) -> dict[str, pd.DataFrame]:
    """標準 split で V0〜V2 を比較する。"""
    featured = compute_recent_stats(df)
    train_df, val_df, test_df = split_by_date(featured)
    models = model.train(train_df, half_life_days=half_life_days)
    calibrated = calibration.calibrate_models(models, val_df)

    val = _prepare(val_df, models, calibrated)
    test = _prepare(test_df, models, calibrated)
    val_groups, test_groups = _race_groups(val), _race_groups(test)
    val_win = val["is_win"].to_numpy()

    gamma = _fit_power(val["win_prob"].to_numpy(), val_win, val_groups)
    k = _fit_power(val["raw_softmax"].to_numpy(), val_win, val_groups)
    logger.info(
        f"較正期間 {len(val_groups):,}レースで推定: V1 gamma={gamma:.3f} / V2 k={k:.3f}"
    )

    test["V0（現行）"] = test["win_prob"]
    win_prob = test["win_prob"].to_numpy()
    raw_softmax = test["raw_softmax"].to_numpy()
    test["V1（isotonic+鋭さ）"] = _sharpen(win_prob, test_groups, gamma)
    test["V2（softmax+温度）"] = _sharpen(raw_softmax, test_groups, k)
    methods = [BASELINE, "V1（isotonic+鋭さ）", "V2（softmax+温度）"]
    logger.info(f"評価対象: テスト期間 {len(test_groups):,}レース")

    is_win = test["is_win"].to_numpy()
    per_race: dict[str, dict[str, np.ndarray]] = {}
    for m in methods:
        logger.info(f"評価中: {m}")
        trio_nll, place_nll, marg = _trio_and_place(test, m, test_groups)
        test[f"{m}_top3"] = marg
        per_race[m] = {
            "win_nll": _win_nll(test[m].to_numpy(), is_win, test_groups),
            "trio_nll": trio_nll,
            "place_nll": place_nll,
        }

    rng = np.random.default_rng(random_state)
    n_races = len(test_groups)
    rows = []
    for m in methods:
        for metric, values in per_race[m].items():
            base = per_race[BASELINE][metric]
            valid = ~np.isnan(values) & ~np.isnan(base)
            diff = (values - base)[valid]
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
                    "value": float(np.nanmean(values)),
                    "diff_vs_baseline": float(diff.mean()),
                    "diff_ci_lower": float(lo),
                    "diff_ci_upper": float(hi),
                    "diff_significant": m != BASELINE and not (lo <= 0 <= hi),
                }
            )
    summary = pd.DataFrame(rows)
    logger.info(f"検定対象 {n_races:,}レース")

    prob_cols = {}
    for m in methods:
        prob_cols[f"勝率 {m}"] = m
        prob_cols[f"3着内 {m}"] = f"{m}_top3"
    by_popularity = evaluation.calibration_by_popularity(
        test, prob_cols, n_bootstrap=1000, random_state=random_state
    )
    params = pd.DataFrame([{"gamma_v1": gamma, "k_v2": k}])
    return {"summary": summary, "by_popularity": by_popularity, "params": params}


def save_results(
    results: dict[str, pd.DataFrame], output_dir: Path = _OUTPUT_DIR
) -> list[Path]:
    """結果を CSV に保存し、保存先パスを返す。"""
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    paths = []
    for name, frame in results.items():
        path = output_dir / f"sharpness_{name}_{timestamp}.csv"
        frame.to_csv(path, index=False)
        paths.append(path)
    return paths

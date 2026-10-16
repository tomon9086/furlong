"""三連複確率のベースライン測定（docs/plan/trio-probability.md のフェーズ1・2）。

三連複の確率を作る方法ごとに、テスト期間のレースで次を測る。

- 三連複対数尤度: 実際に1〜3着に来た3頭の組に付けた確率の -log（小さいほど良い）
- 3着内率の logloss: 各方法から出る各馬の3着内確率と is_placed の logloss
- 確率上位 N 点を買った場合の回収率（払戻は payoffs の実配当）

方法:
    現行        : win_prob -> Plackett-Luce（output.py の三連複推奨と同じ確率）
    案A         : win_prob に着順別ディスカウント（lam2, lam3 を較正期間で最尤推定）
    案B         : 3着内確率が複勝モデルの place_prob に一致するよう強さを調整
    市場        : 単勝オッズ（確定）から逆算した勝率 -> Plackett-Luce
    市場+補正   : 市場に案Aと同じ方法で推定したディスカウントをかける

「市場」は単勝オッズしか使っていないので、三連複オッズそのものから逆算した
市場の確率ではない（三連複オッズのバックフィル完了後に別途比較する）。
評価対象は、全馬の単勝オッズがあり、同着なしで1〜3着が決まったレースに限る
（全方法で同じレース集合）。
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from predictor import calibration, model, trio
from predictor.evaluation import _normalize_combination, _parse_payout
from predictor.preprocessing import compute_recent_stats, split_by_date

logger = logging.getLogger(__name__)

_OUTPUT_DIR = Path(__file__).parent.parent.parent / "output"

TOP_N_OPTIONS = [1, 3, 5]
BASELINE = "現行"


def _valid_races(
    test_df: pd.DataFrame, pred_df: pd.DataFrame
) -> tuple[list[str], list[pd.DataFrame]]:
    """全方法で共通に評価できるレース（全馬の単勝オッズあり・同着なし）に絞る。"""
    race_ids, frames = trio.race_arrays(test_df, pred_df, ["win_prob", "place_prob"])
    keep = [i for i, g in enumerate(frames) if (g["odds"] > 0).all()]
    return [race_ids[i] for i in keep], [frames[i] for i in keep]


def _top3_idx(frames: list[pd.DataFrame]) -> np.ndarray:
    return np.array(
        [
            g.sort_values("finishing_position").index[:3].to_numpy()
            for g in frames
        ]
    )


def _strengths(frames: list[pd.DataFrame], source: str) -> list[np.ndarray]:
    if source == "win":
        return [trio._normalize(g["win_prob"].to_numpy()) for g in frames]
    if source == "market":
        return [trio._normalize(1.0 / g["odds"].to_numpy()) for g in frames]
    raise ValueError(source)


def _trio_payoff_map(payoffs_df: pd.DataFrame) -> dict[str, dict[str, float]]:
    trio_payoffs = payoffs_df[payoffs_df["bet_type"] == "三連複"].copy()
    trio_payoffs["payout_value"] = trio_payoffs["payout"].apply(_parse_payout)
    trio_payoffs["combo"] = trio_payoffs["combination"].apply(_normalize_combination)
    result: dict[str, dict[str, float]] = {}
    for row in trio_payoffs.itertuples():
        result.setdefault(str(row.race_id), {})[row.combo] = row.payout_value / 100.0
    return result


def _evaluate_method(
    race_ids: list[str],
    frames: list[pd.DataFrame],
    strengths: list[np.ndarray],
    lam2: float,
    lam3: float,
    payoff_map: dict[str, dict[str, float]],
) -> dict[str, np.ndarray]:
    """1つの方法について、レースごとの指標の配列を返す。"""
    top3_idx = _top3_idx(frames)
    actual = trio.actual_trio_probability(strengths, top3_idx, lam2, lam3)
    out: dict[str, np.ndarray] = {
        "trio_nll": -np.log(np.clip(actual, 1e-300, None)),
        "place_nll": np.empty(len(frames)),
    }
    for n in TOP_N_OPTIONS:
        out[f"top{n}_return"] = np.zeros(len(frames))

    for r, (race_id, g, s) in enumerate(zip(race_ids, frames, strengths, strict=True)):
        combos, probs = trio.trio_set_probabilities(s, lam2, lam3)
        marg = np.zeros(len(s))
        for col in range(3):
            np.add.at(marg, combos[:, col], probs)
        marg = np.clip(marg, 1e-12, 1 - 1e-12)
        placed = (g["finishing_position"] <= 3).to_numpy(dtype=float)
        out["place_nll"][r] = float(
            -(placed * np.log(marg) + (1 - placed) * np.log(1 - marg)).mean()
        )

        horse_numbers = g["hn_int"].to_numpy(dtype=int)
        order = np.argsort(-probs, kind="stable")
        race_payoffs = payoff_map.get(race_id, {})
        for n in TOP_N_OPTIONS:
            ret = 0.0
            for c in combos[order[:n]]:
                key = "-".join(str(h) for h in sorted(horse_numbers[c]))
                ret += race_payoffs.get(key, 0.0)
            out[f"top{n}_return"][r] = ret / n
    return out


def _bootstrap(
    stats: dict[str, dict[str, np.ndarray]],
    n_bootstrap: int,
    random_state: int | None,
) -> pd.DataFrame:
    """方法ごとの点推定・95%CIと、現行との差のペアード95%CIを返す。"""
    n_races = len(next(iter(stats.values()))["trio_nll"])
    rng = np.random.default_rng(random_state)
    metrics = ["trio_nll", "place_nll"] + [f"top{n}_return" for n in TOP_N_OPTIONS]
    base = stats[BASELINE]
    boot = {(k, m): np.empty(n_bootstrap) for k in stats for m in metrics}
    diff = {(k, m): np.empty(n_bootstrap) for k in stats for m in metrics}
    # 添字行列（n_bootstrap × n_races）を一度に作るとメモリを食うので分割する
    chunk = 500
    for start in range(0, n_bootstrap, chunk):
        size = min(chunk, n_bootstrap - start)
        idx = rng.integers(0, n_races, size=(size, n_races), dtype=np.int32)
        for k, s in stats.items():
            for m in metrics:
                boot[(k, m)][start : start + size] = s[m][idx].mean(axis=1)
                diff[(k, m)][start : start + size] = (s[m] - base[m])[idx].mean(axis=1)

    rows = []
    for method, s in stats.items():
        for m in metrics:
            values = s[m]
            diff_lo, diff_hi = np.percentile(diff[(method, m)], [2.5, 97.5])
            rows.append(
                {
                    "method": method,
                    "metric": m,
                    "value": float(values.mean()),
                    "ci_lower": float(np.percentile(boot[(method, m)], 2.5)),
                    "ci_upper": float(np.percentile(boot[(method, m)], 97.5)),
                    "diff_vs_baseline": float(values.mean() - base[m].mean()),
                    "diff_ci_lower": float(diff_lo),
                    "diff_ci_upper": float(diff_hi),
                    "diff_significant": method != BASELINE
                    and not (diff_lo <= 0 <= diff_hi),
                }
            )
    return pd.DataFrame(rows)


def run(
    df: pd.DataFrame,
    payoffs_loader,
    half_life_days: float | None = 1095.0,
    n_bootstrap: int = 10_000,
    random_state: int | None = 42,
) -> dict[str, pd.DataFrame]:
    """標準 split（train/val/test）で三連複確率の各方法を比較する。

    Parameters
    ----------
    df : pd.DataFrame
        ``preprocess()`` 済み・``compute_recent_stats()`` 未適用のデータ。
    payoffs_loader : Callable[[list[str]], pd.DataFrame]
        race_id のリストから払戻データを読み込む関数
        （``load_payoffs`` に DB の URL を部分適用したもの）。
    """
    featured = compute_recent_stats(df)
    train_df, val_df, test_df = split_by_date(featured)
    logger.info(
        f"学習{len(train_df):,}行 / 較正{len(val_df):,}行 / テスト{len(test_df):,}行"
    )
    models = model.train(train_df, half_life_days=half_life_days)
    calibrated = calibration.calibrate_models(models, val_df)
    pred_val = model.predict(calibrated, val_df)
    pred_test = model.predict(calibrated, test_df)

    # ディスカウント指数は較正期間で推定する（テスト期間の結果を見ないため）
    val_ids, val_frames = _valid_races(val_df, pred_val)
    val_top3 = _top3_idx(val_frames)
    lam_win = trio.fit_discount(_strengths(val_frames, "win"), val_top3)
    lam_market = trio.fit_discount(_strengths(val_frames, "market"), val_top3)
    logger.info(
        f"着順別ディスカウント（較正期間 {len(val_ids):,}レースで推定）: "
        f"win_prob lam2={lam_win[0]:.3f} lam3={lam_win[1]:.3f} / "
        f"市場 lam2={lam_market[0]:.3f} lam3={lam_market[1]:.3f}"
    )

    race_ids, frames = _valid_races(test_df, pred_test)
    logger.info(f"評価対象: テスト期間 {len(race_ids):,}レース")
    payoff_map = _trio_payoff_map(payoffs_loader(race_ids))

    win_s = _strengths(frames, "win")
    market_s = _strengths(frames, "market")
    logger.info("案B: 3着内確率を place_prob に合わせた強さを計算中...")
    place_s = [
        trio.strengths_matching_marginals(g["place_prob"].to_numpy(), init=s)
        for g, s in zip(frames, win_s, strict=True)
    ]

    methods = {
        "現行": (win_s, 1.0, 1.0),
        "案A": (win_s, *lam_win),
        "案B": (place_s, 1.0, 1.0),
        "市場": (market_s, 1.0, 1.0),
        "市場+補正": (market_s, *lam_market),
    }
    stats = {}
    for name, (strengths, lam2, lam3) in methods.items():
        logger.info(f"評価中: {name}")
        stats[name] = _evaluate_method(
            race_ids, frames, strengths, lam2, lam3, payoff_map
        )

    summary = _bootstrap(stats, n_bootstrap, random_state)
    params = pd.DataFrame(
        [
            {"source": "win_prob", "lam2": lam_win[0], "lam3": lam_win[1]},
            {"source": "市場", "lam2": lam_market[0], "lam3": lam_market[1]},
        ]
    )
    return {"summary": summary, "discount": params}


def save_results(
    results: dict[str, pd.DataFrame], output_dir: Path = _OUTPUT_DIR
) -> list[Path]:
    """結果を CSV に保存し、保存先パスを返す。"""
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    paths = []
    for name, frame in results.items():
        path = output_dir / f"trio_baseline_{name}_{timestamp}.csv"
        frame.to_csv(path, index=False)
        paths.append(path)
    return paths

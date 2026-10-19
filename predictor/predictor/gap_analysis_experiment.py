"""モデルが市場にどこで負けているかの調査（区切り別の対数尤度の差）。

オッズなしのモデル（Plackett-Luce 上位3頭、ADR-0036）は、市場（単勝オッズ）より
勝率の対数尤度が大きく悪い（ADR-0035 のとおり情報不足が原因）。足すべき情報の
手がかりを得るため、テスト期間のレースを区切りごとに分けて、モデルと市場の差が
どこで大きいかを調べる。

- レース単位: 勝ち馬に付けた確率の -log（勝率の対数尤度）を、クラス・グレード・
  芝ダート・距離・頭数・馬場状態・開催場で区切る。
- 馬単位: Plackett-Luce の3着内率の logloss を、キャリア（何戦目か）・出走間隔・
  年齢・人気で区切る。

各区切りについて、件数・モデル・市場・差（モデル − 市場、正ならモデルが負けている）・
差の95%CI（レース単位 bootstrap）・全体の差のうちその区切りが占める割合を出す。
市場側は確定オッズで、発走前より有利な条件である点に注意。
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from predictor import pl_model, trio
from predictor.market_residual_experiment import _complete_races, _market_log_prob
from predictor.preprocessing import (
    compute_recent_stats,
    compute_time_decay_weight,
    split_by_date,
)

logger = logging.getLogger(__name__)

_OUTPUT_DIR = Path(__file__).parent.parent.parent / "output"

_CLASS_LABELS = {0: "新馬", 1: "未勝利", 2: "1勝", 3: "2勝", 4: "3勝", 5: "オープン"}


def _band(values: pd.Series, edges: list[float], labels: list[str]) -> pd.Series:
    return pd.cut(values, bins=edges, labels=labels, right=False).astype(str)


def _race_segments(test: pd.DataFrame) -> pd.DataFrame:
    """レース単位の区切り（1行1レース）。"""
    races = test.drop_duplicates("race_id").set_index("race_id")
    grade = races["grade"].astype(str).replace({"nan": "", "None": ""})
    seg = pd.DataFrame(index=races.index)
    seg["クラス"] = races["class_level"].map(_CLASS_LABELS).fillna("不明")
    seg["グレード"] = np.where(
        grade.str.contains("G1|GI$", regex=True),
        "G1",
        np.where(grade.str.contains("G", regex=False), "G2/G3", "重賞以外"),
    )
    seg["芝ダート"] = races["course_type"].astype(str)
    seg["距離"] = _band(
        pd.to_numeric(races["distance"], errors="coerce"),
        [0, 1400, 1800, 2200, 9999],
        ["〜1399m", "1400〜1799m", "1800〜2199m", "2200m〜"],
    )
    seg["頭数"] = _band(
        pd.to_numeric(races["head_count"], errors="coerce"),
        [0, 10, 14, 17, 99],
        ["〜9頭", "10〜13頭", "14〜16頭", "17頭〜"],
    )
    seg["馬場状態"] = races["track_condition"].astype(str)
    seg["開催場"] = races["venue"].astype(str)
    return seg


def _horse_segments(test: pd.DataFrame) -> pd.DataFrame:
    """馬単位の区切り（test と同じ行順）。"""
    seg = pd.DataFrame(index=test.index)
    seg["キャリア"] = _band(
        test["career_starts"],
        [0, 1, 3, 6, 16, 999],
        ["初出走", "2〜3戦目", "4〜6戦目", "7〜16戦目", "17戦目〜"],
    )
    seg["出走間隔"] = _band(
        test["days_since_last_race"],
        [0, 15, 36, 91, 181, 99999],
        ["〜2週", "3〜5週", "6週〜3か月", "3〜6か月", "半年〜"],
    ).where(test["days_since_last_race"].notna(), "初出走")
    seg["年齢"] = _band(
        test["age"], [0, 3, 4, 5, 6, 99], ["2歳", "3歳", "4歳", "5歳", "6歳〜"]
    )
    seg["人気"] = _band(
        test["popularity"],
        [1, 2, 4, 7, 10, 13, 99],
        ["1番人気", "2-3番人気", "4-6番人気", "7-9番人気", "10-12番人気", "13番人気〜"],
    )
    return seg


def _summarize(
    values: pd.DataFrame,
    segments: pd.DataFrame,
    race_index: np.ndarray,
    n_races: int,
    n_bootstrap: int,
    rng: np.random.Generator,
) -> pd.DataFrame:
    """区切りごとの差（model − market）と、レース単位 bootstrap の CI。

    values は model・market 列を持つ（レース単位なら1行1レース、馬単位なら1行1頭）。
    race_index は各行のレース番号（0..n_races-1）。
    """
    diff = (values["model"] - values["market"]).to_numpy()
    total_gap = diff.sum()
    samples = [rng.integers(0, n_races, size=n_races) for _ in range(n_bootstrap)]
    rows = []
    for col in segments.columns:
        for label, mask in segments.groupby(col).groups.items():
            idx = segments.index.get_indexer(mask)
            seg_race = race_index[idx]
            seg_diff = diff[idx]
            # レースごとの差の合計と件数を作り、レースを復元抽出して平均の CI を出す
            race_sum = np.bincount(seg_race, weights=seg_diff, minlength=n_races)
            race_cnt = np.bincount(seg_race, minlength=n_races).astype(float)
            boot = np.array(
                [race_sum[s].sum() / max(race_cnt[s].sum(), 1) for s in samples]
            )
            lo, hi = np.percentile(boot, [2.5, 97.5])
            rows.append(
                {
                    "区切り": col,
                    "値": label,
                    "件数": len(idx),
                    "モデル": float(values["model"].to_numpy()[idx].mean()),
                    "市場": float(values["market"].to_numpy()[idx].mean()),
                    "差": float(seg_diff.mean()),
                    "差_CI下限": float(lo),
                    "差_CI上限": float(hi),
                    "全体の差に占める割合": float(seg_diff.sum() / total_gap),
                }
            )
    return pd.DataFrame(rows)


def run(
    df: pd.DataFrame,
    half_life_days: float | None = 1095.0,
    n_bootstrap: int = 1000,
    random_state: int | None = 42,
) -> dict[str, pd.DataFrame]:
    """標準 split で P3 を学習し、テスト期間の区切り別にモデルと市場の差を出す。"""
    featured = compute_recent_stats(df).sort_values(["date", "race_id"])
    # キャリア: その馬のこのレースより前の出走数（データ上の）
    featured["career_starts"] = featured.groupby("horse_id", observed=True).cumcount()
    featured = _complete_races(featured)
    train_df, val_df, test_df = split_by_date(featured)
    weight = (
        compute_time_decay_weight(
            train_df["date"], train_df["date"].max(), half_life_days
        )
        if half_life_days is not None
        else None
    )
    logger.info("P3（オッズなし）を学習中...")
    booster = pl_model.train_pl(train_df, val_df, top_k=3, weight=weight)

    test = test_df.sort_values(["race_id", "horse_number"]).reset_index(drop=True)
    test["model"] = pl_model.predict_win_prob(booster, test)
    test["market"] = np.exp(_market_log_prob(test))
    race_codes, race_ids = pd.factorize(test["race_id"])
    n_races = len(race_ids)
    logger.info(f"評価対象: テスト期間 {n_races:,}レース")

    # レース単位: 勝ち馬の確率の -log
    winners = test[test["is_win"] == 1].drop_duplicates("race_id").set_index("race_id")
    race_values = pd.DataFrame(
        {
            "model": -np.log(winners["model"].clip(lower=1e-300)),
            "market": -np.log(winners["market"].clip(lower=1e-300)),
        }
    )
    race_seg = _race_segments(test).loc[race_values.index]
    race_index = pd.Index(race_ids).get_indexer(race_values.index)

    # 馬単位: Plackett-Luce の3着内率の logloss
    for col in ("model", "market"):
        marg = np.empty(len(test))
        for _, idx in test.groupby("race_id", sort=False).indices.items():
            p = test[col].to_numpy()[idx]
            marg[idx] = trio.top3_marginals(p / p.sum())
        test[f"{col}_top3"] = np.clip(marg, 1e-12, 1 - 1e-12)
    placed = test["is_placed"].to_numpy(dtype=float)
    horse_values = pd.DataFrame(
        {
            col: -(
                placed * np.log(test[f"{col}_top3"])
                + (1 - placed) * np.log(1 - test[f"{col}_top3"])
            )
            for col in ("model", "market")
        }
    )

    rng = np.random.default_rng(random_state)
    by_race = _summarize(
        race_values.reset_index(drop=True),
        race_seg.reset_index(drop=True),
        race_index,
        n_races,
        n_bootstrap,
        rng,
    )
    by_horse = _summarize(
        horse_values, _horse_segments(test), race_codes, n_races, n_bootstrap, rng
    )
    overall = pd.DataFrame(
        [
            {
                "単位": "レース（勝率）",
                "モデル": float(race_values["model"].mean()),
                "市場": float(race_values["market"].mean()),
            },
            {
                "単位": "馬（3着内率）",
                "モデル": float(horse_values["model"].mean()),
                "市場": float(horse_values["market"].mean()),
            },
        ]
    )
    return {"overall": overall, "by_race": by_race, "by_horse": by_horse}


def save_results(
    results: dict[str, pd.DataFrame], output_dir: Path = _OUTPUT_DIR
) -> list[Path]:
    """結果を CSV に保存し、保存先パスを返す。"""
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    paths = []
    for name, frame in results.items():
        path = output_dir / f"gap_analysis_{name}_{timestamp}.csv"
        frame.to_csv(path, index=False)
        paths.append(path)
    return paths

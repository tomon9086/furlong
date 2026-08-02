"""予測結果の出力モジュール"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from predictor.evaluation import _pop_tier
from predictor.simulation import (
    DEFAULT_N_ITER as _MC_DEFAULT_N_ITER,
    quinella_probability as _quinella_probability,
    simulate_finishing_orders as _simulate_finishing_orders,
    trifecta_box_probability as _trifecta_box_probability,
    wide_probability as _wide_probability,
)

_OUTPUT_DIR = Path("output")
_EV_THRESHOLD = 1.5
_MC_SEED = 42

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Strategy:
    """買い目選定戦略の設定。

    ``popularity_tiers`` は人気帯によるフィルタ（``None`` なら全人気帯）。
    ``ev_threshold`` は ``win_prob × win_odds`` によるEVフィルタ（``None`` ならフィルタなし）。
    """

    name: str
    bet_type: str  # "win" | "wide"
    popularity_tiers: tuple[str, ...] | None
    ev_threshold: float | None
    note: str


# 2026-08-01 の walk-forward プール bootstrap CI 検証（docs/plan/prediction-accuracy-followup.md）に基づく設定。
STRATEGIES: tuple[Strategy, ...] = (
    Strategy(
        name="堅実",
        bet_type="wide",
        popularity_tiers=("2-3番人気",),
        ev_threshold=1.5,
        note=(
            "walk-forward 26年分プールで点推定95.0%・CI[79.8%, 111.7%]（n=913）。"
            "有意ではないが検証済み候補の中で最も損益分岐点に近い。"
        ),
    ),
    Strategy(
        name="大穴",
        bet_type="win",
        popularity_tiers=("7番人気以下",),
        ev_threshold=None,
        note=(
            "回収率は検証上マイナス（pooled 点推定46〜64%、CI上限も100%未達）。"
            "期待値でなく一撃のリターンを狙うレクリエーション枠。少額に限定して運用すること。"
        ),
    ),
)


def _select_strategy_pick(
    win_probs_raw: np.ndarray,
    ev_vals: np.ndarray | None,
    tier_labels: np.ndarray,
    strategy: Strategy,
) -> tuple[list[int], float | None]:
    """レース内の win_prob 最大馬（1位人気予想馬）を戦略条件で判定し、
    bet_type に応じて win_prob 上位N頭を選ぶ。

    ``evaluation.ev_bet_records`` のバックテストロジックと同一にする必要がある:
    EV・人気帯の条件判定は「そのレースの win_prob 最大馬」のみに適用し、
    馬連・ワイド・三連複の相手馬は MC 確率ではなく win_prob 順位でそのまま選ぶ
    （バックテストで測定した回収率と現実の買い目を一致させるため）。

    Returns
    -------
    tuple[list[int], float | None]
        選ばれた馬のグループ内位置（0始まり、win_prob降順）のリストと、
        win_prob 最大馬の EV（対象外は None）。条件を満たさない場合は空リスト。
    """
    n = len(win_probs_raw)
    if n == 0:
        return [], None

    top1 = int(np.argmax(win_probs_raw))

    if strategy.popularity_tiers is not None and (
        tier_labels[top1] not in strategy.popularity_tiers
    ):
        return [], None
    if strategy.ev_threshold is not None:
        if ev_vals is None or not (ev_vals[top1] > strategy.ev_threshold):
            return [], None

    ev = float(ev_vals[top1]) if ev_vals is not None else None
    n_horses = {"win": 1, "wide": 2}[strategy.bet_type]
    if n < n_horses:
        return [], None
    order = np.argsort(-win_probs_raw)[:n_horses]
    return [int(p) for p in order], ev


def _mark_recommended(
    pred_df: pd.DataFrame, rng_seed: int | None = _MC_SEED
) -> pd.DataFrame:
    """MC シミュレーションを用いて推奨買い目フラグを付与する。

    - 単勝: MC EV（mc_win_prob × win_odds）> _EV_THRESHOLD のうち mc_win_prob 最大の1頭
    - 複勝: MC place_prob 上位3頭
    - 馬連: MC 馬連確率（両馬が2着以内に収まる確率）が最大のペア
    - ワイド: MC ワイド確率（両馬が3着以内に収まる確率）が最大のペア
    - 三連複: MC 三連複確率（3頭が3着以内に収まる確率）が最大のトリプレット
    """
    rng = np.random.default_rng(rng_seed)
    df = pred_df.copy()

    if "win_odds" in df.columns:
        df["win_odds"] = pd.to_numeric(df["win_odds"], errors="coerce")
        odds_col = "win_odds"
    elif "odds" in df.columns:
        df["odds"] = pd.to_numeric(df["odds"], errors="coerce")
        odds_col = "odds"
    else:
        odds_col = None

    df["ev"] = np.nan
    df["recommended_win"] = False
    df["recommended_place"] = False
    df["recommended_quinella"] = False
    df["recommended_wide"] = False
    df["recommended_trifecta_box"] = False
    for strat in STRATEGIES:
        df[f"recommended_{strat.name}"] = False
        df[f"ev_{strat.name}"] = np.nan

    if odds_col is not None:
        df["_pop_rank"] = df.groupby("race_id")[odds_col].rank(
            method="min", ascending=True
        )
    else:
        df["_pop_rank"] = np.nan

    for race_id, group in df.groupby("race_id"):
        idx = group.index
        n = len(group)
        win_probs_raw = group["win_prob"].to_numpy(dtype=float)

        if np.isnan(win_probs_raw).all() or np.nan_to_num(win_probs_raw).sum() <= 0:
            continue

        win_probs = np.nan_to_num(win_probs_raw, nan=0.0)
        orders = _simulate_finishing_orders(
            win_probs, n_iter=_MC_DEFAULT_N_ITER, rng=rng
        )

        # レース内 win_prob 最大馬（top1）の人気帯。
        # 「大穴」戦略は top1 が7番人気以下のときに発火する設計のため、
        # 同じ条件下で単勝・馬連・ワイド・三連複の素の推奨（軸）まで出すと
        # 「軸」と「大穴」が同一馬に収束し、2つの戦略が実質1つになってしまう
        # （2026-08-02 クイーンS で発生）。そのため top1 が7番人気以下の
        # レースでは軸側の推奨を出さず、「大穴」戦略のみに委ねる。
        tier_labels = np.array(
            [
                _pop_tier(p) if pd.notna(p) else None
                for p in group["_pop_rank"].to_numpy()
            ]
        )
        top1 = int(np.argmax(win_probs_raw))
        top1_is_longshot = tier_labels[top1] == "7番人気以下"

        # 単勝 EV（win_prob × win_odds）
        ev_vals = None
        if odds_col is not None:
            win_odds_vals = group[odds_col].to_numpy(dtype=float)
            ev_vals = win_probs_raw * win_odds_vals
            df.loc[idx, "ev"] = ev_vals
            ev_mask = ev_vals > _EV_THRESHOLD
            if ev_mask.any() and not top1_is_longshot:
                masked_win = np.where(ev_mask, win_probs_raw, -1.0)
                best_pos = int(np.argmax(masked_win))
                df.loc[idx[best_pos], "recommended_win"] = True
        elif not top1_is_longshot:
            best_pos = int(np.argmax(win_probs_raw))
            df.loc[idx[best_pos], "recommended_win"] = True

        # 戦略別（堅実・大穴）の推奨買い目
        for strat in STRATEGIES:
            positions, strat_ev = _select_strategy_pick(
                win_probs_raw, ev_vals, tier_labels, strat
            )
            if positions:
                df.loc[idx[positions], f"recommended_{strat.name}"] = True
                if strat_ev is not None:
                    df.loc[idx[positions], f"ev_{strat.name}"] = strat_ev

        # 複勝: place_prob 上位3頭
        place_prob_vals = (
            group["place_prob"].to_numpy(dtype=float)
            if "place_prob" in group.columns
            else win_probs_raw
        )
        place_ranks = pd.Series(place_prob_vals, index=idx).rank(
            ascending=False, method="min"
        )
        df.loc[place_ranks[place_ranks <= 3].index, "recommended_place"] = True

        # 馬連: MC 馬連確率最大ペア
        if n >= 2 and not top1_is_longshot:
            q_probs = _quinella_probability(orders)
            upper = np.triu(q_probs, k=1)
            if upper.max() > 0:
                bi, bj = np.unravel_index(np.argmax(upper), upper.shape)
                df.loc[idx[int(bi)], "recommended_quinella"] = True
                df.loc[idx[int(bj)], "recommended_quinella"] = True

        # ワイド: MC ワイド確率最大ペア
        if n >= 2 and not top1_is_longshot:
            w_probs = _wide_probability(orders)
            upper_w = np.triu(w_probs, k=1)
            if upper_w.max() > 0:
                wi, wj = np.unravel_index(np.argmax(upper_w), upper_w.shape)
                df.loc[idx[int(wi)], "recommended_wide"] = True
                df.loc[idx[int(wj)], "recommended_wide"] = True

        # 三連複: MC 三連複確率最大トリプレット
        if n >= 3 and not top1_is_longshot:
            tb_probs = _trifecta_box_probability(orders)
            best_prob = 0.0
            best_triple: tuple[int, int, int] | None = None
            for i in range(n):
                for j in range(i + 1, n):
                    for k in range(j + 1, n):
                        p = tb_probs[i, j, k]
                        if p > best_prob:
                            best_prob = p
                            best_triple = (i, j, k)
            if best_triple is not None:
                bi2, bj2, bk2 = best_triple
                df.loc[idx[bi2], "recommended_trifecta_box"] = True
                df.loc[idx[bj2], "recommended_trifecta_box"] = True
                df.loc[idx[bk2], "recommended_trifecta_box"] = True

    df["recommended"] = (
        df["recommended_win"]
        | df["recommended_place"]
        | df["recommended_quinella"]
        | df["recommended_wide"]
        | df["recommended_trifecta_box"]
    )

    return df.drop(columns=["_pop_rank"])


def print_prediction(pred_df: pd.DataFrame) -> None:
    """予測結果を標準出力に表示する。"""
    df = _mark_recommended(pred_df)
    display_cols = [
        "horse_number",
        "win_prob",
        "place_prob",
        "predicted_rank",
        "recommended",
    ]
    if "horse_name" in df.columns:
        display_cols.insert(1, "horse_name")
    if "ev" in df.columns:
        display_cols.insert(display_cols.index("recommended"), "ev")

    for race_id, group in df.groupby("race_id"):
        group = group.sort_values("predicted_rank")
        show_cols = [c for c in display_cols if c in group.columns]
        logger.info(f"\n=== レース {race_id} ===")
        logger.info(group[show_cols].to_string(index=False))

        win_horses = group[group["recommended_win"]]
        place_horses = group[group["recommended_place"]]
        quinella_horses = group[group["recommended_quinella"]].sort_values(
            "horse_number"
        )
        wide_horses = group[group["recommended_wide"]].sort_values("horse_number")
        trifecta_horses = group[group["recommended_trifecta_box"]].sort_values(
            "horse_number"
        )

        logger.info("\n  推奨買い目:")
        if win_horses.empty:
            logger.info(f"    単勝 : (EV しきい値 {_EV_THRESHOLD} 未達・推奨なし)")
        else:
            if "ev" in win_horses.columns and not win_horses["ev"].isna().all():
                ev_str = f" (EV={float(win_horses['ev'].iloc[0]):.2f})"
            else:
                ev_str = ""
            logger.info(f"    単勝 : {win_horses['horse_number'].tolist()}{ev_str}")

        logger.info(f"    複勝 : {place_horses['horse_number'].tolist()}")

        if len(quinella_horses) >= 2:
            hn = quinella_horses["horse_number"].tolist()
            logger.info(f"    馬連  : {hn[0]}-{hn[1]}")

        if len(wide_horses) >= 2:
            hn = wide_horses["horse_number"].tolist()
            logger.info(f"    ワイド: {hn[0]}-{hn[1]}")

        if len(trifecta_horses) >= 3:
            hn = trifecta_horses["horse_number"].tolist()
            logger.info(f"    三連複: {hn[0]}-{hn[1]}-{hn[2]}")

        logger.info("\n  戦略別推奨:")
        for strat in STRATEGIES:
            picked = group[group[f"recommended_{strat.name}"]].sort_values(
                "horse_number"
            )
            hn = picked["horse_number"].tolist()
            if not hn:
                logger.info(f"    [{strat.name}] ({strat.bet_type}: 該当馬なし)")
                continue
            ev_col = f"ev_{strat.name}"
            if ev_col in picked.columns and not picked[ev_col].isna().all():
                ev_str = f" (EV={float(picked[ev_col].iloc[0]):.2f})"
            else:
                ev_str = ""
            hn_str = "-".join(str(h) for h in hn)
            logger.info(
                f"    [{strat.name}] {strat.bet_type}: {hn_str}{ev_str}  ※{strat.note}"
            )


def _make_filename(
    race_id: str,
    race_name: str | None = None,
    race_number: str | None = None,
    date: str | None = None,
) -> str:
    """レース情報からファイル名用の文字列を生成する。"""
    import re

    # date: 'YYYY/MM/DD' など数字以外を除去して YYYYMMDD 形式に
    date_str = ""
    if date and str(date) not in ("", "None", "NaT", "nan"):
        date_str = re.sub(r"[^0-9]", "", str(date))[:8]

    # race_number: DB値がなければ race_id 末尾2桁から生成して NR 形式に
    race_number_str = ""
    if race_number and str(race_number) not in ("", "None", "NaT", "nan"):
        race_number_str = re.sub(r"[^0-9A-Za-z]", "", str(race_number)) + "R"
    elif len(race_id) >= 2:
        n = race_id[-2:].lstrip("0") or "0"
        race_number_str = n + "R"

    race_name_str = ""
    if race_name and str(race_name) not in ("", "None", "NaT", "nan"):
        race_name_str = re.sub(r"[\s/\\:*?\"<>|]+", "_", str(race_name)).strip("_")

    parts = [p for p in [date_str, race_number_str, race_name_str, race_id] if p]
    return "prediction_" + "_".join(parts)


def _toml_list(values: list) -> str:
    """Python リストを TOML のインライン配列文字列に変換する。"""
    return "[" + ", ".join(str(v) for v in values) + "]"


def _format_betting_toml(pred_df: pd.DataFrame) -> str:
    """予測結果と推奨買い目を TOML 文字列として生成する。

    tomllib は読み込み専用のため、書き込みは手動フォーマットで行う。
    読み込みは tomllib.loads() で行える。
    """
    df = pred_df  # already _mark_recommended されていることを前提とする

    lines: list[str] = [f"ev_threshold = {_EV_THRESHOLD}\n"]

    for race_id, group in df.groupby("race_id"):
        group = group.sort_values("predicted_rank")

        win_horses = group[group["recommended_win"]]
        place_horses = group[group["recommended_place"]]
        quinella_horses = group[group["recommended_quinella"]].sort_values(
            "horse_number"
        )
        wide_horses = group[group["recommended_wide"]].sort_values("horse_number")
        trifecta_horses = group[group["recommended_trifecta_box"]].sort_values(
            "horse_number"
        )

        lines.append("[[race]]")
        lines.append(f'race_id = "{race_id}"')
        lines.append("")

        lines.append("[race.betting]")

        if win_horses.empty:
            lines.append(
                f'win = {{ horses = [], note = "EV threshold {_EV_THRESHOLD} not reached" }}'
            )
        else:
            hn = win_horses["horse_number"].tolist()
            if "ev" in win_horses.columns and not win_horses["ev"].isna().all():
                ev_val = round(float(win_horses["ev"].iloc[0]), 4)
                lines.append(f"win = {{ horses = {_toml_list(hn)}, ev = {ev_val} }}")
            else:
                lines.append(f"win = {{ horses = {_toml_list(hn)} }}")

        lines.append(
            f"place = {{ horses = {_toml_list(place_horses['horse_number'].tolist())} }}"
        )

        if len(quinella_horses) >= 2:
            hn = quinella_horses["horse_number"].tolist()
            lines.append(f"quinella = {{ horses = {_toml_list(hn)} }}")
        else:
            lines.append("quinella = { horses = [] }")

        if len(wide_horses) >= 2:
            hn = wide_horses["horse_number"].tolist()
            lines.append(f"wide = {{ horses = {_toml_list(hn)} }}")
        else:
            lines.append("wide = { horses = [] }")

        if len(trifecta_horses) >= 3:
            hn = trifecta_horses["horse_number"].tolist()
            lines.append(f"trifecta_box = {{ horses = {_toml_list(hn)} }}")
        else:
            lines.append("trifecta_box = { horses = [] }")

        lines.append("")

        for strat in STRATEGIES:
            picked = group[group[f"recommended_{strat.name}"]].sort_values(
                "horse_number"
            )
            lines.append(f'[race.strategies."{strat.name}"]')
            lines.append(f'bet_type = "{strat.bet_type}"')
            lines.append(f"horses = {_toml_list(picked['horse_number'].tolist())}")
            ev_col = f"ev_{strat.name}"
            if ev_col in picked.columns and not picked[ev_col].isna().all():
                lines.append(f"ev = {round(float(picked[ev_col].iloc[0]), 4)}")
            lines.append(f"note = {json.dumps(strat.note, ensure_ascii=False)}")
            lines.append("")

    return "\n".join(lines)


def save_csv(
    pred_df: pd.DataFrame,
    race_id: str,
    output_dir: Path = _OUTPUT_DIR,
    race_name: str | None = None,
    race_number: str | None = None,
    date: str | None = None,
) -> None:
    """予測結果を CSV ファイルに保存する。"""
    df = _mark_recommended(pred_df)
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = _make_filename(
        race_id, race_name=race_name, race_number=race_number, date=date
    )
    path = output_dir / f"{filename}.csv"
    df.sort_values(["race_id", "predicted_rank"]).to_csv(path, index=False)
    logger.info(f"CSV 保存: {path}")


def save_output(
    pred_df: pd.DataFrame,
    race_id: str,
    output_dir: Path = _OUTPUT_DIR,
    race_name: str | None = None,
    race_number: str | None = None,
    date: str | None = None,
) -> None:
    """予測結果を CSV + 買い目 TOML としてディレクトリ配下に保存する。

    output_dir/<race_dirname>/<predict_timestamp>/prediction.csv
    output_dir/<race_dirname>/<predict_timestamp>/betting.toml

    predict を複数回実行しても timestamp サブディレクトリで分離されるため上書きされない。
    """
    from datetime import datetime

    df = _mark_recommended(pred_df)
    filename = _make_filename(
        race_id, race_name=race_name, race_number=race_number, date=date
    )
    predict_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = output_dir / filename / predict_ts
    run_dir.mkdir(parents=True, exist_ok=True)

    csv_path = run_dir / "prediction.csv"
    df.sort_values(["race_id", "predicted_rank"]).to_csv(csv_path, index=False)
    logger.info(f"CSV 保存: {csv_path}")

    toml_path = run_dir / "betting.toml"
    toml_path.write_text(_format_betting_toml(df), encoding="utf-8")
    logger.info(f"TOML 保存: {toml_path}")

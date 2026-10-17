"""オッズなし・オッズありの2パターンの確率を作る。

- オッズなし: Plackett-Luce（上位3頭）で学習した勝ちモデル（ADR-0036）の勝率と、
  それを Plackett-Luce に入れた3着内率・三連複確率。市場と独立した見立て。
- オッズあり: 発走前の単勝オッズから逆算した市場の勝率
  （1/オッズ をレース内で正規化）と、2・3着の着順別ディスカウント
  （lam2, lam3。学習時に較正期間で推定）をかけた Plackett-Luce の
  3着内率・三連複確率。市場の勝率は今の特徴量では超えられず、
  Plackett-Luce の癖（人気薄の2〜3着の過小評価）だけを補正する。

市場との折衷・買い目の選択は別の LLM が担う。ここでは両方の確率を並べて出すだけ。
"""

from __future__ import annotations

import json
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

from predictor import pl_model, trio

PL_WIN_MODEL_FILE = "win_pl_model.txt"
MARKET_DISCOUNT_FILE = "market_discount.json"
TOP_TRIOS = 5


def market_win_prob(df: pd.DataFrame, odds_col: str) -> np.ndarray:
    """各行の市場の勝率。そのレースに単勝オッズの欠けた馬がいれば NaN。"""
    odds = pd.to_numeric(df[odds_col], errors="coerce")
    inv = 1.0 / odds.where(odds > 0)
    race = df["race_id"].to_numpy()
    total = inv.groupby(race).transform("sum")
    complete = inv.notna().groupby(race).transform("all")
    return np.where(complete, inv / total, np.nan)


def fit_market_discount(df: pd.DataFrame) -> tuple[float, float]:
    """着順の決まったレースで、市場の勝率に対する着順別ディスカウントを推定する。

    df は race_id・odds（確定オッズ）・finishing_position を含む学習データ。
    全馬のオッズがあり同着なしで1〜3着が決まったレースだけを使う。
    """
    data = df[["race_id", "finishing_position"]].copy()
    data["q"] = market_win_prob(df, "odds")
    strengths, top3 = [], []
    for _, g in data.groupby("race_id", sort=False):
        positions = g["finishing_position"].to_numpy()
        if g["q"].isna().any() or len(g) < 4:
            continue
        if sorted(positions[positions <= 3].tolist()) != [1, 2, 3]:
            continue
        strengths.append(g["q"].to_numpy())
        top3.append(np.argsort(positions, kind="stable")[:3])
    return trio.fit_discount(strengths, np.array(top3))


def save_pl_win(booster: lgb.Booster, version_dir: Path) -> None:
    """Plackett-Luce の勝ちモデルを保存する。

    自作目的関数は pickle できないため、LightGBM のテキスト形式で保存する。
    """
    booster.save_model(
        str(version_dir / PL_WIN_MODEL_FILE), num_iteration=booster.best_iteration
    )


def save_market_discount(lam2: float, lam3: float, version_dir: Path) -> None:
    (version_dir / MARKET_DISCOUNT_FILE).write_text(
        json.dumps({"lam2": lam2, "lam3": lam3}), encoding="utf-8"
    )


def load_dual_models(
    version_dir: Path,
) -> tuple[lgb.Booster, tuple[float, float]] | None:
    """モデルディレクトリから PL 勝ちモデルと市場のディスカウントを読む。

    どちらかが無ければ None（PL 勝ちモデル導入前に学習したモデル）。
    """
    model_path = version_dir / PL_WIN_MODEL_FILE
    discount_path = version_dir / MARKET_DISCOUNT_FILE
    if not (model_path.exists() and discount_path.exists()):
        return None
    discount = json.loads(discount_path.read_text(encoding="utf-8"))
    return lgb.Booster(model_file=str(model_path)), (discount["lam2"], discount["lam3"])


def _race_top3(
    df: pd.DataFrame, prob_col: str, lam2: float, lam3: float
) -> np.ndarray:
    out = np.full(len(df), np.nan)
    for _, idx in df.groupby("race_id", sort=False).indices.items():
        p = df[prob_col].to_numpy()[idx]
        if np.isnan(p).any() or len(p) < 3:
            continue
        out[idx] = trio.top3_marginals(p / p.sum(), lam2, lam3)
    return out


def top_trios(
    group: pd.DataFrame, prob_col: str, lam2: float, lam3: float, n: int = TOP_TRIOS
) -> list[tuple[list[int], float]]:
    """1レース分の三連複確率の上位 n 組（馬番の昇順リストと確率）。"""
    p = group[prob_col].to_numpy(dtype=float)
    if np.isnan(p).any() or len(p) < 3:
        return []
    horse_numbers = pd.to_numeric(group["horse_number"]).to_numpy(dtype=int)
    combos, probs = trio.trio_set_probabilities(p / p.sum(), lam2, lam3)
    order = np.argsort(-probs, kind="stable")[:n]
    return [
        (sorted(int(h) for h in horse_numbers[combos[i]]), float(probs[i]))
        for i in order
    ]


def add_dual_probabilities(
    pred_df: pd.DataFrame,
    target_df: pd.DataFrame,
    pl_booster: lgb.Booster,
    market_discount: tuple[float, float],
) -> pd.DataFrame:
    """予測結果にオッズなし・オッズありの確率列を加える。

    追加・更新する列:
        win_prob        : オッズなしの勝率（PL 勝ちモデル。lambdarank の値を置き換える）
        top3_prob       : オッズなしの3着内率（win_prob の Plackett-Luce）
        win_prob_odds   : オッズありの勝率（発走前の単勝オッズ。欠けていれば NaN）
        top3_prob_odds  : オッズありの3着内率（市場の勝率 + 着順別ディスカウント）
        predicted_rank  : win_prob の順位（置き換えた win_prob で付け直す）
    """
    out = pred_df.copy()
    probs = pl_model.predict_win_prob(pl_booster, target_df)
    keyed = target_df[["race_id", "horse_number"]].assign(_pl=probs)
    out = out.merge(keyed, on=["race_id", "horse_number"], how="left")
    out["win_prob"] = out["_pl"]
    out = out.drop(columns=["_pl"])
    out["top3_prob"] = _race_top3(out, "win_prob", 1.0, 1.0)

    odds_col = "win_odds" if "win_odds" in out.columns else "odds"
    if odds_col in out.columns:
        out["win_prob_odds"] = market_win_prob(out, odds_col)
    else:
        out["win_prob_odds"] = np.nan
    out["top3_prob_odds"] = _race_top3(out, "win_prob_odds", *market_discount)

    out["predicted_rank"] = (
        out.groupby("race_id")["win_prob"].rank(ascending=False, method="min")
    ).astype(int)
    return out

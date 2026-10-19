"""オッズなし・オッズありの2パターンの確率を作る。

- オッズなし: Plackett-Luce（上位3頭）で学習した勝ちモデル（ADR-0036）の勝率と、
  それを Plackett-Luce に入れた3着内率・三連複確率。市場と独立した見立て。
- オッズあり: 勝率は発走前の単勝オッズから逆算した市場の勝率
  （1/オッズ をレース内で正規化）。三連複確率・3着内率は発走前の三連複オッズを
  q**trio_alpha で補正したもの（ADR-0037）。三連複オッズが取れないときは、
  単勝の市場勝率に2・3着の着順別ディスカウント（lam2, lam3）をかけた
  Plackett-Luce で代用する。パラメータは学習時に較正期間で推定する。

市場との折衷・買い目の選択は別の LLM が担う。ここでは両方の確率を並べて出すだけ。
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from itertools import combinations
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

from predictor import pl_model, trio

PL_WIN_MODEL_FILE = "win_pl_model.txt"
MARKET_DISCOUNT_FILE = "market_discount.json"
TOP_TRIOS = 5

NO_ODDS = "オッズなし"
WITH_ODDS = "オッズあり"
SOURCE_MODEL = "モデル"
SOURCE_TRIO_ODDS = "三連複オッズ"
SOURCE_WIN_ODDS = "単勝オッズ+補正"


@dataclass(frozen=True)
class MarketParams:
    """「オッズあり」の確率を作るパラメータ（学習時に較正期間で推定）。

    lam2, lam3: 単勝の市場勝率に対する2・3着の着順別ディスカウント
    trio_alpha: 三連複オッズ由来の確率のべき補正（None なら三連複オッズは使わない）
    """

    lam2: float
    lam3: float
    trio_alpha: float | None = None


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


def save_market_params(params: MarketParams, version_dir: Path) -> None:
    (version_dir / MARKET_DISCOUNT_FILE).write_text(
        json.dumps(asdict(params)), encoding="utf-8"
    )


def load_dual_models(version_dir: Path) -> tuple[lgb.Booster, MarketParams] | None:
    """モデルディレクトリから PL 勝ちモデルと市場のパラメータを読む。

    どちらかが無ければ None（PL 勝ちモデル導入前に学習したモデル）。
    trio_alpha が無いモデル（ADR-0037 以前）は三連複オッズを使わない。
    """
    model_path = version_dir / PL_WIN_MODEL_FILE
    params_path = version_dir / MARKET_DISCOUNT_FILE
    if not (model_path.exists() and params_path.exists()):
        return None
    raw = json.loads(params_path.read_text(encoding="utf-8"))
    params = MarketParams(raw["lam2"], raw["lam3"], raw.get("trio_alpha"))
    return lgb.Booster(model_file=str(model_path)), params


def trio_odds_from_payload(payload: str) -> dict[str, float]:
    """オッズ API（type=all）の応答から三連複オッズを {組番: オッズ} で取り出す。

    発売されなかった組（0.0 / -2.0 / -3.0 倍、人気9999）は除く。
    発売前の予想オッズ（status=yoso）など、実オッズでない応答なら空を返す。
    人気9999の組は1つの要素にまとめて並ぶことがあるため、4要素ずつ読む。
    """
    try:
        doc = json.loads(payload)
    except json.JSONDecodeError:
        return {}
    # 発走前の実オッズ（middle）か確定オッズ（result）だけ使う。予想オッズ（yoso）は除く
    if doc.get("status") not in ("middle", "result"):
        return {}
    data = doc.get("data")
    entries = data.get("odds", {}).get("7") if isinstance(data, dict) else None
    if not isinstance(entries, dict):
        return {}
    result = {}
    for entry in entries.values():
        if not isinstance(entry, list):
            continue
        for i in range(0, len(entry) - 3, 4):
            combo = str(entry[i + 3]).strip()
            try:
                odds = float(str(entry[i]).replace(",", ""))
            except ValueError:
                continue
            if combo.isdigit() and odds > 0:
                result[combo] = odds
    return result


def _horse_numbers(group: pd.DataFrame) -> np.ndarray:
    return pd.to_numeric(group["horse_number"]).to_numpy(dtype=int)


def _trio_market_probs(
    group: pd.DataFrame, trio_odds: dict[str, float] | None, alpha: float | None
) -> tuple[np.ndarray, np.ndarray] | None:
    """出走馬の全組の三連複オッズがそろっていれば、q**alpha を正規化した確率。"""
    if not trio_odds or alpha is None or len(group) < 3:
        return None
    horse_numbers = _horse_numbers(group)
    combos = np.array(list(combinations(range(len(group)), 3)))
    keys = ["".join(f"{h:02d}" for h in sorted(horse_numbers[c])) for c in combos]
    if any(k not in trio_odds for k in keys):
        return None
    q = np.array([1.0 / trio_odds[k] for k in keys]) ** alpha
    return combos, q / q.sum()


def _pl_probs(
    group: pd.DataFrame, prob_col: str, lam2: float, lam3: float
) -> tuple[np.ndarray, np.ndarray] | None:
    p = group[prob_col].to_numpy(dtype=float)
    if np.isnan(p).any() or len(p) < 3:
        return None
    return trio.trio_set_probabilities(p / p.sum(), lam2, lam3)


def _with_odds_probs(
    group: pd.DataFrame, params: MarketParams, trio_odds: dict[str, float] | None
) -> tuple[str, tuple[np.ndarray, np.ndarray] | None]:
    """「オッズあり」の三連複確率。三連複オッズを優先し、無ければ単勝オッズ+補正。"""
    market = _trio_market_probs(group, trio_odds, params.trio_alpha)
    if market is not None:
        return SOURCE_TRIO_ODDS, market
    return SOURCE_WIN_ODDS, _pl_probs(group, "win_prob_odds", params.lam2, params.lam3)


def _marginals(n: int, combos: np.ndarray, probs: np.ndarray) -> np.ndarray:
    marg = np.zeros(n)
    for col in range(3):
        np.add.at(marg, combos[:, col], probs)
    return marg


def _top(
    group: pd.DataFrame, combo_probs: tuple[np.ndarray, np.ndarray] | None, n: int
) -> list[tuple[list[int], float]]:
    if combo_probs is None:
        return []
    combos, probs = combo_probs
    horse_numbers = _horse_numbers(group)
    order = np.argsort(-probs, kind="stable")[:n]
    return [
        (sorted(int(h) for h in horse_numbers[combos[i]]), float(probs[i]))
        for i in order
    ]


def top_trios(
    group: pd.DataFrame, prob_col: str, lam2: float, lam3: float, n: int = TOP_TRIOS
) -> list[tuple[list[int], float]]:
    """1レース分の、勝率を Plackett-Luce に入れた三連複確率の上位 n 組。"""
    return _top(group, _pl_probs(group, prob_col, lam2, lam3), n)


def trio_candidates(
    group: pd.DataFrame,
    params: MarketParams,
    trio_odds: dict[str, float] | None = None,
    n: int = TOP_TRIOS,
) -> dict[str, dict]:
    """1レース分の、2パターンの三連複確率の上位 n 組と、その確率の出どころ。

    Returns
    -------
    dict
        {"オッズなし" / "オッズあり": {"source": 出どころ, "combos": [(馬番, 確率)]}}
        オッズが無ければ combos は空。
    """
    source, with_odds = _with_odds_probs(group, params, trio_odds)
    return {
        NO_ODDS: {
            "source": SOURCE_MODEL,
            "combos": top_trios(group, "win_prob", 1.0, 1.0, n),
        },
        WITH_ODDS: {"source": source, "combos": _top(group, with_odds, n)},
    }


def add_dual_probabilities(
    pred_df: pd.DataFrame,
    target_df: pd.DataFrame,
    pl_booster: lgb.Booster,
    params: MarketParams,
    trio_odds: dict[str, dict[str, float]] | None = None,
) -> pd.DataFrame:
    """予測結果にオッズなし・オッズありの確率列を加える。

    trio_odds は {race_id: {組番: 発走前の三連複オッズ}}。
    無いレースは単勝オッズ+補正で代用する。

    追加・更新する列:
        win_prob        : オッズなしの勝率（PL 勝ちモデル。lambdarank の値を置き換える）
        top3_prob       : オッズなしの3着内率（win_prob の Plackett-Luce）
        win_prob_odds   : オッズありの勝率（発走前の単勝オッズ。欠けていれば NaN）
        top3_prob_odds  : オッズありの3着内率（三連複オッズ、無ければ単勝オッズ+補正）
        predicted_rank  : win_prob の順位（置き換えた win_prob で付け直す）
    """
    out = pred_df.copy()
    probs = pl_model.predict_win_prob(pl_booster, target_df)
    keyed = target_df[["race_id", "horse_number"]].assign(_pl=probs)
    out = out.merge(keyed, on=["race_id", "horse_number"], how="left")
    out["win_prob"] = out["_pl"]
    out = out.drop(columns=["_pl"])

    odds_col = "win_odds" if "win_odds" in out.columns else "odds"
    if odds_col in out.columns:
        out["win_prob_odds"] = market_win_prob(out, odds_col)
    else:
        out["win_prob_odds"] = np.nan

    out["top3_prob"] = np.nan
    out["top3_prob_odds"] = np.nan
    for race_id, idx in out.groupby("race_id", sort=False).indices.items():
        group = out.iloc[idx]
        no_odds = _pl_probs(group, "win_prob", 1.0, 1.0)
        if no_odds is not None:
            out.iloc[idx, out.columns.get_loc("top3_prob")] = _marginals(
                len(group), *no_odds
            )
        race_trio = (trio_odds or {}).get(race_id)
        _, with_odds = _with_odds_probs(group, params, race_trio)
        if with_odds is not None:
            out.iloc[idx, out.columns.get_loc("top3_prob_odds")] = _marginals(
                len(group), *with_odds
            )

    out["predicted_rank"] = (
        out.groupby("race_id")["win_prob"].rank(ascending=False, method="min")
    ).astype(int)
    return out

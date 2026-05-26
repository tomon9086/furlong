"""モデル評価モジュール"""

from __future__ import annotations

import pandas as pd
from sklearn.metrics import brier_score_loss, log_loss


def evaluate(test_df: pd.DataFrame, pred_df: pd.DataFrame) -> dict[str, float]:
    """テストデータと予測結果から評価指標を計算する。

    Returns
    -------
    dict[str, float]
        win_accuracy   : 単勝的中率（win_prob 最大馬が実際に1着になった割合）
        recovery_rate  : 単勝回収率（100円×レース数投資して返ってくる割合）
        win_logloss    : 単勝モデルの log-loss
        place_logloss  : 複勝モデルの log-loss
        win_brier      : 単勝モデルの Brier score
        place_brier    : 複勝モデルの Brier score
    """
    merged = test_df[["race_id", "horse_number", "is_win", "is_placed", "odds"]].merge(
        pred_df[
            ["race_id", "horse_number", "win_prob", "place_prob", "predicted_rank"]
        ],
        on=["race_id", "horse_number"],
    )

    # 各レースで win_prob 最大の馬を推奨馬とする
    top1_idx = merged.groupby("race_id")["win_prob"].idxmax()
    top1 = merged.loc[top1_idx]

    # 単勝的中率
    win_accuracy = float(top1["is_win"].mean())

    # 単勝回収率: 100円×レース数 を投資し、的中時は odds×100 円を回収
    invested = len(top1) * 100
    recovered = float(
        (top1["is_win"] * pd.to_numeric(top1["odds"], errors="coerce") * 100).sum()
    )
    recovery_rate = recovered / invested if invested > 0 else 0.0

    # Log-loss
    win_logloss = float(log_loss(merged["is_win"], merged["win_prob"]))
    place_logloss = float(log_loss(merged["is_placed"], merged["place_prob"]))

    # Brier score
    win_brier = float(brier_score_loss(merged["is_win"], merged["win_prob"]))
    place_brier = float(brier_score_loss(merged["is_placed"], merged["place_prob"]))

    return {
        "win_accuracy": win_accuracy,
        "recovery_rate": recovery_rate,
        "win_logloss": win_logloss,
        "place_logloss": place_logloss,
        "win_brier": win_brier,
        "place_brier": place_brier,
    }


def evaluate_by_popularity(
    test_df: pd.DataFrame, pred_df: pd.DataFrame
) -> dict[str, pd.DataFrame]:
    """人気帯・オッズ帯別の評価指標を計算する。

    推奨馬（win_prob 最大馬）を人気帯・オッズ帯でグループ化し、
    各グループの推奨頻度・的中率・回収率を返す。

    Returns
    -------
    dict[str, pd.DataFrame]
        popularity_tier : 人気帯別集計（1番人気 / 2-3番 / 4-6番 / 7番以下）
        odds_tier       : オッズ帯別集計（〜1.9倍 / 2-4倍 / 5-9倍 / 10倍以上）
    """
    merged = test_df[["race_id", "horse_number", "is_win", "odds", "popularity"]].merge(
        pred_df[["race_id", "horse_number", "win_prob"]],
        on=["race_id", "horse_number"],
    )

    merged["odds"] = pd.to_numeric(merged["odds"], errors="coerce")
    merged["popularity"] = pd.to_numeric(merged["popularity"], errors="coerce")

    # 各レースで win_prob 最大の馬を推奨馬とする
    top1_idx = merged.groupby("race_id")["win_prob"].idxmax()
    top1 = merged.loc[top1_idx].copy()

    # 人気帯ラベル付け
    def _pop_tier(p: float) -> str:
        if p == 1:
            return "1番人気"
        elif p <= 3:
            return "2-3番人気"
        elif p <= 6:
            return "4-6番人気"
        else:
            return "7番人気以下"

    top1["popularity_tier"] = top1["popularity"].map(_pop_tier)

    # オッズ帯ラベル付け
    def _odds_tier(o: float) -> str:
        if o < 2.0:
            return "〜1.9倍"
        elif o < 5.0:
            return "2-4倍"
        elif o < 10.0:
            return "5-9倍"
        else:
            return "10倍以上"

    top1["odds_tier"] = top1["odds"].map(_odds_tier)

    def _aggregate(df: pd.DataFrame, group_col: str, order: list[str]) -> pd.DataFrame:
        agg = (
            df.groupby(group_col)
            .apply(
                lambda g: pd.Series(
                    {
                        "推奨頻度": len(g),
                        "的中率": float(g["is_win"].mean()),
                        "回収率": float(
                            (g["is_win"] * g["odds"] * 100).sum() / (len(g) * 100)
                        ),
                    }
                ),
                include_groups=False,
            )
            .reindex(order)
        )
        return agg

    popularity_order = ["1番人気", "2-3番人気", "4-6番人気", "7番人気以下"]
    odds_order = ["〜1.9倍", "2-4倍", "5-9倍", "10倍以上"]

    return {
        "popularity_tier": _aggregate(top1, "popularity_tier", popularity_order),
        "odds_tier": _aggregate(top1, "odds_tier", odds_order),
    }


def evaluate_by_grade(test_df: pd.DataFrame, pred_df: pd.DataFrame) -> pd.DataFrame:
    """重賞グレード別の評価指標を計算する。

    推奨馬（win_prob 最大馬）をグレード別でグループ化し、
    各グループの推奨頻度・的中率・回収率を返す。

    Parameters
    ----------
    test_df : pd.DataFrame
        テストデータ（race_id, horse_number, is_win, odds, grade を含む）
    pred_df : pd.DataFrame
        予測結果（race_id, horse_number, win_prob を含む）

    Returns
    -------
    pd.DataFrame
        グレード別集計（GI / GII / GIII / L / 平場）
    """
    merged = test_df[["race_id", "horse_number", "is_win", "odds", "grade"]].merge(
        pred_df[["race_id", "horse_number", "win_prob"]],
        on=["race_id", "horse_number"],
    )

    merged["odds"] = pd.to_numeric(merged["odds"], errors="coerce")
    # category 型を文字列に変換
    merged["grade"] = merged["grade"].astype(str).replace({"nan": None, "": None})

    # 各レースで win_prob 最大の馬を推奨馬とする
    top1_idx = merged.groupby("race_id")["win_prob"].idxmax()
    top1 = merged.loc[top1_idx].copy()

    def _grade_tier(g: str | None) -> str:
        if g in ("GI", "GII", "GIII", "L"):
            return g
        return "平場"

    top1["grade_tier"] = top1["grade"].map(_grade_tier)

    order = ["GI", "GII", "GIII", "L", "平場"]

    agg = (
        top1.groupby("grade_tier")
        .apply(
            lambda g: pd.Series(
                {
                    "推奨頻度": len(g),
                    "的中率": float(g["is_win"].mean()),
                    "回収率": float(
                        (g["is_win"] * g["odds"] * 100).sum() / (len(g) * 100)
                    ),
                }
            ),
            include_groups=False,
        )
        .reindex(order)
    )
    return agg


def ev_filter_analysis(
    test_df: pd.DataFrame,
    pred_df: pd.DataFrame,
    thresholds: list[float] | None = None,
) -> pd.DataFrame:
    """期待値フィルタ付き回収率分析。

    ``win_prob × odds > threshold`` で絞り込んだ場合の
    的中率・回収率・カバレッジを複数閾値で算出する。

    バックテスト（train_mode）では ``test_df["odds"]`` として
    確定オッズ（``race_results.odds``）を使用する。これが回収率測定の基準値となる。
    予測時（predict_mode）では事前オッズ（``pre_race_odds.win_odds``）を使うため、
    この関数は直接呼ばず ``output.py`` 経由で EV を算出すること。

    Parameters
    ----------
    test_df : pd.DataFrame
        テストデータ（race_id, horse_number, is_win, odds を含む）
    pred_df : pd.DataFrame
        予測結果（race_id, horse_number, win_prob を含む）
    thresholds : list[float] | None
        期待値の閾値リスト。None の場合はデフォルト値を使用。

    Returns
    -------
    pd.DataFrame
        各閾値での 推奨数・的中数・的中率・回収率・カバレッジ
    """
    if thresholds is None:
        thresholds = [1.0, 1.2, 1.5, 2.0, 3.0]

    merged = test_df[["race_id", "horse_number", "is_win", "odds"]].merge(
        pred_df[["race_id", "horse_number", "win_prob"]],
        on=["race_id", "horse_number"],
    )
    merged["odds"] = pd.to_numeric(merged["odds"], errors="coerce")
    merged["ev"] = merged["win_prob"] * merged["odds"]

    total_races = merged["race_id"].nunique()

    rows = []
    for thr in thresholds:
        filtered = merged[merged["ev"] > thr]
        n = len(filtered)
        if n == 0:
            rows.append(
                {
                    "threshold": thr,
                    "推奨数": 0,
                    "的中数": 0,
                    "的中率": float("nan"),
                    "回収率": float("nan"),
                    "カバレッジ": 0.0,
                }
            )
            continue

        wins = int(filtered["is_win"].sum())
        win_rate = float(filtered["is_win"].mean())
        recovered = float((filtered["is_win"] * filtered["odds"] * 100).sum())
        recovery_rate = recovered / (n * 100)
        covered_races = filtered["race_id"].nunique()
        coverage = covered_races / total_races if total_races > 0 else 0.0

        rows.append(
            {
                "threshold": thr,
                "推奨数": n,
                "的中数": wins,
                "的中率": win_rate,
                "回収率": recovery_rate,
                "カバレッジ": coverage,
            }
        )

    return pd.DataFrame(rows).set_index("threshold")


def calibration_curve(
    test_df: pd.DataFrame,
    pred_df: pd.DataFrame,
    n_bins: int = 10,
) -> dict[str, pd.DataFrame]:
    """予測確率ビン別の実測勝率（キャリブレーションカーブ）を算出する。

    Parameters
    ----------
    test_df : pd.DataFrame
        テストデータ（race_id, horse_number, is_win, is_placed を含む）
    pred_df : pd.DataFrame
        予測結果（race_id, horse_number, win_prob, place_prob を含む）
    n_bins : int
        確率を分割するビン数。デフォルト 10（等幅）。

    Returns
    -------
    dict[str, pd.DataFrame]
        win   : 単勝モデルのキャリブレーション
        place : 複勝モデルのキャリブレーション

        各 DataFrame のカラム:
            bin_center  : ビン中央値（予測確率軸）
            mean_pred   : ビン内の予測確率の平均
            actual_rate : ビン内の実際の的中率（実測勝率 / 複勝率）
            count       : ビン内のサンプル数
    """
    merged = test_df[["race_id", "horse_number", "is_win", "is_placed"]].merge(
        pred_df[["race_id", "horse_number", "win_prob", "place_prob"]],
        on=["race_id", "horse_number"],
    )

    def _calc(prob_col: str, actual_col: str) -> pd.DataFrame:
        labels, _ = pd.cut(
            merged[prob_col], bins=n_bins, include_lowest=True, retbins=True
        )
        tmp = merged[[prob_col, actual_col]].copy()
        tmp["_bin"] = labels
        grouped = tmp.groupby("_bin", observed=True).agg(
            mean_pred=(prob_col, "mean"),
            actual_rate=(actual_col, "mean"),
            count=(actual_col, "count"),
        )
        grouped["bin_center"] = [
            (iv.left + iv.right) / 2 for iv in grouped.index
        ]
        return grouped.reset_index(drop=True)[
            ["bin_center", "mean_pred", "actual_rate", "count"]
        ]

    return {
        "win": _calc("win_prob", "is_win"),
        "place": _calc("place_prob", "is_placed"),
    }


def analyze_calibration_bias(
    calib: dict[str, pd.DataFrame],
) -> dict[str, dict]:
    """キャリブレーションカーブからズレ（過信／過小評価）を分析する。

    Parameters
    ----------
    calib : dict[str, pd.DataFrame]
        ``calibration_curve`` の返り値（win / place キー）

    Returns
    -------
    dict[str, dict]
        win / place それぞれの分析結果:
            signed_bias      : 加重平均バイアス（正=過信, 負=過小評価）
            mean_calib_error : 加重平均較正誤差（絶対値）
            needs_calibration: 較正を推奨するかどうか (bool)
            summary          : 人間向けサマリ文字列
    """
    THRESHOLD_BIAS = 0.01  # |signed_bias| がこれを超えたら要較正
    THRESHOLD_MCE = 0.02   # mean_calib_error がこれを超えたら要較正

    result: dict[str, dict] = {}
    for key in ("win", "place"):
        df = calib[key].dropna(subset=["mean_pred", "actual_rate"])
        if df.empty or df["count"].sum() == 0:
            result[key] = {
                "signed_bias": float("nan"),
                "mean_calib_error": float("nan"),
                "needs_calibration": False,
                "summary": "データ不足のため評価不可",
            }
            continue

        weights = df["count"].astype(float)
        total_w = weights.sum()
        diff = df["mean_pred"] - df["actual_rate"]
        signed_bias = float((diff * weights).sum() / total_w)
        mce = float((diff.abs() * weights).sum() / total_w)

        needs_calibration = abs(signed_bias) > THRESHOLD_BIAS or mce > THRESHOLD_MCE

        if needs_calibration:
            direction = "過信（過大評価）" if signed_bias > 0 else "過小評価"
            summary = (
                f"{direction}: signed_bias={signed_bias:+.4f}, MCE={mce:.4f}"
                " → 確率較正（Isotonic / Platt）を推奨"
            )
        else:
            summary = (
                f"較正誤差は軽微: signed_bias={signed_bias:+.4f}, MCE={mce:.4f}"
                " → 較正不要"
            )

        result[key] = {
            "signed_bias": signed_bias,
            "mean_calib_error": mce,
            "needs_calibration": needs_calibration,
            "summary": summary,
        }
    return result

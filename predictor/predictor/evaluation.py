"""モデル評価モジュール"""

from __future__ import annotations

import numpy as np
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


def _pop_tier(p: float) -> str:
    """人気帯ラベルを返す。"""
    if p == 1:
        return "1番人気"
    elif p <= 3:
        return "2-3番人気"
    elif p <= 6:
        return "4-6番人気"
    else:
        return "7番人気以下"


_POP_TIER_ORDER = ["1番人気", "2-3番人気", "4-6番人気", "7番人気以下"]


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
    """期待値フィルタ付き回収率分析（EV閾値 × 人気帯の2軸グリッド）。

    ``win_prob × odds > threshold`` で絞り込んだ場合の
    的中率・回収率・カバレッジを「EV閾値 × 人気帯」の2軸グリッドで算出する。

    バックテスト（train_mode）では ``test_df["odds"]`` として
    確定オッズ（``race_results.odds``）を使用する。これが回収率測定の基準値となる。
    予測時（predict_mode）では事前オッズ（``pre_race_odds.win_odds``）を使うため、
    この関数は直接呼ばず ``output.py`` 経由で EV を算出すること。

    Parameters
    ----------
    test_df : pd.DataFrame
        テストデータ（race_id, horse_number, is_win, odds を含む。
        popularity カラムがある場合は人気帯別集計も行う）
    pred_df : pd.DataFrame
        予測結果（race_id, horse_number, win_prob を含む）
    thresholds : list[float] | None
        期待値の閾値リスト。None の場合はデフォルト値を使用。

    Returns
    -------
    pd.DataFrame
        MultiIndex（threshold, 人気帯）を持つ DataFrame。
        カラム: 推奨数・的中数・的中率・回収率・カバレッジ。
        人気帯は「全体」「1番人気」「2-3番人気」「4-6番人気」「7番人気以下」。
        popularity カラムが test_df にない場合は「全体」行のみ返す。
    """
    if thresholds is None:
        thresholds = [1.0, 1.2, 1.5, 2.0, 3.0]

    use_popularity = "popularity" in test_df.columns
    test_cols = ["race_id", "horse_number", "is_win", "odds"]
    if use_popularity:
        test_cols.append("popularity")

    merged = test_df[test_cols].merge(
        pred_df[["race_id", "horse_number", "win_prob"]],
        on=["race_id", "horse_number"],
    )
    merged["odds"] = pd.to_numeric(merged["odds"], errors="coerce")
    merged["ev"] = merged["win_prob"] * merged["odds"]

    if use_popularity:
        merged["popularity"] = pd.to_numeric(merged["popularity"], errors="coerce")
        merged["popularity_tier"] = merged["popularity"].map(_pop_tier)

    total_races = merged["race_id"].nunique()

    def _stats(df: pd.DataFrame, thr: float, tier: str) -> dict:
        n = len(df)
        if n == 0:
            return {
                "threshold": thr,
                "人気帯": tier,
                "推奨数": 0,
                "的中数": 0,
                "的中率": float("nan"),
                "回収率": float("nan"),
                "カバレッジ": 0.0,
            }
        wins = int(df["is_win"].sum())
        recovered = float((df["is_win"] * df["odds"] * 100).sum())
        coverage = df["race_id"].nunique() / total_races if total_races > 0 else 0.0
        return {
            "threshold": thr,
            "人気帯": tier,
            "推奨数": n,
            "的中数": wins,
            "的中率": float(df["is_win"].mean()),
            "回収率": recovered / (n * 100),
            "カバレッジ": coverage,
        }

    tier_order = ["全体"] + _POP_TIER_ORDER
    rows = []
    for thr in thresholds:
        filtered = merged[merged["ev"] > thr]
        rows.append(_stats(filtered, thr, "全体"))
        if use_popularity:
            for tier in _POP_TIER_ORDER:
                rows.append(
                    _stats(filtered[filtered["popularity_tier"] == tier], thr, tier)
                )

    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["人気帯"] = pd.Categorical(df["人気帯"], categories=tier_order, ordered=True)
    return df.set_index(["threshold", "人気帯"])


def bootstrap_recovery_ci(
    is_win: "pd.Series | np.ndarray",
    odds: "pd.Series | np.ndarray",
    n_bootstrap: int = 10_000,
    ci: float = 0.95,
    random_state: int | None = None,
) -> dict[str, float]:
    """回収率の bootstrap 信頼区間を算出する。

    ベット単位でリサンプリング（復元抽出）し、回収率の分布を推定する。
    数千ベット規模を想定（n < 500 程度では信頼区間が広くなる）。

    Parameters
    ----------
    is_win : array-like
        的中フラグ（1=的中, 0=外れ）
    odds : array-like
        払戻オッズ
    n_bootstrap : int
        ブートストラップ試行回数。デフォルト 10000。
    ci : float
        信頼区間の幅（例: 0.95 = 95%信頼区間）。
    random_state : int | None
        乱数シード。再現性が必要な場合に指定。

    Returns
    -------
    dict[str, float]
        point_estimate : 実データから計算した回収率
        ci_lower       : 信頼区間下限
        ci_upper       : 信頼区間上限
        ci_level       : 信頼水準（例: 0.95）
        n_bets         : ベット数
        above_100      : 信頼区間下限 > 1.0（有意にプラス）
        above_110      : 信頼区間下限 > 1.1（110%以上が誤差でない）
    """
    w = np.asarray(is_win, dtype=float)
    o = np.asarray(odds, dtype=float)
    n = len(w)

    if n == 0:
        return {
            "point_estimate": float("nan"),
            "ci_lower": float("nan"),
            "ci_upper": float("nan"),
            "ci_level": ci,
            "n_bets": 0,
            "above_100": False,
            "above_110": False,
        }

    # 点推定（実データの回収率）
    point_estimate = float((w * o).sum() / n)

    # bootstrap
    rng = np.random.default_rng(random_state)
    boot_rates = np.empty(n_bootstrap, dtype=float)
    for i in range(n_bootstrap):
        idx = rng.integers(0, n, size=n)
        boot_rates[i] = (w[idx] * o[idx]).mean()

    alpha = 1.0 - ci
    ci_lower = float(np.percentile(boot_rates, 100 * alpha / 2))
    ci_upper = float(np.percentile(boot_rates, 100 * (1 - alpha / 2)))

    return {
        "point_estimate": point_estimate,
        "ci_lower": ci_lower,
        "ci_upper": ci_upper,
        "ci_level": ci,
        "n_bets": n,
        "above_100": ci_lower > 1.0,
        "above_110": ci_lower > 1.1,
    }


def ev_filter_bootstrap_ci(
    test_df: pd.DataFrame,
    pred_df: pd.DataFrame,
    thresholds: list[float] | None = None,
    n_bootstrap: int = 10_000,
    ci: float = 0.95,
    random_state: int | None = None,
) -> pd.DataFrame:
    """EV閾値 × 人気帯ごとの回収率 bootstrap 信頼区間を算出する。

    ``ev_filter_analysis`` と同じフィルタリングロジックを用い、
    各セルの回収率に対して bootstrap 信頼区間を付与する。

    Parameters
    ----------
    test_df : pd.DataFrame
        ``ev_filter_analysis`` と同じ形式のテストデータ
    pred_df : pd.DataFrame
        ``ev_filter_analysis`` と同じ形式の予測データ
    thresholds : list[float] | None
        EV閾値リスト。None の場合はデフォルト値を使用。
    n_bootstrap : int
        ブートストラップ試行回数。デフォルト 10000。
    ci : float
        信頼水準。デフォルト 0.95（95%信頼区間）。
    random_state : int | None
        乱数シード。

    Returns
    -------
    pd.DataFrame
        MultiIndex（threshold, 人気帯）を持つ DataFrame。
        カラム: 推奨数・回収率・CI下限・CI上限・有意>100%・有意>110%。
        人気帯は「全体」「1番人気」「2-3番人気」「4-6番人気」「7番人気以下」。
        popularity カラムが test_df にない場合は「全体」行のみ。
    """
    if thresholds is None:
        thresholds = [1.0, 1.2, 1.5, 2.0, 3.0]

    use_popularity = "popularity" in test_df.columns
    test_cols = ["race_id", "horse_number", "is_win", "odds"]
    if use_popularity:
        test_cols.append("popularity")

    merged = test_df[test_cols].merge(
        pred_df[["race_id", "horse_number", "win_prob"]],
        on=["race_id", "horse_number"],
    )
    merged["odds"] = pd.to_numeric(merged["odds"], errors="coerce")
    merged["ev"] = merged["win_prob"] * merged["odds"]

    if use_popularity:
        merged["popularity"] = pd.to_numeric(merged["popularity"], errors="coerce")
        merged["popularity_tier"] = merged["popularity"].map(_pop_tier)

    def _row(df: pd.DataFrame, thr: float, tier: str) -> dict:
        result = bootstrap_recovery_ci(
            df["is_win"],
            df["odds"],
            n_bootstrap=n_bootstrap,
            ci=ci,
            random_state=random_state,
        )
        return {
            "threshold": thr,
            "人気帯": tier,
            "推奨数": result["n_bets"],
            "回収率": result["point_estimate"],
            f"CI下限({int(ci*100)}%)": result["ci_lower"],
            f"CI上限({int(ci*100)}%)": result["ci_upper"],
            "有意>100%": result["above_100"],
            "有意>110%": result["above_110"],
        }

    tier_order = ["全体"] + _POP_TIER_ORDER
    rows = []
    for thr in thresholds:
        filtered = merged[merged["ev"] > thr]
        rows.append(_row(filtered, thr, "全体"))
        if use_popularity:
            for tier in _POP_TIER_ORDER:
                rows.append(
                    _row(filtered[filtered["popularity_tier"] == tier], thr, tier)
                )

    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["人気帯"] = pd.Categorical(df["人気帯"], categories=tier_order, ordered=True)
    return df.set_index(["threshold", "人気帯"])


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
        grouped["bin_center"] = [(iv.left + iv.right) / 2 for iv in grouped.index]
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
    THRESHOLD_MCE = 0.02  # mean_calib_error がこれを超えたら要較正

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


# ---------------------------------------------------------------------------
# 券種別回収率評価（payoffs テーブル活用）
# ---------------------------------------------------------------------------


def _normalize_combination(combo: str) -> str:
    """組合せ文字列を正規化（馬番を昇順ソート）。

    例: ``'7-3'`` → ``'3-7'``, ``'3-1-7'`` → ``'1-3-7'``
    """
    parts = [p.strip() for p in str(combo).split("-")]
    try:
        parts_int = [int(p) for p in parts]
        parts_int.sort()
        return "-".join(str(p) for p in parts_int)
    except ValueError:
        return str(combo)


def _parse_payout(payout_str: str) -> float:
    """払戻金額文字列を数値に変換。例: ``'1,310'`` → ``1310.0``"""
    try:
        return float(str(payout_str).replace(",", ""))
    except (ValueError, AttributeError):
        return float("nan")


def multi_bet_recovery_analysis(
    test_df: pd.DataFrame,
    pred_df: pd.DataFrame,
    payoffs_df: pd.DataFrame,
) -> pd.DataFrame:
    """単勝以外の券種（複勝・馬連・三連複）の回収率を評価する。

    各レースでモデル予測に基づいて買い目を1点選択し、
    ``payoffs`` テーブルの実際の払戻と照合して回収率を算出する。

    選択ルール:
    - 複勝  : place_prob 最大の馬 1 頭
    - 馬連  : win_prob 上位 2 頭（組合せ1点）
    - 三連複 : win_prob 上位 3 頭（組合せ1点）

    Parameters
    ----------
    test_df : pd.DataFrame
        テストデータ（race_id, horse_number を含む）
    pred_df : pd.DataFrame
        予測結果（race_id, horse_number, win_prob, place_prob を含む）
    payoffs_df : pd.DataFrame
        払戻データ（race_id, bet_type, combination, payout を含む）

    Returns
    -------
    pd.DataFrame
        券種別の集計（index: 券種）。
        カラム: 推奨数・的中数・的中率・回収率
    """
    merged = test_df[["race_id", "horse_number"]].merge(
        pred_df[["race_id", "horse_number", "win_prob", "place_prob"]],
        on=["race_id", "horse_number"],
    )
    # horse_number を整数に統一（組合せ文字列の生成に使用）
    merged["hn_int"] = (
        pd.to_numeric(merged["horse_number"], errors="coerce").fillna(0).astype(int)
    )

    # payoffs データを正規化して検索マップを構築
    payoffs = payoffs_df.copy()
    payoffs["payout_value"] = payoffs["payout"].apply(_parse_payout)
    payoffs["combination_norm"] = payoffs["combination"].apply(_normalize_combination)
    payoff_map: dict[tuple[str, str, str], float] = payoffs.set_index(
        ["race_id", "bet_type", "combination_norm"]
    )["payout_value"].to_dict()

    rows = []

    # --- 複勝 ---
    place_idx = merged.groupby("race_id")["place_prob"].idxmax()
    place_picks = merged.loc[place_idx].copy()
    place_picks["combo_norm"] = place_picks["hn_int"].astype(str)
    place_picks["payout_val"] = place_picks.apply(
        lambda r: payoff_map.get((r["race_id"], "複勝", r["combo_norm"]), float("nan")),
        axis=1,
    )
    place_picks["is_hit"] = place_picks["payout_val"].notna()
    n = len(place_picks)
    hits = int(place_picks["is_hit"].sum())
    recovered = float(place_picks["payout_val"].fillna(0).sum())
    rows.append(
        {
            "券種": "複勝",
            "推奨数": n,
            "的中数": hits,
            "的中率": hits / n if n > 0 else float("nan"),
            "回収率": recovered / (n * 100) if n > 0 else float("nan"),
        }
    )

    # --- 馬連 ---
    quinella_rows: list[dict] = []
    for race_id, group in merged.groupby("race_id"):
        top2 = group.nlargest(2, "win_prob")
        if len(top2) < 2:
            continue
        nums = sorted(top2["hn_int"].tolist())
        combo = f"{nums[0]}-{nums[1]}"
        payout = payoff_map.get((race_id, "馬連", combo), float("nan"))
        quinella_rows.append(
            {"race_id": race_id, "payout": payout, "is_hit": not pd.isna(payout)}
        )
    if quinella_rows:
        qdf = pd.DataFrame(quinella_rows)
        n = len(qdf)
        hits = int(qdf["is_hit"].sum())
        recovered = float(qdf["payout"].fillna(0).sum())
        rows.append(
            {
                "券種": "馬連",
                "推奨数": n,
                "的中数": hits,
                "的中率": hits / n if n > 0 else float("nan"),
                "回収率": recovered / (n * 100) if n > 0 else float("nan"),
            }
        )

    # --- 三連複 ---
    trio_rows: list[dict] = []
    for race_id, group in merged.groupby("race_id"):
        top3 = group.nlargest(3, "win_prob")
        if len(top3) < 3:
            continue
        nums = sorted(top3["hn_int"].tolist())
        combo = f"{nums[0]}-{nums[1]}-{nums[2]}"
        payout = payoff_map.get((race_id, "三連複", combo), float("nan"))
        trio_rows.append(
            {"race_id": race_id, "payout": payout, "is_hit": not pd.isna(payout)}
        )
    if trio_rows:
        tdf = pd.DataFrame(trio_rows)
        n = len(tdf)
        hits = int(tdf["is_hit"].sum())
        recovered = float(tdf["payout"].fillna(0).sum())
        rows.append(
            {
                "券種": "三連複",
                "推奨数": n,
                "的中数": hits,
                "的中率": hits / n if n > 0 else float("nan"),
                "回収率": recovered / (n * 100) if n > 0 else float("nan"),
            }
        )

    result = pd.DataFrame(rows)
    if result.empty:
        return result
    return result.set_index("券種")


def walk_forward_summary(
    fold_results: list[dict],
) -> pd.DataFrame:
    """Walk-forward 検証の各フォールド結果をまとめた DataFrame を返す。

    Parameters
    ----------
    fold_results : list[dict]
        各フォールドの結果 dict のリスト。各 dict は以下のキーを持つ:
            fold          : フォールド番号（1 始まり）
            train_rows    : 学習データ行数
            test_rows     : テストデータ行数
            test_start    : テスト期間の開始日（str）
            test_end      : テスト期間の終了日（str）
            win_accuracy  : 単勝的中率
            recovery_rate : 単勝回収率
            win_brier     : 単勝 Brier score
            place_brier   : 複勝 Brier score
            win_logloss   : 単勝 log-loss
            place_logloss : 複勝 log-loss

    Returns
    -------
    pd.DataFrame
        フォールドを行、指標を列とした DataFrame。
        末尾に全フォールド平均行（fold='mean'）を付加する。
    """
    if not fold_results:
        return pd.DataFrame()

    df = pd.DataFrame(fold_results).set_index("fold")

    metric_cols = [
        "win_accuracy",
        "recovery_rate",
        "win_brier",
        "place_brier",
        "win_logloss",
        "place_logloss",
    ]
    existing_metrics = [c for c in metric_cols if c in df.columns]

    mean_row = df[existing_metrics].mean().to_frame().T
    mean_row.index = pd.Index(["mean"])
    mean_row["train_rows"] = float("nan")
    mean_row["test_rows"] = float("nan")
    mean_row["test_start"] = ""
    mean_row["test_end"] = ""

    summary = pd.concat([df, mean_row])
    return summary


# ---------------------------------------------------------------------------
# EV閾値 × 人気帯 × 券種 の3軸グリッド回収率評価
# ---------------------------------------------------------------------------


def ev_multi_bet_grid(
    test_df: pd.DataFrame,
    pred_df: pd.DataFrame,
    payoffs_df: pd.DataFrame,
    thresholds: list[float] | None = None,
) -> pd.DataFrame:
    """EV閾値 × 人気帯 × 券種 の3軸グリッドで回収率を算出する。

    EV = win_prob × win_odds（確定オッズ）でフィルタリングし、
    単勝・複勝・馬連・三連複の回収率を各セルで集計する。

    各券種の選択ルール（フィルタを通過したレースに対して）:

    - 単勝  : フィルタ通過馬を単勝で買う
    - 複勝  : フィルタ通過馬を複勝で買う
    - 馬連  : top-1 馬がフィルタ通過 → top-2 で馬連 1 点
    - 三連複 : top-1 馬がフィルタ通過 → top-3 で三連複 1 点

    フィルタ条件: win_prob × win_odds > threshold かつ 人気帯が一致

    Parameters
    ----------
    test_df : pd.DataFrame
        テストデータ（race_id, horse_number, is_win, odds を含む。
        popularity カラムがある場合は人気帯別集計も行う）
    pred_df : pd.DataFrame
        予測結果（race_id, horse_number, win_prob, place_prob を含む）
    payoffs_df : pd.DataFrame
        払戻データ（race_id, bet_type, combination, payout を含む）
    thresholds : list[float] | None
        EV閾値リスト。None の場合はデフォルト値を使用。

    Returns
    -------
    pd.DataFrame
        MultiIndex（threshold, 人気帯, 券種）を持つ DataFrame。
        カラム: 推奨数・的中数・的中率・回収率
    """
    if thresholds is None:
        thresholds = [1.0, 1.2, 1.5, 2.0, 3.0]

    use_popularity = "popularity" in test_df.columns
    test_cols = ["race_id", "horse_number", "is_win", "odds"]
    if use_popularity:
        test_cols.append("popularity")

    merged = test_df[test_cols].merge(
        pred_df[["race_id", "horse_number", "win_prob", "place_prob"]],
        on=["race_id", "horse_number"],
    )
    merged["odds"] = pd.to_numeric(merged["odds"], errors="coerce")
    merged["ev"] = merged["win_prob"] * merged["odds"]
    merged["hn_int"] = (
        pd.to_numeric(merged["horse_number"], errors="coerce").fillna(0).astype(int)
    )

    if use_popularity:
        merged["popularity"] = pd.to_numeric(merged["popularity"], errors="coerce")
        merged["popularity_tier"] = merged["popularity"].map(_pop_tier)

    # payoffs 正規化マップを構築
    payoffs = payoffs_df.copy()
    payoffs["payout_value"] = payoffs["payout"].apply(_parse_payout)
    payoffs["combination_norm"] = payoffs["combination"].apply(_normalize_combination)
    payoff_map: dict[tuple[str, str, str], float] = payoffs.set_index(
        ["race_id", "bet_type", "combination_norm"]
    )["payout_value"].to_dict()

    bet_types = ["単勝", "複勝", "馬連", "三連複"]
    tier_order = ["全体"] + _POP_TIER_ORDER

    def _stats_for_races(race_ids: set, base_df: pd.DataFrame, bet_type: str) -> dict:
        """指定レースIDセットに対して bet_type の回収率統計を返す。"""
        sub = base_df[base_df["race_id"].isin(race_ids)]

        if bet_type == "単勝":
            n = len(sub)
            if n == 0:
                return {
                    "推奨数": 0,
                    "的中数": 0,
                    "的中率": float("nan"),
                    "回収率": float("nan"),
                }
            wins = int(sub["is_win"].sum())
            recovered = float((sub["is_win"] * sub["odds"] * 100).sum())
            return {
                "推奨数": n,
                "的中数": wins,
                "的中率": wins / n,
                "回収率": recovered / (n * 100),
            }

        elif bet_type == "複勝":
            # フィルタ通過馬（1頭）を複勝で購入
            n = len(sub)
            if n == 0:
                return {
                    "推奨数": 0,
                    "的中数": 0,
                    "的中率": float("nan"),
                    "回収率": float("nan"),
                }
            hits = 0
            recovered = 0.0
            for _, row in sub.iterrows():
                combo = str(int(row["hn_int"]))
                payout = payoff_map.get((row["race_id"], "複勝", combo), float("nan"))
                if not pd.isna(payout):
                    hits += 1
                    recovered += payout
            return {
                "推奨数": n,
                "的中数": hits,
                "的中率": hits / n,
                "回収率": recovered / (n * 100),
            }

        elif bet_type == "馬連":
            # フィルタ通過レースで win_prob 上位2頭の馬連1点を購入
            sub_races = merged[merged["race_id"].isin(race_ids)]
            rows_list = []
            for race_id, group in sub_races.groupby("race_id"):
                top2 = group.nlargest(2, "win_prob")
                if len(top2) < 2:
                    continue
                nums = sorted(top2["hn_int"].tolist())
                combo = f"{nums[0]}-{nums[1]}"
                payout = payoff_map.get((race_id, "馬連", combo), float("nan"))
                rows_list.append({"payout": payout, "is_hit": not pd.isna(payout)})
            if not rows_list:
                return {
                    "推奨数": 0,
                    "的中数": 0,
                    "的中率": float("nan"),
                    "回収率": float("nan"),
                }
            qdf = pd.DataFrame(rows_list)
            n = len(qdf)
            hits = int(qdf["is_hit"].sum())
            recovered = float(qdf["payout"].fillna(0).sum())
            return {
                "推奨数": n,
                "的中数": hits,
                "的中率": hits / n,
                "回収率": recovered / (n * 100),
            }

        elif bet_type == "三連複":
            # フィルタ通過レースで win_prob 上位3頭の三連複1点を購入
            sub_races = merged[merged["race_id"].isin(race_ids)]
            rows_list = []
            for race_id, group in sub_races.groupby("race_id"):
                top3 = group.nlargest(3, "win_prob")
                if len(top3) < 3:
                    continue
                nums = sorted(top3["hn_int"].tolist())
                combo = f"{nums[0]}-{nums[1]}-{nums[2]}"
                payout = payoff_map.get((race_id, "三連複", combo), float("nan"))
                rows_list.append({"payout": payout, "is_hit": not pd.isna(payout)})
            if not rows_list:
                return {
                    "推奨数": 0,
                    "的中数": 0,
                    "的中率": float("nan"),
                    "回収率": float("nan"),
                }
            tdf = pd.DataFrame(rows_list)
            n = len(tdf)
            hits = int(tdf["is_hit"].sum())
            recovered = float(tdf["payout"].fillna(0).sum())
            return {
                "推奨数": n,
                "的中数": hits,
                "的中率": hits / n,
                "回収率": recovered / (n * 100),
            }

        return {
            "推奨数": 0,
            "的中数": 0,
            "的中率": float("nan"),
            "回収率": float("nan"),
        }

    rows = []
    for thr in thresholds:
        # EV > threshold のフィルタ通過馬（各レースで win_prob 最大馬かつ EV 閾値以上）
        # ※ 全馬に対してフィルタをかけると1レースに複数馬が通過する場合があるため、
        #    各レースの top-1 馬が閾値を超えるかどうかで判定する
        top1_idx = merged.groupby("race_id")["win_prob"].idxmax()
        top1 = merged.loc[top1_idx].copy()
        filtered_top1 = top1[top1["ev"] > thr]

        for tier in tier_order:
            if tier == "全体":
                tier_top1 = filtered_top1
            elif use_popularity:
                tier_top1 = filtered_top1[filtered_top1["popularity_tier"] == tier]
            else:
                continue

            race_ids = set(tier_top1["race_id"].tolist())

            for bet_type in bet_types:
                stats = _stats_for_races(race_ids, tier_top1, bet_type)
                rows.append(
                    {
                        "threshold": thr,
                        "人気帯": tier,
                        "券種": bet_type,
                        **stats,
                    }
                )

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    tier_cat = tier_order if use_popularity else ["全体"]
    df["人気帯"] = pd.Categorical(df["人気帯"], categories=tier_cat, ordered=True)
    df["券種"] = pd.Categorical(df["券種"], categories=bet_types, ordered=True)
    return df.set_index(["threshold", "人気帯", "券種"])

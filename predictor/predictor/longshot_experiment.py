"""7番人気以下（穴馬）専用モデルの比較実験スクリプト。

「オッズが一定以上の馬が勝った/3着内に入ったレースだけに学習を絞る」という案は
目的変数（勝敗）で学習データを選別することになり、予測時には知り得ない情報で
サンプルを選ぶ selection-on-the-outcome に当たるため機能しない。

代わりに、目的変数を使わず予測前に分かる情報（人気＝オッズ順位）だけで
学習に使う「行」を絞る、健全なバージョンを検証する。全馬で学習した baseline と、
popularity >= 7 の行だけで学習した longshot 専用モデルを、同じテストデータの
7番人気以下の行に対する win_logloss / win_brier で比較する。
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

import pandas as pd
from sklearn.metrics import brier_score_loss, log_loss

from predictor import calibration, model

logger = logging.getLogger(__name__)

_OUTPUT_DIR = Path(__file__).parent.parent.parent / "output"

LONGSHOT_MIN_POPULARITY = 7  # 7番人気以下


def _filter_longshot(df: pd.DataFrame) -> pd.DataFrame:
    """popularity（人気＝オッズ順位）が LONGSHOT_MIN_POPULARITY 以上の行だけを残す。"""
    popularity = pd.to_numeric(df["popularity"], errors="coerce")
    return df[popularity >= LONGSHOT_MIN_POPULARITY]


def _longshot_metrics(test_df: pd.DataFrame, pred_df: pd.DataFrame) -> dict[str, float]:
    """テストデータのうち7番人気以下の行に絞った win_logloss / win_brier を計算する。"""
    merged = test_df[["race_id", "horse_number", "is_win", "popularity"]].merge(
        pred_df[["race_id", "horse_number", "win_prob"]],
        on=["race_id", "horse_number"],
    )
    merged["popularity"] = pd.to_numeric(merged["popularity"], errors="coerce")
    sub = merged[merged["popularity"] >= LONGSHOT_MIN_POPULARITY].dropna(
        subset=["win_prob", "is_win"]
    )
    if sub.empty:
        return {"n": 0, "win_logloss": float("nan"), "win_brier": float("nan")}
    return {
        "n": len(sub),
        "win_logloss": log_loss(sub["is_win"], sub["win_prob"], labels=[0, 1]),
        "win_brier": brier_score_loss(sub["is_win"], sub["win_prob"]),
    }


def run_comparison(
    train_df: pd.DataFrame,
    val_df: pd.DataFrame,
    test_df: pd.DataFrame,
    half_life_days: float | None = 1095.0,
) -> pd.DataFrame:
    """baseline（全馬で学習）と longshot 専用（人気薄の行だけで学習）を比較する。

    どちらも train_df のみを学習に使い、val_df で較正する（時系列リークなし）。
    比較対象は test_df のうち popularity >= 7 の行に絞った win_logloss / win_brier。

    Parameters
    ----------
    train_df, val_df, test_df : pd.DataFrame
        ``split_by_date`` で分割済みのデータ。
    half_life_days : float | None
        ``model.train`` に渡す時間減衰の半減期。本番のデフォルトと合わせておく。

    Returns
    -------
    pd.DataFrame
        index がモデル名、列が n（対象行数）・win_logloss・win_brier。
    """
    rows = []

    logger.info("baseline モデルを学習中（全馬）...")
    baseline_models = model.train(train_df, half_life_days=half_life_days)
    baseline_calibrated = calibration.calibrate_models(baseline_models, val_df)
    baseline_pred = model.predict(baseline_calibrated, test_df)
    rows.append(
        {"model": "baseline（全馬で学習）", **_longshot_metrics(test_df, baseline_pred)}
    )

    train_longshot = _filter_longshot(train_df)
    val_longshot = _filter_longshot(val_df)
    logger.info(
        f"longshot専用モデルを学習中（popularity>={LONGSHOT_MIN_POPULARITY} の行のみ、"
        f"{len(train_longshot):,} / {len(train_df):,} 行）..."
    )
    longshot_models = model.train(train_longshot, half_life_days=half_life_days)
    longshot_calibrated = calibration.calibrate_models(longshot_models, val_longshot)
    longshot_pred = model.predict(longshot_calibrated, test_df)
    rows.append(
        {
            "model": f"longshot専用（popularity>={LONGSHOT_MIN_POPULARITY}のみ学習）",
            **_longshot_metrics(test_df, longshot_pred),
        }
    )

    return pd.DataFrame(rows).set_index("model")


def save_comparison(df: pd.DataFrame, output_dir: Path = _OUTPUT_DIR) -> Path:
    """比較結果を CSV に保存し、保存先パスを返す。"""
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = output_dir / f"longshot_specialization_comparison_{timestamp}.csv"
    df.to_csv(path)
    return path

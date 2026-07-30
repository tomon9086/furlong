"""time_decay half_life_days の比較実験スクリプト。

複数の ``half_life_days`` 値（半減期）で学習・較正・評価を行い、
Log Loss・回収率などの指標を比較する。結果は CSV に保存する。
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

import pandas as pd

from predictor import calibration, evaluation, model

logger = logging.getLogger(__name__)

_OUTPUT_DIR = Path(__file__).parent.parent.parent / "output"

# ラベル: (表示名, half_life_days)。None = 重みなし（従来挙動相当）。
DEFAULT_HALF_LIFE_OPTIONS: list[tuple[str, float | None]] = [
    ("1年", 365.0),
    ("3年", 1095.0),
    ("5年", 1825.0),
    ("10年", 3650.0),
    ("無限大(重みなし)", None),
]


def run_comparison(
    train_df: pd.DataFrame,
    val_df: pd.DataFrame,
    test_df: pd.DataFrame,
    half_life_options: list[tuple[str, float | None]] | None = None,
) -> pd.DataFrame:
    """複数の half_life_days で学習・較正・評価し、比較結果を DataFrame で返す。

    Parameters
    ----------
    train_df, val_df, test_df : pd.DataFrame
        ``split_by_date`` で分割済みのデータ（train で学習、val で較正、test で評価）。
    half_life_options : list[tuple[str, float | None]] | None
        (表示ラベル, half_life_days) のリスト。``None`` の場合はデフォルト
        （1年・3年・5年・10年・無限大）を使う。

    Returns
    -------
    pd.DataFrame
        index が half_life_days のラベル、列が ``evaluation.evaluate`` の指標
        （win_accuracy, recovery_rate, win_logloss, place_logloss,
        win_brier, place_brier）。
    """
    if half_life_options is None:
        half_life_options = DEFAULT_HALF_LIFE_OPTIONS

    rows = []
    for label, half_life_days in half_life_options:
        logger.info(f"学習中: half_life_days={label}")
        models = model.train(train_df, half_life_days=half_life_days)
        calibrated = calibration.calibrate_models(models, val_df)
        pred_df = model.predict(calibrated, test_df)
        metrics = evaluation.evaluate(test_df, pred_df)
        rows.append({"half_life_days": label, **metrics})

    return pd.DataFrame(rows).set_index("half_life_days")


def save_comparison(df: pd.DataFrame, output_dir: Path = _OUTPUT_DIR) -> Path:
    """比較結果を CSV に保存し、保存先パスを返す。"""
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = output_dir / f"half_life_comparison_{timestamp}.csv"
    df.to_csv(path)
    return path

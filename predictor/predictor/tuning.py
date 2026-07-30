"""Optuna によるハイパーパラメータ最適化。

LightGBM のハイパーパラメータ（``num_leaves``, ``learning_rate``,
``min_child_samples``, ``feature_fraction``）と時間減衰ウェイトの
``half_life_days`` を同時に探索する。

評価指標は walk-forward（expanding window）複数フォールドの平均回収率。
精度（Log Loss）ではなく回収率を最大化する（回収率が本プロジェクトの目標指標のため）。
"""

from __future__ import annotations

import logging

import optuna
import pandas as pd

from predictor import evaluation, model
from predictor.calibration import calibrate_models
from predictor.preprocessing import walk_forward_splits

logger = logging.getLogger(__name__)

# None = 重みなし（時間減衰を適用しない）を探索空間に含める。
HALF_LIFE_CHOICES: list[float | None] = [365.0, 1095.0, 1825.0, 3650.0, None]

# optuna.Trial.suggest_categorical は None を含むリストを受け付けないため、
# 内部的には文字列 "none" にマッピングして扱う。
_HALF_LIFE_LABELS: dict[str, float | None] = {
    "365": 365.0,
    "1095": 1095.0,
    "1825": 1825.0,
    "3650": 3650.0,
    "none": None,
}


def _objective(trial: optuna.Trial, df: pd.DataFrame, n_splits: int) -> float:
    shared_params = {
        "num_leaves": trial.suggest_int("num_leaves", 15, 255),
        "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.2, log=True),
        "min_child_samples": trial.suggest_int("min_child_samples", 5, 100),
        "feature_fraction": trial.suggest_float("feature_fraction", 0.5, 1.0),
    }
    half_life_label = trial.suggest_categorical(
        "half_life_days", list(_HALF_LIFE_LABELS.keys())
    )
    half_life_days = _HALF_LIFE_LABELS[half_life_label]

    splits = walk_forward_splits(df, n_splits=n_splits)
    recovery_rates = []
    for wf_train, wf_test in splits:
        models = model.train(
            wf_train,
            half_life_days=half_life_days,
            win_params=shared_params,
            place_params=shared_params,
        )
        calibrated = calibrate_models(models, wf_test)
        pred_df = model.predict(calibrated, wf_test)
        metrics = evaluation.evaluate(wf_test, pred_df)
        recovery_rates.append(metrics["recovery_rate"])

    return sum(recovery_rates) / len(recovery_rates)


def run_tuning(df: pd.DataFrame, n_trials: int = 30, n_splits: int = 3) -> optuna.Study:
    """walk-forward 平均回収率を最大化する Optuna study を実行する。

    Parameters
    ----------
    df : pd.DataFrame
        前処理・近走成績計算済みの全学習データ
        （``preprocess`` → ``compute_recent_stats`` 後、``split_by_date`` 前）。
    n_trials : int
        Optuna の試行回数。デフォルト 30。
    n_splits : int
        walk-forward の分割数。1 トライアルにつき ``n_splits`` 回の全量学習が
        走るため、本番の検証（5 分割）より少なめの値をデフォルトにしている。

    Returns
    -------
    optuna.Study
        ``study.best_params`` に最良パラメータ（``half_life_days`` は文字列ラベル）、
        ``study.best_value`` に最良の walk-forward 平均回収率が入る。
    """
    study = optuna.create_study(direction="maximize")
    study.optimize(lambda trial: _objective(trial, df, n_splits), n_trials=n_trials)

    logger.info(f"最良パラメータ: {study.best_params}")
    logger.info(f"最良スコア（walk-forward平均回収率）: {study.best_value:.4f}")
    return study


def best_half_life_days(study: optuna.Study) -> float | None:
    """study の最良パラメータから half_life_days の実数値（または None）を取り出す。"""
    return _HALF_LIFE_LABELS[study.best_params["half_life_days"]]

"""Optuna によるハイパーパラメータ最適化。

LightGBM のハイパーパラメータ（``num_leaves``, ``learning_rate``,
``min_child_samples``, ``feature_fraction``）と時間減衰ウェイトの
``half_life_days`` を同時に探索する。

評価指標は walk-forward（expanding window）複数フォールドの平均 Log Loss（``win_logloss``）。
本プロジェクトの目標指標は回収率だが、回収率は分散が大きく、小さい探索予算
（``n_trials`` × ``n_splits``）で直接最適化すると特定の fold 構成のノイズに
過学習しやすいことが判明している（``docs/experiments.md`` の 2026-07-30 の検証結果、
Optuna で見つけた「最良パラメータ」が通常の train/val/test split では悪化した）。
そのため探索自体は分散の小さい Log Loss を最小化し、各 trial の回収率は
``user_attrs["recovery_rate"]`` に記録するだけに留める。探索後に
``top_trials()`` で Log Loss 上位の候補と回収率を並べて確認し、Log Loss が
悪化していない範囲で回収率が良いものを人手で選ぶ（簡易的なパレート確認）。
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
    win_loglosses = []
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
        win_loglosses.append(metrics["win_logloss"])
        recovery_rates.append(metrics["recovery_rate"])

    # 目的関数（Log Loss）ではなく参考情報として回収率を記録する。
    trial.set_user_attr("recovery_rate", sum(recovery_rates) / len(recovery_rates))

    return sum(win_loglosses) / len(win_loglosses)


def run_tuning(df: pd.DataFrame, n_trials: int = 30, n_splits: int = 3) -> optuna.Study:
    """walk-forward 平均 Log Loss（win_logloss）を最小化する Optuna study を実行する。

    回収率ではなく Log Loss を目的関数にする理由はモジュール docstring を参照。
    各 trial の walk-forward 平均回収率は ``trial.user_attrs["recovery_rate"]`` に
    記録されるので、``top_trials()`` で Log Loss と回収率を並べて確認できる。

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
        ``study.best_value`` に最良の walk-forward 平均 win_logloss が入る。
    """
    study = optuna.create_study(direction="minimize")
    study.optimize(lambda trial: _objective(trial, df, n_splits), n_trials=n_trials)

    logger.info(f"最良パラメータ: {study.best_params}")
    logger.info(f"最良スコア（walk-forward平均win_logloss）: {study.best_value:.4f}")
    logger.info(
        "  （参考）対応する回収率: "
        f"{study.best_trial.user_attrs['recovery_rate']:.4f}"
    )
    return study


def top_trials(study: optuna.Study, n: int = 5) -> list[dict]:
    """win_logloss が良い順に上位 n 件を、対応する回収率つきで返す。

    Log Loss 最小化のみで探索した結果から、Log Loss が悪化していない範囲で
    回収率が良いものを人手で選ぶための一覧（簡易的なパレート確認）。
    """
    completed = [t for t in study.trials if t.value is not None]
    ranked = sorted(completed, key=lambda t: t.value)
    return [
        {
            "number": t.number,
            "win_logloss": t.value,
            "recovery_rate": t.user_attrs.get("recovery_rate"),
            "params": t.params,
        }
        for t in ranked[:n]
    ]


def best_half_life_days(study: optuna.Study) -> float | None:
    """study の最良パラメータから half_life_days の実数値（または None）を取り出す。"""
    return _HALF_LIFE_LABELS[study.best_params["half_life_days"]]

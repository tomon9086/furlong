"""LightGBM 予測モデル"""

from __future__ import annotations

import pickle
from datetime import datetime
from pathlib import Path
from typing import NamedTuple

import lightgbm as lgb
import pandas as pd

from predictor.calibration import CalibratedModels
from predictor.preprocessing import get_feature_columns

_MODEL_DIR = Path(__file__).parent.parent / "models"

_PARAMS: dict = {
    "objective": "binary",
    "metric": "binary_logloss",
    "verbosity": -1,
    "learning_rate": 0.05,
    "num_leaves": 63,
    "feature_fraction": 0.8,
    "bagging_fraction": 0.8,
    "bagging_freq": 5,
    "min_child_samples": 20,
}

_NUM_BOOST_ROUND = 500


class Models(NamedTuple):
    win: lgb.Booster
    place: lgb.Booster


def _build_dataset(df: pd.DataFrame, label_col: str) -> lgb.Dataset:
    features = get_feature_columns()
    available = [f for f in features if f in df.columns]
    X = df[available].copy()
    cat_cols = [c for c in X.columns if X[c].dtype.name == "category"]
    return lgb.Dataset(
        X,
        label=df[label_col],
        categorical_feature=cat_cols if cat_cols else "auto",
        free_raw_data=False,
    )


def train(train_df: pd.DataFrame) -> Models:
    """学習データで勝ち・複勝 LightGBM モデルを学習する。"""
    win_ds = _build_dataset(train_df, "is_win")
    place_ds = _build_dataset(train_df, "is_placed")

    win_model = lgb.train(_PARAMS, win_ds, num_boost_round=_NUM_BOOST_ROUND)
    place_model = lgb.train(_PARAMS, place_ds, num_boost_round=_NUM_BOOST_ROUND)

    return Models(win=win_model, place=place_model)


def save_models(
    models: Models,
    metrics: dict | None = None,
    model_dir: Path = _MODEL_DIR,
) -> Path:
    """モデルをタイムスタンプ付きディレクトリに保存する。"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    version_dir = model_dir / timestamp
    version_dir.mkdir(parents=True, exist_ok=True)

    with open(version_dir / "win_model.pkl", "wb") as f:
        pickle.dump(models.win, f)
    with open(version_dir / "place_model.pkl", "wb") as f:
        pickle.dump(models.place, f)

    return version_dir


def save_calibrated_models(
    calibrated: CalibratedModels,
    version_dir: Path,
) -> None:
    """較正済みモデルを指定ディレクトリに保存する。"""
    with open(version_dir / "win_calibrated.pkl", "wb") as f:
        pickle.dump(calibrated.win, f)
    with open(version_dir / "place_calibrated.pkl", "wb") as f:
        pickle.dump(calibrated.place, f)


def load_models(model_dir: Path = _MODEL_DIR) -> Models:
    """保存済みモデルを読み込む（最新のタイムスタンプディレクトリを使用）。"""
    dirs = sorted(d for d in model_dir.iterdir() if d.is_dir())
    if not dirs:
        raise FileNotFoundError(f"モデルが見つかりません: {model_dir}")
    version_dir = dirs[-1]

    with open(version_dir / "win_model.pkl", "rb") as f:
        win = pickle.load(f)
    with open(version_dir / "place_model.pkl", "rb") as f:
        place = pickle.load(f)
    return Models(win=win, place=place)


def load_calibrated_models(model_dir: Path = _MODEL_DIR) -> CalibratedModels:
    """保存済み較正済みモデルを読み込む（較正済みファイルが存在する最新ディレクトリを使用）。"""
    dirs = sorted(d for d in model_dir.iterdir() if d.is_dir())
    if not dirs:
        raise FileNotFoundError(f"モデルが見つかりません: {model_dir}")

    for version_dir in reversed(dirs):
        win_path = version_dir / "win_calibrated.pkl"
        place_path = version_dir / "place_calibrated.pkl"
        if win_path.exists() and place_path.exists():
            with open(win_path, "rb") as f:
                win = pickle.load(f)
            with open(place_path, "rb") as f:
                place = pickle.load(f)
            return CalibratedModels(win=win, place=place)

    raise FileNotFoundError(f"較正済みモデルが見つかりません: {model_dir}")


def predict(models: Models | CalibratedModels, df: pd.DataFrame) -> pd.DataFrame:
    """予測確率と予測着順を付与した DataFrame を返す。"""
    if isinstance(models, CalibratedModels):
        from predictor.calibration import predict_calibrated

        win_probs, place_probs = predict_calibrated(models, df)
    else:
        features = get_feature_columns()
        available = [f for f in features if f in df.columns]
        X = df[available].copy()
        win_probs = models.win.predict(X)
        place_probs = models.place.predict(X)

    result = df[["race_id", "horse_number", "horse_id"]].copy()
    if "horse_name" in df.columns:
        result["horse_name"] = df["horse_name"].values
    result["win_prob"] = win_probs
    result["win_prob"] = result["win_prob"] / result.groupby("race_id")[
        "win_prob"
    ].transform("sum")
    result["place_prob"] = place_probs
    result["predicted_rank"] = (
        result.groupby("race_id")["win_prob"]
        .rank(ascending=False, method="min")
        .astype(int)
    )

    if "win_odds" in df.columns:
        result["win_odds"] = pd.to_numeric(df["win_odds"].values, errors="coerce")
    elif "odds" in df.columns:
        result["odds"] = pd.to_numeric(df["odds"].values, errors="coerce")

    return result

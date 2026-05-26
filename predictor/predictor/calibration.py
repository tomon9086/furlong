"""確率較正モジュール

CalibratedClassifierCV（Isotonic / Platt）で win / place モデルを後段較正する。
較正は ``cv="prefit"`` を使用するため、渡すデータは学習に使っていない
保留セット（テストセット等）であること。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, NamedTuple

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, ClassifierMixin
from sklearn.calibration import CalibratedClassifierCV

from predictor.preprocessing import get_feature_columns

if TYPE_CHECKING:
    import lightgbm as lgb

    from predictor.model import Models


class _LGBMBoosterWrapper(BaseEstimator, ClassifierMixin):
    """lgb.Booster を sklearn の ClassifierMixin に準拠させるラッパー。

    CalibratedClassifierCV(cv="prefit") で使用するための最小実装。
    """

    def __init__(self, booster: lgb.Booster) -> None:
        self.booster = booster
        self.classes_ = np.array([0, 1])

    def fit(self, X, y):
        # cv="prefit" では呼ばれない。sklearn API 規約のために定義。
        return self

    def predict(self, X):
        proba = self.booster.predict(X)
        return (proba >= 0.5).astype(int)

    def predict_proba(self, X):
        proba = self.booster.predict(X)
        return np.column_stack([1 - proba, proba])


class CalibratedModels(NamedTuple):
    """較正済みモデルのペア。"""

    win: CalibratedClassifierCV
    place: CalibratedClassifierCV


def _extract_features(df: pd.DataFrame) -> pd.DataFrame:
    """特徴量カラムのみを抽出した DataFrame を返す。"""
    features = get_feature_columns()
    available = [f for f in features if f in df.columns]
    return df[available].copy()


def calibrate_models(
    models: Models,
    calib_df: pd.DataFrame,
    method: str = "isotonic",
) -> CalibratedModels:
    """win/place モデルを保留セットで後段較正する。

    Parameters
    ----------
    models : predictor.model.Models
        学習済み LightGBM モデル（``model.train`` の戻り値）。
        較正は ``cv="prefit"`` で行うため、``calib_df`` は学習に
        使っていないデータ（テストセット等）を使うこと。
    calib_df : pd.DataFrame
        較正用データ。``is_win`` / ``is_placed`` カラムを含む必要がある。
    method : str
        較正方式。``"isotonic"``（ノンパラメトリック）または
        ``"sigmoid"``（Platt scaling）を指定。
        サンプル数が少ない場合は ``"sigmoid"`` が安定する。

    Returns
    -------
    CalibratedModels
        ``win`` / ``place`` それぞれの :class:`CalibratedClassifierCV` インスタンス。
        ``predict_proba(X)[:, 1]`` で較正済み確率を取得できる。

    Raises
    ------
    ValueError
        ``method`` が ``"isotonic"`` / ``"sigmoid"`` 以外の場合。
    """
    if method not in ("isotonic", "sigmoid"):
        raise ValueError(
            f"method は 'isotonic' または 'sigmoid' のみ指定可能: {method!r}"
        )

    X = _extract_features(calib_df)

    win_wrapper = _LGBMBoosterWrapper(models.win)
    place_wrapper = _LGBMBoosterWrapper(models.place)

    win_calib = CalibratedClassifierCV(win_wrapper, cv="prefit", method=method)
    place_calib = CalibratedClassifierCV(place_wrapper, cv="prefit", method=method)

    win_calib.fit(X, calib_df["is_win"].to_numpy())
    place_calib.fit(X, calib_df["is_placed"].to_numpy())

    return CalibratedModels(win=win_calib, place=place_calib)


def predict_calibrated(
    calibrated: CalibratedModels,
    df: pd.DataFrame,
) -> tuple[np.ndarray, np.ndarray]:
    """較正済みモデルで予測確率を返す。

    Parameters
    ----------
    calibrated : CalibratedModels
        ``calibrate_models`` の戻り値。
    df : pd.DataFrame
        予測対象データ。

    Returns
    -------
    tuple[np.ndarray, np.ndarray]
        ``(win_probs, place_probs)`` の較正済み確率ベクトル。
    """
    X = _extract_features(df)
    win_probs: np.ndarray = calibrated.win.predict_proba(X)[:, 1]
    place_probs: np.ndarray = calibrated.place.predict_proba(X)[:, 1]
    return win_probs, place_probs

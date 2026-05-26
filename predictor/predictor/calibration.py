"""確率較正モジュール

IsotonicRegression（Isotonic）または LogisticRegression（Platt）で
win / place モデルを後段較正する。

較正は学習済み LightGBM モデルの生スコアを保留セット（テストセット等）で
キャリブレータに当てはめることで実行する。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, NamedTuple

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression

from predictor.preprocessing import get_feature_columns

if TYPE_CHECKING:
    from predictor.model import Models


class _Calibrator:
    """生スコア → 較正済み確率 のマッピングを保持するラッパー。

    ``method="isotonic"`` の場合は IsotonicRegression、
    ``method="sigmoid"`` の場合は LogisticRegression（Platt scaling）を使用する。
    """

    def __init__(self, method: str) -> None:
        if method == "isotonic":
            self._model = IsotonicRegression(out_of_bounds="clip")
            self._method = "isotonic"
        elif method == "sigmoid":
            self._model = LogisticRegression(C=1.0)
            self._method = "sigmoid"
        else:
            raise ValueError(
                f"method は 'isotonic' または 'sigmoid' のみ指定可能: {method!r}"
            )

    def fit(self, raw_probs: np.ndarray, y: np.ndarray) -> "_Calibrator":
        if self._method == "isotonic":
            self._model.fit(raw_probs, y)
        else:
            self._model.fit(raw_probs.reshape(-1, 1), y)
        return self

    def predict(self, raw_probs: np.ndarray) -> np.ndarray:
        if self._method == "isotonic":
            return self._model.predict(raw_probs)
        else:
            return self._model.predict_proba(raw_probs.reshape(-1, 1))[:, 1]


class CalibratedModels(NamedTuple):
    """較正済みモデルのペア（較正器 + 元の LightGBM モデル）。"""

    win: _Calibrator
    place: _Calibrator
    raw_win: lgb.Booster
    raw_place: lgb.Booster


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

    学習済み LightGBM モデルの生スコアを保留セットで IsotonicRegression
    または LogisticRegression（Platt scaling）に当てはめることで後段較正を実現する。

    Parameters
    ----------
    models : predictor.model.Models
        学習済み LightGBM モデル（``model.train`` の戻り値）。
        ``calib_df`` は学習に使っていないデータ（テストセット等）を使うこと。
    calib_df : pd.DataFrame
        較正用データ。``is_win`` / ``is_placed`` カラムを含む必要がある。
    method : str
        較正方式。``"isotonic"``（ノンパラメトリック）または
        ``"sigmoid"``（Platt scaling）を指定。
        サンプル数が少ない場合は ``"sigmoid"`` が安定する。

    Returns
    -------
    CalibratedModels
        ``win`` / ``place`` それぞれの :class:`_Calibrator` インスタンス。

    Raises
    ------
    ValueError
        ``method`` が ``"isotonic"`` / ``"sigmoid"`` 以外の場合。
    """
    X = _extract_features(calib_df)

    win_raw = models.win.predict(X)
    place_raw = models.place.predict(X)

    win_calib = _Calibrator(method).fit(win_raw, calib_df["is_win"].to_numpy())
    place_calib = _Calibrator(method).fit(place_raw, calib_df["is_placed"].to_numpy())

    return CalibratedModels(
        win=win_calib, place=place_calib, raw_win=models.win, raw_place=models.place
    )


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
    win_raw: np.ndarray = calibrated.raw_win.predict(X)
    place_raw: np.ndarray = calibrated.raw_place.predict(X)
    win_probs = calibrated.win.predict(win_raw)
    place_probs = calibrated.place.predict(place_raw)
    return win_probs, place_probs

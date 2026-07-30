"""LightGBM 予測モデル"""

from __future__ import annotations

import pickle
from datetime import datetime
from pathlib import Path
from typing import NamedTuple

import lightgbm as lgb
import numpy as np
import pandas as pd

from predictor.calibration import CalibratedModels
from predictor.preprocessing import compute_time_decay_weight, get_feature_columns

_MODEL_DIR = Path(__file__).parent.parent / "models"

# 複勝モデル用パラメータ（binary classification）
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

# 勝ち順位モデル用パラメータ（lambdarank: レース内順位を直接最適化）
_RANK_PARAMS: dict = {
    "objective": "lambdarank",
    "metric": "ndcg",
    "verbosity": -1,
    "learning_rate": 0.05,
    "num_leaves": 63,
    "feature_fraction": 0.8,
    "bagging_fraction": 0.8,
    "bagging_freq": 5,
    "min_child_samples": 20,
    "ndcg_eval_at": [1, 3, 5],
    # 線形ゲイン: 日本競馬の最大出走頭数 18 頭に対応（デフォルトの指数ゲインより均一に寄与）
    "label_gain": list(range(18)),
}

_NUM_BOOST_ROUND = 500


class Models(NamedTuple):
    win: lgb.Booster
    place: lgb.Booster


def _softmax(arr: np.ndarray) -> np.ndarray:
    """数値安定な softmax を返す（lambdarank スコアの確率変換に使用）。"""
    e = np.exp(arr - arr.max())
    return e / e.sum()


def _build_dataset(
    df: pd.DataFrame,
    label_col: str,
    weight: np.ndarray | None = None,
    extra_feature_columns: list[str] | None = None,
) -> lgb.Dataset:
    features = get_feature_columns(extra_columns=extra_feature_columns)
    available = [f for f in features if f in df.columns]
    X = df[available].copy()
    cat_cols = [c for c in X.columns if X[c].dtype.name == "category"]
    return lgb.Dataset(
        X,
        label=df[label_col],
        weight=weight,
        categorical_feature=cat_cols if cat_cols else "auto",
        free_raw_data=False,
    )


def _build_rank_dataset(
    df: pd.DataFrame,
    weight: np.ndarray | None = None,
    extra_feature_columns: list[str] | None = None,
) -> lgb.Dataset:
    """lambdarank 用データセットを構築する（group=レース単位）。

    レース内の着順から関連度ラベルを計算し、レース単位のグループ情報を付与する。
    関連度ラベル: 勝ち馬 = (出走頭数 - 1)、最下位 = 0。
    LightGBM は group 内でのみラベルを比較するため、頭数が異なるレース間での
    ラベル値の差は問題にならない。

    ``weight`` は ``df`` の行順に対応する配列で渡すこと（内部でソート後の順序に
    並び替える）。
    """
    if weight is not None:
        df = df.copy()
        df["_sample_weight"] = weight

    # レース・馬番順にソートしてグループの連続性を保証
    df_s = df.sort_values(["race_id", "horse_number"]).reset_index(drop=True)

    features = get_feature_columns(extra_columns=extra_feature_columns)
    available = [f for f in features if f in df_s.columns]
    X = df_s[available].copy()
    cat_cols = [c for c in X.columns if X[c].dtype.name == "category"]

    # 関連度ラベル: レース内最大着順 - 着順 (非負整数, 勝ち馬が最大値)
    rank_label = (
        df_s.groupby("race_id")["finishing_position"].transform("max")
        - df_s["finishing_position"]
    ).astype(int)

    # グループサイズ: レース単位の出走頭数（race_id 昇順 = df_s の行順と一致）
    group = df_s.groupby("race_id")["horse_number"].count().tolist()

    sorted_weight = df_s["_sample_weight"].to_numpy() if weight is not None else None

    return lgb.Dataset(
        X,
        label=rank_label,
        group=group,
        weight=sorted_weight,
        categorical_feature=cat_cols if cat_cols else "auto",
        free_raw_data=False,
    )


def train(
    train_df: pd.DataFrame,
    half_life_days: float | None = None,
    reference_date: "pd.Timestamp | None" = None,
    win_params: dict | None = None,
    place_params: dict | None = None,
    embedding_feature_columns: list[str] | None = None,
) -> Models:
    """学習データで lambdarank (勝ち順位) と binary (複勝) の LightGBM モデルを学習する。

    勝ちモデル: lambdarank でレース内順位を直接最適化（group=レース単位）。
    複勝モデル: 従来どおり binary classification。

    Parameters
    ----------
    half_life_days : float | None
        指定した場合、レース日付からの経過日数に応じた指数減衰サンプルウェイトを
        適用する（半減期＝指定日数）。``None``（デフォルト）の場合は従来どおり
        重みなしで学習する。
    reference_date : pd.Timestamp | None
        時間減衰の基準日。``None`` の場合は ``train_df["date"]`` の最大値を使う。
    win_params, place_params : dict | None
        LightGBM ハイパーパラメータの上書き（Optuna 連携用）。指定したキーのみ
        デフォルトパラメータに上書きされる。
    embedding_feature_columns : list[str] | None
        ``train_df`` に事前追加済みの Embedding 特徴量カラム名（
        ``embedding_features.add_embedding_features`` の戻り値）。指定した場合、
        既存の特徴量に追加して学習に使う。``None``（デフォルト）の場合は従来どおり。
    """
    weight: np.ndarray | None = None
    if half_life_days is not None:
        if reference_date is None:
            reference_date = train_df["date"].max()
        weight = compute_time_decay_weight(
            train_df["date"], reference_date, half_life_days
        )

    rank_ds = _build_rank_dataset(
        train_df, weight=weight, extra_feature_columns=embedding_feature_columns
    )
    place_ds = _build_dataset(
        train_df,
        "is_placed",
        weight=weight,
        extra_feature_columns=embedding_feature_columns,
    )

    rank_params = {**_RANK_PARAMS, **(win_params or {})}
    bin_params = {**_PARAMS, **(place_params or {})}

    win_model = lgb.train(rank_params, rank_ds, num_boost_round=_NUM_BOOST_ROUND)
    place_model = lgb.train(bin_params, place_ds, num_boost_round=_NUM_BOOST_ROUND)

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
        win_raw_path = version_dir / "win_model.pkl"
        place_raw_path = version_dir / "place_model.pkl"
        if win_path.exists() and place_path.exists():
            with open(win_path, "rb") as f:
                win = pickle.load(f)
            with open(place_path, "rb") as f:
                place = pickle.load(f)
            with open(win_raw_path, "rb") as f:
                raw_win = pickle.load(f)
            with open(place_raw_path, "rb") as f:
                raw_place = pickle.load(f)
            return CalibratedModels(
                win=win, place=place, raw_win=raw_win, raw_place=raw_place
            )

    raise FileNotFoundError(f"較正済みモデルが見つかりません: {model_dir}")


def predict(models: Models | CalibratedModels, df: pd.DataFrame) -> pd.DataFrame:
    """予測確率と予測着順を付与した DataFrame を返す。"""
    if isinstance(models, CalibratedModels):
        from predictor.calibration import predict_calibrated

        win_probs, place_probs = predict_calibrated(models, df)
    else:
        # 学習済み Booster 自身の feature_name() を使う（Embedding 特徴量の
        # 有無に関わらず、学習時に実際に使われたカラム集合と厳密に一致させるため）。
        win_features = [f for f in models.win.feature_name() if f in df.columns]
        place_features = [f for f in models.place.feature_name() if f in df.columns]
        win_probs = models.win.predict(df[win_features])
        place_probs = models.place.predict(df[place_features])

    result = df[["race_id", "horse_number", "horse_id"]].copy()
    if "horse_name" in df.columns:
        result["horse_name"] = df["horse_name"].values
    result["win_prob"] = win_probs
    if isinstance(models, CalibratedModels):
        # 較正済みモデル: [0,1] の較正済み確率をレース内合計で正規化
        result["win_prob"] = result["win_prob"] / result.groupby("race_id")[
            "win_prob"
        ].transform("sum")
    else:
        # 未較正モデル (lambdarank スコアは任意の実数): softmax でレース内正規化
        result["win_prob"] = result.groupby("race_id")["win_prob"].transform(
            lambda g: _softmax(g.to_numpy())
        )
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

    if "weight_carried" in df.columns:
        result["weight_carried"] = pd.to_numeric(df["weight_carried"].values, errors="coerce")

    return result

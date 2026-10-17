"""Plackett-Luce（上位 K 頭の着順の尤度）を目的関数にした LightGBM。

各馬のスコア f を学習し、レース内の softmax を勝率とする。着順は
「残っている馬の中から exp(f) に比例して次の着順の馬が選ばれる」と考え、
上位 K 頭までの着順の対数尤度を最大化する。K=1 なら勝ち馬だけ、
K=3 なら1〜3着の順番まで学習する（三連複・3着内の精度を直接狙う）。

``init_score`` に市場の勝率の log を入れると、学習の出発点が市場になり、
出力は「市場の勝率 × exp(モデルの補正)」をレース内で正規化したものになる
（補正を何も学ばなければ市場そのもの）。LightGBM は予測時に init_score を
足さないので、``predict_win_prob`` に同じものを渡して足し戻す。
"""

from __future__ import annotations

from dataclasses import dataclass

import lightgbm as lgb
import numpy as np
import pandas as pd

from predictor.preprocessing import get_feature_columns

# model.py の _PARAMS（Optuna で探索した値）をベースにする
_BASE_PARAMS: dict = {
    "verbosity": -1,
    "learning_rate": 0.012807161179774155,
    "num_leaves": 127,
    "feature_fraction": 0.5597186764633092,
    "bagging_fraction": 0.8,
    "bagging_freq": 5,
    "min_child_samples": 41,
    "metric": "None",
}


@dataclass
class RaceLayout:
    """レースを (レース数, 最大頭数) の行列に並べるための添字。

    ``index[r, j]`` はレース r の j 頭目に対応する行番号（無ければ -1）。
    ``rank[r, j]`` はその馬の着順（無ければ大きな値）。
    """

    index: np.ndarray
    rank: np.ndarray
    mask: np.ndarray

    @classmethod
    def from_frame(cls, df: pd.DataFrame) -> RaceLayout:
        race_codes, _ = pd.factorize(df["race_id"])
        n_races = race_codes.max() + 1
        order = np.argsort(race_codes, kind="stable")
        counts = np.bincount(race_codes, minlength=n_races)
        max_n = counts.max()
        starts = np.concatenate([[0], np.cumsum(counts)[:-1]])
        pos_in_race = np.arange(len(df)) - np.repeat(starts, counts)

        index = np.full((n_races, max_n), -1, dtype=np.int64)
        index[race_codes[order], pos_in_race] = order
        mask = index >= 0
        positions = df["finishing_position"].to_numpy(dtype=float)
        rank = np.full((n_races, max_n), 1e9)
        rank[mask] = positions[index[mask]]
        return cls(index=index, rank=rank, mask=mask)

    def to_matrix(self, values: np.ndarray, fill: float = 0.0) -> np.ndarray:
        out = np.full(self.index.shape, fill, dtype=float)
        out[self.mask] = values[self.index[self.mask]]
        return out

    def to_rows(self, matrix: np.ndarray, n_rows: int) -> np.ndarray:
        out = np.empty(n_rows)
        out[self.index[self.mask]] = matrix[self.mask]
        return out


def _masked_softmax(scores: np.ndarray, mask: np.ndarray) -> np.ndarray:
    s = np.where(mask, scores, -np.inf)
    s = s - s.max(axis=1, keepdims=True)
    e = np.where(mask, np.exp(s), 0.0)
    return e / e.sum(axis=1, keepdims=True)


def _pl_grad_hess_nll(
    layout: RaceLayout, scores: np.ndarray, top_k: int
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """行列形式のスコアに対する -対数尤度の勾配・対角ヘッセ・レースごとの -対数尤度。"""
    grad = np.zeros_like(scores)
    hess = np.zeros_like(scores)
    nll = np.zeros(scores.shape[0])
    rank = layout.rank
    for k in range(1, top_k + 1):
        remaining = layout.mask & (rank >= k)
        # k 着の馬がいない（頭数不足・同着で番号が飛ぶ）レースはこの段を飛ばす
        chosen = layout.mask & (rank == k)
        has_k = chosen.any(axis=1)
        if not has_k.any():
            continue
        p = _masked_softmax(scores, remaining)
        p = np.where(has_k[:, None], p, 0.0)
        grad += p - np.where(has_k[:, None], chosen, False)
        hess += p * (1.0 - p)
        chosen_p = np.where(chosen, p, 0.0).sum(axis=1)
        nll += np.where(has_k, -np.log(np.clip(chosen_p, 1e-300, None)), 0.0)
    return grad, hess, nll


def make_objective(layout: RaceLayout, top_k: int, weight: np.ndarray | None):
    """LightGBM の自作目的関数（preds は行順の生スコア、init_score を含む）。"""
    n_rows = int(layout.mask.sum())
    w_matrix = layout.to_matrix(weight, 0.0) if weight is not None else None

    def objective(preds: np.ndarray, _dataset: lgb.Dataset):
        scores = layout.to_matrix(preds)
        grad, hess, _ = _pl_grad_hess_nll(layout, scores, top_k)
        if w_matrix is not None:
            grad *= w_matrix
            hess *= w_matrix
        hess = np.maximum(hess, 1e-6)
        return layout.to_rows(grad, n_rows), layout.to_rows(hess, n_rows)

    return objective


def make_eval(layout: RaceLayout, top_k: int, name: str):
    """検証用の評価関数（レース平均の -対数尤度、小さいほど良い）。"""

    def feval(preds: np.ndarray, _dataset: lgb.Dataset):
        _, _, nll = _pl_grad_hess_nll(layout, layout.to_matrix(preds), top_k)
        return name, float(nll.mean()), False

    return feval


def _features(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    available = [f for f in get_feature_columns() if f in df.columns]
    X = df[available]
    cat_cols = [c for c in X.columns if X[c].dtype.name == "category"]
    return X, cat_cols


def train_pl(
    train_df: pd.DataFrame,
    val_df: pd.DataFrame,
    top_k: int,
    init_train: np.ndarray | None = None,
    init_val: np.ndarray | None = None,
    weight: np.ndarray | None = None,
    num_boost_round: int = 5000,
    early_stopping_rounds: int = 200,
    params: dict | None = None,
) -> lgb.Booster:
    """Plackett-Luce（上位 top_k 頭）で学習する。木の本数は val の尤度で早期終了。

    ``init_train``・``init_val`` は各行の初期スコア（例: 市場の勝率の log）。
    """
    X_train, cat_cols = _features(train_df)
    X_val, _ = _features(val_df)
    train_set = lgb.Dataset(
        X_train,
        label=train_df["finishing_position"].to_numpy(dtype=float),
        init_score=init_train,
        categorical_feature=cat_cols or "auto",
        free_raw_data=False,
    )
    val_set = lgb.Dataset(
        X_val,
        label=val_df["finishing_position"].to_numpy(dtype=float),
        init_score=init_val,
        reference=train_set,
        categorical_feature=cat_cols or "auto",
        free_raw_data=False,
    )
    train_layout = RaceLayout.from_frame(train_df)
    val_layout = RaceLayout.from_frame(val_df)
    full_params = {
        **_BASE_PARAMS,
        **(params or {}),
        "objective": make_objective(train_layout, top_k, weight),
    }
    return lgb.train(
        full_params,
        train_set,
        num_boost_round=num_boost_round,
        valid_sets=[val_set],
        valid_names=["val"],
        feval=make_eval(val_layout, top_k, f"pl_top{top_k}_nll"),
        callbacks=[lgb.early_stopping(early_stopping_rounds, verbose=False)],
    )


def predict_win_prob(
    booster: lgb.Booster, df: pd.DataFrame, init: np.ndarray | None = None
) -> np.ndarray:
    """各行の勝率（レース内 softmax）を返す。init は学習時と同じ初期スコア。"""
    X, _ = _features(df)
    scores = booster.predict(X, num_iteration=booster.best_iteration)
    if init is not None:
        scores = scores + init
    layout = RaceLayout.from_frame(df)
    probs = _masked_softmax(layout.to_matrix(scores), layout.mask)
    return layout.to_rows(probs, len(df))

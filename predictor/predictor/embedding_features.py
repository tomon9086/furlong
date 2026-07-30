"""学習済み Embedding ベクトルを LightGBM 特徴量として統合するモジュール。

``embedding.py`` で学習・保存した ID → ベクトルの辞書を読み込み、カテゴリ ID から
ベクトルを引いて数値列として DataFrame に追加する。未知 ID（学習データに存在しない
ID）はカテゴリごとの平均ベクトル（``"__mean__"``）にフォールバックする。

**重要**: このモジュールは torch に依存しない（``embedding_common.py`` からのみ
定数を読む）。LightGBM の学習・推論パス（``model.py`` 経由）で使われるため、
torch を import する ``embedding.py`` を直接 import しないこと（同一プロセスで
torch と lightgbm を読み込むと OpenMP ランタイムの競合でセグメンテーション違反が
発生することを確認済み）。
"""

from __future__ import annotations

import pickle
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.decomposition import PCA

from predictor.embedding_common import EMBEDDING_DIR, TARGET_CATEGORIES

__all__ = [
    "TARGET_CATEGORIES",
    "load_embeddings",
    "apply_pca",
    "add_embedding_features",
]


def load_embeddings(
    embedding_dir: Path = EMBEDDING_DIR,
) -> dict[str, dict[str, np.ndarray]]:
    """保存済み Embedding のうち最新のものを読み込む。

    Returns
    -------
    dict[str, dict[str, np.ndarray]]
        category 名 →
        {id 文字列: ベクトル, ``"__mean__"``: フォールバック用平均ベクトル}
    """
    if not embedding_dir.exists():
        raise FileNotFoundError(f"学習済み Embedding が見つかりません: {embedding_dir}")
    dirs = sorted(d for d in embedding_dir.iterdir() if d.is_dir())
    if not dirs:
        raise FileNotFoundError(f"学習済み Embedding が見つかりません: {embedding_dir}")
    version_dir = dirs[-1]
    with open(version_dir / "embeddings.pkl", "rb") as f:
        return pickle.load(f)


def apply_pca(
    embeddings: dict[str, dict[str, np.ndarray]], n_components: int
) -> dict[str, dict[str, np.ndarray]]:
    """各カテゴリの Embedding テーブルを PCA で圧縮する。

    ``"__mean__"`` を含む全ベクトルに対して同一の PCA 変換を適用するため、
    フォールバック時のベクトルも一貫した空間に射影される。

    Parameters
    ----------
    embeddings : dict[str, dict[str, np.ndarray]]
        ``load_embeddings`` の戻り値。
    n_components : int
        圧縮後の次元数。元の次元数より大きい場合は元の次元数に丸める。

    Returns
    -------
    dict[str, dict[str, np.ndarray]]
        圧縮後の Embedding（同じキー構造）。
    """
    reduced: dict[str, dict[str, np.ndarray]] = {}
    for category, table in embeddings.items():
        keys = list(table.keys())
        matrix = np.stack([table[k] for k in keys])
        n_comp = min(n_components, matrix.shape[1])
        pca = PCA(n_components=n_comp)
        reduced_matrix = pca.fit_transform(matrix)
        reduced[category] = {k: reduced_matrix[i] for i, k in enumerate(keys)}
    return reduced


def add_embedding_features(
    df: pd.DataFrame,
    embeddings: dict[str, dict[str, np.ndarray]],
    categories: list[str] | None = None,
) -> tuple[pd.DataFrame, list[str]]:
    """カテゴリ ID から Embedding ベクトルを引いて数値列として追加する。

    未知 ID（``embeddings[category]`` に存在しない ID）や欠損値は、そのカテゴリの
    平均ベクトル（``"__mean__"``）にフォールバックする。

    Parameters
    ----------
    df : pd.DataFrame
        対象データ（``categories`` のカラムを含む）。
    embeddings : dict[str, dict[str, np.ndarray]]
        ``load_embeddings`` または ``apply_pca`` の戻り値。
    categories : list[str] | None
        対象カテゴリ列名。``None`` の場合は ``TARGET_CATEGORIES``。

    Returns
    -------
    tuple[pd.DataFrame, list[str]]
        (Embedding 列を追加した DataFrame のコピー, 追加した列名のリスト)
    """
    if categories is None:
        categories = TARGET_CATEGORIES

    df = df.copy()
    new_columns: list[str] = []
    for category in categories:
        if category not in embeddings or category not in df.columns:
            continue
        table = embeddings[category]
        mean_vec = table["__mean__"]
        dim = len(mean_vec)
        col_names = [f"{category}_emb_{i}" for i in range(dim)]

        vectors = np.stack(
            [
                table.get(str(v), mean_vec) if pd.notna(v) else mean_vec
                for v in df[category]
            ]
        )
        for i, col in enumerate(col_names):
            df[col] = vectors[:, i]
        new_columns.extend(col_names)

    return df, new_columns

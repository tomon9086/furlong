"""騎手ID・調教師ID・血統IDの Entity Embedding 学習（PyTorch）。

各カテゴリ変数を ``nn.Embedding`` で低次元ベクトルに変換し、複勝（``is_placed``）
予測を補助タスクとして End-to-End に学習する。学習済みベクトルは ID → ベクトルの
辞書として pickle 保存し、LightGBM の特徴量として後段（``embedding_features.py``）で
利用する。

学習・GBDT 学習は別プロセス。Embedding は ``split_by_date`` の train 部分のみで
学習し（val/test への情報リークを防ぐため）、``python -m predictor.main
train-embeddings`` で実行する。

**重要**: このモジュールは torch に依存する。torch と lightgbm を同一プロセスで
読み込むと OpenMP ランタイムの競合により ``lgb.Dataset.construct()`` がセグメン
テーション違反を起こすことを確認しているため、LightGBM の学習・推論パス
（``model.py`` 等）からは絶対にこのモジュールを import しないこと。定数のみが
必要な場合は torch 非依存の ``embedding_common.py`` を参照する。
"""

from __future__ import annotations

import logging
import pickle
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

from predictor.embedding_common import EMBEDDING_DIR, TARGET_CATEGORIES

logger = logging.getLogger(__name__)

__all__ = [
    "EMBEDDING_DIR",
    "TARGET_CATEGORIES",
    "auto_embedding_dim",
    "train_embeddings",
    "save_embeddings",
]


def auto_embedding_dim(cardinality: int) -> int:
    """カーディナリティから経験則で Embedding 次元数を決める。

    ``min(50, cardinality**0.25 * 4)`` を最も近い整数に丸め、最低 2 次元とする。
    """
    dim = round(min(50.0, cardinality**0.25 * 4))
    return max(2, dim)


class _EntityEmbeddingNet(nn.Module):
    """複数カテゴリ変数の Embedding を連結し、複勝を予測する補助タスクモデル。"""

    def __init__(self, cardinalities: dict[str, int]) -> None:
        super().__init__()
        self.categories = list(cardinalities.keys())
        self.embeddings = nn.ModuleDict(
            {
                cat: nn.Embedding(card, auto_embedding_dim(card))
                for cat, card in cardinalities.items()
            }
        )
        total_dim = sum(self.embeddings[cat].embedding_dim for cat in self.categories)
        self.head = nn.Sequential(
            nn.Linear(total_dim, 32),
            nn.ReLU(),
            nn.Linear(32, 1),
        )

    def forward(self, inputs: dict[str, torch.Tensor]) -> torch.Tensor:
        embedded = [self.embeddings[cat](inputs[cat]) for cat in self.categories]
        x = torch.cat(embedded, dim=1)
        return self.head(x).squeeze(-1)


def _build_vocab(series: pd.Series) -> dict[str, int]:
    """カテゴリ値 → 連番インデックスの辞書を作る（欠損値は除外）。"""
    values = series.dropna().astype(str).unique()
    return {v: i for i, v in enumerate(sorted(values))}


def train_embeddings(
    df: pd.DataFrame,
    categories: list[str] | None = None,
    epochs: int = 5,
    batch_size: int = 4096,
    lr: float = 1e-3,
    device: str = "cpu",
) -> dict[str, dict[str, np.ndarray]]:
    """カテゴリ変数の Embedding を PyTorch で学習し、ID → ベクトルの辞書を返す。

    補助タスクは複勝（``is_placed``）予測（``BCEWithLogitsLoss``）。

    Parameters
    ----------
    df : pd.DataFrame
        ``preprocess`` 済みのデータ（``is_placed`` と対象カテゴリ列を含む）。
        val/test へのリークを避けるため、時系列分割の train 部分のみを渡すこと。
    categories : list[str] | None
        Embedding 対象のカテゴリ列名。``None`` の場合は ``TARGET_CATEGORIES``。
    epochs, batch_size, lr : 学習ハイパーパラメータ。
    device : str
        ``"cpu"`` または ``"cuda"``。

    Returns
    -------
    dict[str, dict[str, np.ndarray]]
        category 名 →
        {id 文字列: ベクトル, ``"__mean__"``: フォールバック用平均ベクトル}
    """
    if categories is None:
        categories = TARGET_CATEGORIES

    work = df.dropna(subset=["is_placed"] + categories).copy()
    vocabs = {cat: _build_vocab(work[cat]) for cat in categories}
    cardinalities = {cat: len(vocab) for cat, vocab in vocabs.items()}
    for cat, card in cardinalities.items():
        dim = auto_embedding_dim(card)
        logger.info(f"  {cat}: カーディナリティ={card}, embedding次元={dim}")

    inputs = {
        cat: torch.tensor(
            work[cat].astype(str).map(vocabs[cat]).to_numpy(), dtype=torch.long
        )
        for cat in categories
    }
    target = torch.tensor(work["is_placed"].to_numpy(), dtype=torch.float32)

    dataset = TensorDataset(*[inputs[cat] for cat in categories], target)
    loader = DataLoader(dataset, batch_size=batch_size, shuffle=True)

    net = _EntityEmbeddingNet(cardinalities).to(device)
    optimizer = torch.optim.Adam(net.parameters(), lr=lr)
    loss_fn = nn.BCEWithLogitsLoss()

    net.train()
    for epoch in range(epochs):
        total_loss = 0.0
        n_batches = 0
        for *cat_batches, y_batch in loader:
            batch_inputs = {
                cat: cat_batches[i].to(device) for i, cat in enumerate(categories)
            }
            y_batch = y_batch.to(device)

            optimizer.zero_grad()
            logits = net(batch_inputs)
            loss = loss_fn(logits, y_batch)
            loss.backward()
            optimizer.step()

            total_loss += loss.item()
            n_batches += 1
        logger.info(f"  epoch {epoch + 1}/{epochs}: loss={total_loss / n_batches:.4f}")

    net.eval()
    result: dict[str, dict[str, np.ndarray]] = {}
    with torch.no_grad():
        for cat in categories:
            weight = net.embeddings[cat].weight.detach().cpu().numpy()
            id_to_vec = {id_str: weight[idx] for id_str, idx in vocabs[cat].items()}
            id_to_vec["__mean__"] = weight.mean(axis=0)
            result[cat] = id_to_vec

    return result


def save_embeddings(
    embeddings: dict[str, dict[str, np.ndarray]],
    embedding_dir: Path = EMBEDDING_DIR,
) -> Path:
    """学習済み Embedding をタイムスタンプ付きディレクトリに pickle 保存する。"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    version_dir = embedding_dir / timestamp
    version_dir.mkdir(parents=True, exist_ok=True)
    with open(version_dir / "embeddings.pkl", "wb") as f:
        pickle.dump(embeddings, f)
    return version_dir

"""embedding.py / embedding_features.py で共有する定数。

``embedding.py``（PyTorch 依存）と ``embedding_features.py``（LightGBM 学習・
推論パスから呼ばれる）を分離するためのモジュール。torch と lightgbm を同一
プロセスで読み込むと、このリポジトリの環境では OpenMP ランタイムの競合により
``lgb.Dataset.construct()`` がセグメンテーション違反を起こすことを確認している。
``embedding_features.py`` がこのモジュール経由で定数を参照することで、
学習・推論の通常フローが torch を読み込まずに済むようにする。
"""

from __future__ import annotations

from pathlib import Path

EMBEDDING_DIR = Path(__file__).parent.parent / "embeddings"

# Embedding 学習対象カテゴリ（騎手ID・調教師ID・父馬名・母父馬名）。
TARGET_CATEGORIES: list[str] = ["jockey_id", "trainer_id", "sire", "broodmare_sire"]

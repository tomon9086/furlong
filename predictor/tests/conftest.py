"""pytest 共通設定。

torch と lightgbm を同一プロセスで使うと、この環境（macOS）では OpenMP
ランタイムの競合により ``lgb.Dataset.construct()`` がセグメンテーション違反を
起こすことを確認している（``import torch`` 後に ``lgb.Dataset(...).construct()``
を呼ぶだけで再現する）。テストスイートは torch 依存の ``test_embedding.py`` と
lightgbm 依存の ``test_model.py`` を同一セッションで実行するため、プロセス全体を
OpenMP シングルスレッドに固定して回避する（テストデータは小規模なため速度への
影響は無視できる）。

本番の学習・推論パス（``model.py`` / ``embedding_features.py``）は torch を
import しない設計にしているため、この制約は本番コードには影響しない
（``embedding.py`` を直接 import する ``train-embeddings`` コマンドのみ torch を
使うが、lightgbm とは別プロセスで実行される）。
"""

import os

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

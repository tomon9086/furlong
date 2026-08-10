# ADR-0011: Embeddingハイブリッド特徴量は導入しない

- Status: Rejected
- Date: 2026-07-31

## Context

騎手ID・調教師ID・父馬名・母父馬名の Entity Embedding を PyTorch で学習し（train部分のみ、リーク防止）、LightGBM に統合する効果を検証した。生の73次元Embeddingと、4カテゴリ×6次元=24列に PCA 圧縮した版の2パターンを比較した。

## Decision

Embeddingハイブリッドはデフォルトで無効（`use_embeddings=False`）を維持する。実装（`embedding.py`, `embedding_features.py`, `--use-embeddings` フラグ）は非破壊的に残す。

## Consequences

- 生の73次元版は全指標で悪化。PCA圧縮24次元版は回収率のみ+1.4pt改善、Log Lossは横ばい〜微悪化。
- baseline [73.16%, 83.50%] と Embedding+PCA [74.36%, 85.38%] の95%bootstrap CIはほぼ全域が重なり、+1.4ptの改善は統計的に有意でないと判断。
- 両設定ともCI上限が100%を下回り、単勝top1戦略はどちらも高い確度で損失側。

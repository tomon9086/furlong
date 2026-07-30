# 時間減衰重み付け + Embeddingハイブリッド（検討中）

> このファイルは探索・議論の場です。決定前のアイデアや選択肢を自由に書いてください。
> 確定した仕様は `spec.md` に移してください。

---

## 背景

30年分・70万レースの学習データには非定常性（馬場改修・血統トレンド変化・騎手世代交代等）があり、均等重み学習は古いパターンを過剰学習するリスクがある。既存パイプラインへの非破壊的な追加として、(1) 時間減衰サンプルウェイト、(2) 騎手/調教師/血統IDのEmbeddingハイブリッドを段階的に導入する。

優先順位: タスク1（時間減衰）→ 検証 → タスク2（Embedding）。

## 既存実装の確認結果（前提）

- 学習データの日付列は `races.date`（`YYYY/MM/DD` 文字列）。`preprocessing.preprocess()` で `date` 列として `pd.to_datetime` 済み（[preprocessing.py](../../predictor/predictor/preprocessing.py)）。
- 学習データ読み込み: `load_data()` → `preprocess()` → `compute_recent_stats()` → `split_by_date()`（train/val/test 時系列3分割）。
- モデル学習: `model.train(train_df)` が `_build_rank_dataset`（lambdarank, 勝ちモデル）と `_build_dataset`（binary, 複勝モデル）を組み立てて `lgb.train` を呼ぶ。どちらも `lgb.Dataset` 作成時に `weight=` を渡せる（LightGBM 標準機能）。
- 既存の Optuna 連携は **存在しない**（`docs/todo.md` に「Optuna によるハイパーパラメータ最適化」が未着手タスクとして記載されているのみ）。新規に `predictor/predictor/tuning.py` を追加する。
- 評価の主指標は **回収率**（[[project_recovery_rate_goal]] 参照）。Optuna の目的関数も walk-forward 平均回収率を採用する（`docs/todo.md` の既存方針と整合）。
- カテゴリ変数 `jockey_id`, `trainer_id`, `sire`, `dam`, `broodmare_sire` はすでに `category` dtype で LightGBM のネイティブカテゴリ分割に渡っている（Embeddingハイブリッドは、これを置き換えるのではなく低次元ベクトルを**追加の数値特徴量**として増設する非破壊的な形にする）。

## タスク1の設計判断

- `compute_time_decay_weight(race_date, reference_date, half_life_days)` を `preprocessing.py` に追加（ユーザー指定の式をそのまま採用）。
- `reference_date` のデフォルトは学習データ（`train_df`）の `date.max()`。
- `half_life_days=None` を「重みなし（無限大）」として扱い、既存挙動と完全互換にする（非破壊）。
- `model.train()` に `half_life_days: float | None = None` と `reference_date: pd.Timestamp | None = None` を追加。デフォルト `None` なので既存呼び出し元（`main.py`, `tuning.py` の他フォールド）は無変更で動作する。
- `model._build_dataset` / `_build_rank_dataset` に `weight: np.ndarray | None = None` を追加し、`lgb.Dataset(..., weight=weight)` に渡す。lambdarank 側は `df_s`（race_id, horse_number でソート済み）と行順序を揃える必要があるため、weight 配列もソート前の元 df のインデックスに対応させてから並び替える。
- CLI: `python -m predictor.main train [--time-decay] [--half-life-days N] [--no-walkforward]`。`--time-decay` 未指定時は従来通り重みなし。
- Optuna: `predictor/predictor/tuning.py` に `run_tuning(df, n_trials)` を追加。探索対象は `num_leaves`, `learning_rate`, `min_child_samples`, `feature_fraction`, `half_life_days`（`None` 相当として大きな値 or 専用カテゴリ選択肢を含む）。目的関数は `walk_forward_splits` で複数フォールドの平均回収率（`evaluation.evaluate` の `recovery_rate`）を最大化。
- 比較スクリプト: `predictor/predictor/half_life_experiment.py` に `run_comparison()` を追加。`half_life_days ∈ {365, 1095, 1825, 3650, None}` で学習→較正→評価し、fold別・全体の Log Loss・回収率を比較した DataFrame を返し `output/half_life_comparison_{timestamp}.csv` に保存。CLI: `python -m predictor.main compare-half-life`。

## タスク2（Embedding）の設計メモ（先行検討・タスク1完了後に着手）

- 対象カテゴリ: `jockey_id`, `trainer_id`, `sire`, `dam`（`broodmare_sire` も候補）。
- 学習は `predictor/predictor/embedding.py`（PyTorch, entity embedding + 着順予測補助タスク）で別プロセス実施し、`{category}_id -> vector` の辞書を pickle 保存。
- LightGBM 側は `get_feature_columns()` に embedding 由来の数値列（`{category}_emb_{i}`）を追加するかどうかをフラグで切り替え。既存の `jockey_id` 等のカテゴリ列自体は残す（併用）。
- 未知ID・欠損IDは学習時の平均ベクトルにフォールバック。
- 依存追加: `torch`（CPU版で十分。GPUは要件になし）。

---

> 実装が完了した項目は `docs/spec.md` の該当セクションに移す。

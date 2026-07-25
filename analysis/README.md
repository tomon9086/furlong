# analysis

DB データの探索的分析・可視化用の Jupyter 環境。モデル本体（`predictor`）とは分離し、
「試しに見てみる」ための使い捨て分析をここに置く。

## 起動

ルートで一度依存関係をインストール（初回のみ）:

```bash
uv sync --all-extras
uv run nbstripout --install
```

`nbstripout --install` はこのリポジトリの `.ipynb` を commit するたびに実行結果を自動で
剥がす git filter をローカルの `.git/config` に登録するコマンド。**clone ごとに一度実行が必要**
（`.gitattributes` 自体は commit 済みだが、filter の実体はローカル設定のため）。

Jupyter Lab を起動:

```bash
uv run --package furlong-analysis jupyter lab --notebook-dir=analysis
```

## ノートブックの管理方針

`.ipynb` をそのまま Git 管理する。ただし [nbstripout](https://github.com/kynan/nbstripout) の
git filter（`.gitattributes` 参照）により、commit 時に実行結果・`execution_count` などが
自動で取り除かれるため、差分にノイズが乗らない。

- ノートブックは自由に実行してよい（ローカルのファイルには出力が残ったままでOK）
- commit 時に自動で出力が剥がされるので、手動でクリアする必要はない
- 新しい環境で clone した場合は `uv run nbstripout --install` を忘れずに実行する

## DB 接続

`analysis/db.py` の `query_df(sql)` で任意の SQL を pandas DataFrame として取得できる。
接続情報はルートの `.env`（`DATABASE_URL`）を使う。

```python
from analysis.db import query_df

df = query_df("SELECT * FROM races LIMIT 10")
```

## 既存ノートブック

| ファイル | 内容 |
|---|---|
| `notebooks/01_data_overview.ipynb` | 各テーブルの件数・期間・欠損率など、データ全体のヘルスチェック |
| `notebooks/02_recovery_rate_analysis.ipynb` | 人気別の単勝・複勝回収率（モデルなしのベースライン把握） |

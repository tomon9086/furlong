# TODO

> 完了したタスクは削除せず、チェックを付けてください。
> セクション内のタスクがすべて完了したら、セクションごと削除してください。

## 実装

### scraper

- [x] netkeiba レースページのスクレイピング実装
- [x] netkeiba 馬ページのスクレイピング実装
- [x] 払い戻しデータのスクレイピング実装
- [x] DB 保存処理の実装

### predictor

- [x] データ前処理モジュール
- [x] 予測モデル実装
- [x] 評価モジュール
- [x] 出力モジュール

### repository パッケージ導入

- [x] `repository/` ディレクトリと `pyproject.toml` を作成（name = "furlong-repository"）
- [x] `scraper/types.py` → `repository/repository/models.py` へ移動
- [x] `scraper/database.py` → `repository/repository/database.py` へ移動
- [x] ルート `pyproject.toml` の `[tool.uv.workspace].members` に `"repository"` を追加
- [x] `scraper/pyproject.toml` に `furlong-repository = { workspace = true }` を追加し、`psycopg` 依存を削除
- [x] `predictor/pyproject.toml` に `furlong-repository = { workspace = true }` を追加し、`psycopg` 依存を削除
- [x] `scraper` 内の import を `repository.models` / `repository.database` に更新
- [x] `uv sync` で依存関係を再解決・動作確認

## テスト

- [ ] 単体テスト
- [ ] 統合テスト

## ドキュメント

- [ ] `spec.md` の記入（仕様確定後）
- [ ] `development.md` の記入（環境構築確定後）

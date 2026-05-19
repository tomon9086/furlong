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
- [ ] 予測モデル実装
- [ ] 評価モジュール
- [ ] 出力モジュール

### repository パッケージ導入

- [ ] `repository/` ディレクトリと `pyproject.toml` を作成（name = "furlong-repository"）
- [ ] `scraper/types.py` → `repository/repository/models.py` へ移動
- [ ] `scraper/database.py` → `repository/repository/database.py` へ移動
- [ ] ルート `pyproject.toml` の `[tool.uv.workspace].members` に `"repository"` を追加
- [ ] `scraper/pyproject.toml` に `furlong-repository = { workspace = true }` を追加し、`psycopg` 依存を削除
- [ ] `predictor/pyproject.toml` に `furlong-repository = { workspace = true }` を追加し、`psycopg` 依存を削除
- [ ] `scraper` 内の import を `repository.models` / `repository.database` に更新
- [ ] `uv sync` で依存関係を再解決・動作確認

## テスト

- [ ] 単体テスト
- [ ] 統合テスト

## ドキュメント

- [ ] `spec.md` の記入（仕様確定後）
- [ ] `development.md` の記入（環境構築確定後）

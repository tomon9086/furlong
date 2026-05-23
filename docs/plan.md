# 実装計画メモ（インデックス）

> 各トピックは `plan/` ディレクトリ配下のファイルに分割しました。
> 確定した仕様は `spec.md` に移してください。

---

## ファイル一覧

| ファイル | 内容 |
|---|---|
| [plan/overview.md](./plan/overview.md) | 概要・基本方針・学習方針・近走成績フィーチャー |
| [plan/repository-package.md](./plan/repository-package.md) | repository 共有パッケージの導入・SQL 設計メモ |
| [plan/future-race-prediction.md](./plan/future-race-prediction.md) | 未来レース予想機能（出馬表取得・予測クエリ分離） |
| [plan/horse-data-supplement.md](./plan/horse-data-supplement.md) | scrape_race / scrape_backfill における馬データの欠損問題 |
| [plan/prediction-accuracy.md](./plan/prediction-accuracy.md) | DB スキーマ調査メモ・予測精度の問題分析 |
| [plan/scraper-scheduler.md](./plan/scraper-scheduler.md) | scraper 定期実行機能（APScheduler） |
| [plan/predictor-api.md](./plan/predictor-api.md) | predictor HTTP API（FastAPI） |
| [plan/production-deploy.md](./plan/production-deploy.md) | 本番デプロイ構成（docker-compose.prod.yml） |
| [plan/db-backup.md](./plan/db-backup.md) | DB バックアップ（専用コンテナ・crond） |
| [plan/db-check-missing.md](./plan/db-check-missing.md) | DB 欠損チェックスクリプト |

---

> 実験結果は [experiments.md](./experiments.md) を参照。
>
> 次フェーズの改善計画は [improvement_plan.md](./improvement_plan.md) を参照。

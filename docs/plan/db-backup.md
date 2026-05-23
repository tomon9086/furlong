# DB バックアップ（検討中）

> このファイルは探索・議論の場です。決定前のアイデアや選択肢を自由に書いてください。
> 確定した仕様は `spec.md` に移してください。

---

## 背景・目的

- 本番 DB（PostgreSQL 16）はコンテナで稼働し、ポートはホスト非公開
- 障害・誤操作によるデータロストに備えて定期バックアップを行いたい
- **保持世代**: 7日分（7日より古いファイルは自動削除）
- **バッチ方式**: scraper の APScheduler と同じく Docker コンテナで定期実行

---

## 論点1: バックアップ先

本番 DB ポートが非公開のため `pg_dump` はコンテナ内から実行する必要がある。
バックアップファイルの置き先として以下の候補がある。

| 候補 | 概要 | メリット | デメリット |
|---|---|---|---|
| **A: ホスト bind mount** | コンテナ内で dump → ホストディレクトリへマウント | シンプル・追加コストなし | サーバごと消えると失う |
| **B: S3 / GCS（クラウド）** | dump → `aws s3 cp` / `gsutil cp` でアップロード | 耐障害性が高い・別サーバ復旧に使える | クラウド認証設定が必要 |
| **C: A + B の併用** | ローカルに保存しつつクラウドにも転送 | 両方の利点を享受 | 設定がやや複雑 |

**→ 決定: A（ホスト bind mount）から始め、将来的にクラウド対応できる設計にする**

---

## 論点2: バックアップコンテナの構成

scraper と同様の APScheduler 方式を基本としつつ、以下の選択肢がある。

### 案1: 専用 `backup` Docker サービスを追加

```yaml
backup:
  image: postgres:16-alpine   # pg_dump が同梱されている
  restart: always
  environment:
    PGPASSWORD: ${POSTGRES_PASSWORD}
  volumes:
    - ./backup:/backup        # ホストへ bind mount（バックアップ先が A の場合）
  networks:
    - backend
  depends_on:
    db:
      condition: service_healthy
  # シェルスクリプト or Python + APScheduler でスケジューリング
```

- **メリット**: `pg_dump` が既存イメージに含まれており追加インストール不要
- **デメリット**: サービスが増える（管理対象が増える）

### 案2: scraper コンテナに同居

- scraper の APScheduler にバックアップジョブを追加
- バックアップのために scraper に `pg_dump` が使える環境が必要（追加インストールか、Python の `subprocess` 呼び出しで `pg_dump` バイナリを使う）
- **メリット**: サービスを増やさなくて済む
- **デメリット**: scraper と backup の責務が混在する

### 案3: ホスト cron + docker exec

```sh
# crontab
0 3 * * * docker exec db pg_dump -U furlong furlong | gzip > /backup/furlong_$(date +\%Y\%m\%d).sql.gz
```

- **メリット**: Docker 設定不要・最もシンプル
- **デメリット**: scraper のバッチ方式（APScheduler in Docker）と統一されない

**→ 決定: 案1（専用 `backup` Docker サービス）を採用**

---

## 論点3: バックアップ形式・スクリプト構成

| 形式 | コマンド | 特徴 |
|---|---|---|
| プレーンSQL（gzip圧縮） | `pg_dump \| gzip` | 人間が読みやすい・どの環境でも復元しやすい |
| カスタム形式 | `pg_dump -Fc` | 圧縮済み・差分リストア可能・やや高機能 |

**ファイル命名案**: `furlong_YYYYMMDD_HHMMSS.sql.gz`

**世代管理（7日）**: `find /backup -name "*.sql.gz" -mtime +7 -delete`

---

## 未解決の論点

_なし（全論点決定済み）_

## 決定事項

- 保持世代: **7日分**（`find /backup -name "*.sql.gz" -mtime +7 -delete`）
- バックアップ先: **ホスト bind mount**（`./backup:/backup`）。将来クラウド対応できる設計に
- コンテナ構成: **専用 `backup` Docker サービス**（`postgres:16-alpine` ベース）
- バックアップ形式: **プレーンSQL + gzip 圧縮**（`.sql.gz`）
- ファイル命名: `furlong_YYYYMMDD_HHMMSS.sql.gz`
- スケジューラ: **シェルスクリプト + `crond`**（Alpine 内蔵）
- 実行時刻: **毎日深夜3:00**（レース結果取得バッチ 22:00 の後）
- 失敗通知: **ログのみ**（`docker logs` で確認）。将来アラート追加できる設計に

## 実装ステップ

1. `backup/backup.sh` を作成（`pg_dump | gzip` → `/backup/` に保存、7日以上古いファイルを削除）
2. `backup/crontab` を作成（`0 3 * * * /backup.sh`）
3. `backup/Dockerfile` を作成（`postgres:16-alpine` ベース、crontab を組み込む）
4. `docker-compose.prod.yml` に `backup` サービスを追加

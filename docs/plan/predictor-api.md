# predictor HTTP API（検討中）

> このファイルは探索・議論の場です。決定前のアイデアや選択肢を自由に書いてください。
> 確定した仕様は `spec.md` に移してください。

---

## 背景・目的

現状の predictor は CLI（`python -m predictor.main predict <race_id>`）でのみ利用できる。
HTTP API 化することで外部サービス・フロントエンドなどから予測結果を取得できるようにしたい。

## フレームワーク

**FastAPI** を採用（確定）

- 型安全・自動ドキュメント（Swagger UI）・非同期対応
- 既存の Python 環境に追加しやすい

## エンドポイント設計（案）

### `GET /health`

サービスの死活確認。

```json
{ "status": "ok" }
```

### `GET /predict/{race_id}`

指定レースの予測結果を返す。

**レスポンス例（案）:**

```json
{
  "race_id": "202506050811",
  "predictions": [
    {
      "horse_number": 1,
      "horse_name": "ドウデュース",
      "win_prob": 0.312,
      "place_prob": 0.618,
      "win_rank": 1,
      "place_rank": 1
    },
    ...
  ]
}
```

**エラーケース:**

| 状況 | HTTP ステータス | 挙動 |
|---|---|---|
| 出馬表が DB に未登録 | 404 | エラーメッセージを返す（自動取得はしない） |
| モデルファイルが存在しない | 503 | エラーメッセージを返す |

## モデルのロード戦略

- **サーバ起動時に1回だけロード**してメモリに保持する（リクエストごとのロードは重い）
- モデルディレクトリが更新された場合は再起動が必要（または `/reload` エンドポイントを追加）

## 実装構成（案）

```
predictor/
└── predictor/
    ├── main.py         # 既存 CLI エントリーポイント
    ├── api.py          # FastAPI アプリ定義（新設）
    ├── model.py        # 既存（モデルロード・推論）
    └── ...
```

起動コマンド（案）:
```
uv run --package furlong-predictor uvicorn predictor.api:app --host 0.0.0.0 --port 8000
```

## 決定事項

- `/predict/{race_id}` で出馬表が DB に未登録の場合は **404 を返す**（API 内で自動スクレイプしない）
  - 出馬表は scraper バッチ1（`scrape_shutuba_upcoming()`、毎日14:00）で事前に自動取得されるため、通常は DB に揃っている想定
- レスポンス形式: `output.print_prediction()` の出力に近い形（`win_prob`・`place_prob`・順位など）
- Docker サービスとして **常駐**（`docker-compose.yml` に追加）
- `uvicorn`（FastAPI を動かす ASGI サーバ）は `furlong-predictor` の `pyproject.toml` に依存追加

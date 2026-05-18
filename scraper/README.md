# furlong-scraper

netkeiba のスクレイパー。レースデータ・馬データ・払い戻しデータを取得し PostgreSQL に保存します。

## セットアップ

```bash
cd scraper
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp ../.env.example ../.env  # 必要に応じて編集
```

## 実行

```bash
python -m scraper.main
```

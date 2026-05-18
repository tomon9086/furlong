# furlong-predictor

競馬予想プログラム。PostgreSQL からレースデータを読み込み、予想結果を出力します。

予測アプローチは未定（単純統計 or 機械学習）。

## セットアップ

```bash
cd predictor
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
# 機械学習を使う場合
# pip install -e ".[dev,ml]"
cp ../.env.example ../.env  # 必要に応じて編集
```

## 実行

```bash
python -m predictor.main
```

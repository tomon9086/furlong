# repository 共有パッケージの導入（検討中）

> このファイルは探索・議論の場です。決定前のアイデアや選択肢を自由に書いてください。
> 確定した仕様は `spec.md` に移してください。

---

## 背景

- `scraper` が `Database` クラスと型定義（`types.py`）を持っている
- `predictor` も今後 DB アクセスが必要になる
- このまま進めると DB 接続コードと型定義が重複・乖離するリスクがある

## 方針

uv workspace の既存構成を活かし、`repository` パッケージを新設して共有層にする。

```
furlong/
├── pyproject.toml          # members に "repository" を追加
├── repository/             # 新設
│   ├── pyproject.toml      # name = "furlong-repository", psycopg 依存はここに集約
│   └── repository/
│       ├── __init__.py
│       ├── models.py       # 現 scraper/types.py の TypedDict 群を移動
│       └── database.py     # 現 scraper/database.py の Database クラスを移動
├── scraper/
│   ├── pyproject.toml      # furlong-repository = { workspace = true } を追加、psycopg 依存を削除
│   └── scraper/
│       ├── types.py        # 削除（models.py に統合）
│       └── database.py     # 削除（repository に移動）
└── predictor/
    ├── pyproject.toml      # furlong-repository = { workspace = true } を追加、psycopg 依存を削除
    └── ...
```

## メリット

- `psycopg` 依存が `repository` 側に一本化される
- 型定義（`HorseProfile` 等）が一元化され、scraper/predictor で同じモデルを使える
- predictor の DB アクセス実装時にゼロから書く必要がない

## 懸念点

- scraper 内の import パスが変わる（`from .types import ...` → `from repository.models import ...`）
- 現時点では predictor の DB アクセスは未実装のため、恩恵はまだ小さい

## 結論

→ 議論中。実施する場合は `spec.md` に移す。

## SQL 設計メモ（予測時用）

リーク防止のため `ROWS BETWEEN N PRECEDING AND 1 PRECEDING` を使い、当該レース自身を集計から除外する。
同日に複数レースがある場合の順序安定化のため `ORDER BY race_date, race_id` とする。
`last_3f` が数値以外（`'-'` など）の場合は NULL に変換して集計から除外する。

```sql
WITH base AS (
  SELECT
    rr.race_id,
    rr.horse_id,
    TO_DATE(r.date, 'YYYY/MM/DD') AS race_date,
    r.course_type,
    r.distance,
    rr.finishing_position::integer AS finishing_pos,
    CASE WHEN rr.last_3f ~ '^\d+\.?\d*$' THEN rr.last_3f::float ELSE NULL END AS last_3f_num
  FROM race_results rr
  JOIN races r ON rr.race_id = r.race_id
  WHERE rr.finishing_position ~ '^[0-9]+$'
)
SELECT
  race_id,
  horse_id,
  -- 全レース 直近3走
  AVG(finishing_pos) OVER (PARTITION BY horse_id
    ORDER BY race_date, race_id ROWS BETWEEN 3 PRECEDING AND 1 PRECEDING) AS avg_finish_last3,
  MIN(finishing_pos) OVER (PARTITION BY horse_id
    ORDER BY race_date, race_id ROWS BETWEEN 3 PRECEDING AND 1 PRECEDING) AS best_finish_last3,
  AVG(last_3f_num)   OVER (PARTITION BY horse_id
    ORDER BY race_date, race_id ROWS BETWEEN 3 PRECEDING AND 1 PRECEDING) AS avg_last3f_last3,
  -- 全レース 直近5走
  AVG(finishing_pos) OVER (PARTITION BY horse_id
    ORDER BY race_date, race_id ROWS BETWEEN 5 PRECEDING AND 1 PRECEDING) AS avg_finish_last5,
  MIN(finishing_pos) OVER (PARTITION BY horse_id
    ORDER BY race_date, race_id ROWS BETWEEN 5 PRECEDING AND 1 PRECEDING) AS best_finish_last5,
  AVG(last_3f_num)   OVER (PARTITION BY horse_id
    ORDER BY race_date, race_id ROWS BETWEEN 5 PRECEDING AND 1 PRECEDING) AS avg_last3f_last5,
  -- 条件別 直近3走
  AVG(finishing_pos) OVER (PARTITION BY horse_id, course_type, distance
    ORDER BY race_date, race_id ROWS BETWEEN 3 PRECEDING AND 1 PRECEDING) AS avg_finish_last3_cond,
  MIN(finishing_pos) OVER (PARTITION BY horse_id, course_type, distance
    ORDER BY race_date, race_id ROWS BETWEEN 3 PRECEDING AND 1 PRECEDING) AS best_finish_last3_cond,
  AVG(last_3f_num)   OVER (PARTITION BY horse_id, course_type, distance
    ORDER BY race_date, race_id ROWS BETWEEN 3 PRECEDING AND 1 PRECEDING) AS avg_last3f_last3_cond,
  -- 条件別 直近5走
  AVG(finishing_pos) OVER (PARTITION BY horse_id, course_type, distance
    ORDER BY race_date, race_id ROWS BETWEEN 5 PRECEDING AND 1 PRECEDING) AS avg_finish_last5_cond,
  MIN(finishing_pos) OVER (PARTITION BY horse_id, course_type, distance
    ORDER BY race_date, race_id ROWS BETWEEN 5 PRECEDING AND 1 PRECEDING) AS best_finish_last5_cond,
  AVG(last_3f_num)   OVER (PARTITION BY horse_id, course_type, distance
    ORDER BY race_date, race_id ROWS BETWEEN 5 PRECEDING AND 1 PRECEDING) AS avg_last3f_last5_cond
FROM base
```

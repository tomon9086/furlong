"""ノートブックからの DB アクセス用ヘルパー。

ルートの `.env` の `DATABASE_URL` を使って PostgreSQL に接続する。
"""

from __future__ import annotations

import os
from typing import Any

import pandas as pd
import psycopg
from dotenv import load_dotenv

load_dotenv()


def get_database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL が設定されていません（.env を確認してください）")
    return url


def query_df(sql: str, params: tuple[Any, ...] | list[Any] | None = None) -> pd.DataFrame:
    """SQL を実行して結果を DataFrame で返す。"""
    with psycopg.connect(get_database_url()) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
            cols = [desc[0] for desc in cur.description]
    return pd.DataFrame(rows, columns=cols)
